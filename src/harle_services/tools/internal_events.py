from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Annotated, Literal, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harle_domain.events import (
    EventType,
    InternalEvent,
    MonthlyRecurrence,
    RecurrenceRule,
    WeekDay,
    WeeklyRecurrence,
)
from harle_domain.tools import (
    ToolCallResult,
    ToolDefinition,
    ToolEffect,
    ToolExecutionContext,
    ToolFamily,
    ToolHandler,
)
from harle_services.events import (
    AllDayEventSchedule,
    CreateEvent,
    EventNotificationQuotaService,
    EventQuery,
    EventSchedule,
    EventService,
    TimedEventSchedule,
    UpdateEvent,
)

from .registry import ToolFamilyRegistration, ToolHandlerFactory

ModelT = TypeVar("ModelT", bound=BaseModel)
ScheduleKind = Literal["timed", "all_day"]


class WeeklyRecurrenceArgs(BaseModel):
    week_days: set[WeekDay] = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")


MonthDay = Annotated[int, Field(ge=1, le=31)]


class MonthlyRecurrenceArgs(BaseModel):
    month_days: set[MonthDay] = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")


RecurrenceArgs = WeeklyRecurrenceArgs | MonthlyRecurrenceArgs


class ListEventsArgs(BaseModel):
    start_date: date
    end_date: date
    include_disabled: bool = False

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_range(self) -> "ListEventsArgs":
        if self.end_date < self.start_date:
            raise ValueError("Event range end date cannot precede its start date.")
        return self


class CreateEventArgs(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    start_date: date | None = None
    end_date: date | None = None
    timezone: str | None = Field(default=None, min_length=1)
    event_type: EventType = EventType.USER_EVENT
    notify_minutes_before: int = Field(default=0, ge=0)
    recurrence_rule: RecurrenceArgs | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_schedule(self) -> "CreateEventArgs":
        _schedule_kind(self, required=True)
        return self


class UpdateEventArgs(BaseModel):
    event_id: UUID
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    start_date: date | None = None
    end_date: date | None = None
    timezone: str | None = Field(default=None, min_length=1)
    event_type: EventType | None = None
    notify_minutes_before: int | None = Field(default=None, ge=0)
    recurrence_rule: RecurrenceArgs | None = None

    model_config = ConfigDict(extra="forbid")

    @property
    def replaces_recurrence(self) -> bool:
        return "recurrence_rule" in self.model_fields_set

    @model_validator(mode="after")
    def validate_changes(self) -> "UpdateEventArgs":
        schedule_kind = _schedule_kind(self, required=False)
        changes = (
            self.title,
            self.description,
            schedule_kind,
            self.event_type,
            self.notify_minutes_before,
            self.replaces_recurrence,
        )
        if changes == (None, None, None, None, None, False):
            raise ValueError("At least one event change is required.")
        return self


class EventIdentifierArgs(BaseModel):
    event_id: UUID

    model_config = ConfigDict(extra="forbid")


FAMILY = ToolFamily.INTERNAL_EVENTS

SHARED_INSTRUCTIONS = """For every internal event tool:
- Timed event starts_at and ends_at are local ISO date-times without UTC offsets. A supplied IANA timezone overrides the user's profile timezone.
- All-day events use start_date and inclusive end_date. Use the same date for a one-day event.
- Use exactly one complete timed or all-day schedule. Updating a schedule may also change between timed and all-day.
- Use user_event for the user's agenda and system_event for an internal reminder or task for the assistant.
- notify_minutes_before defaults to 0 on creation, meaning notification at event start. On update, omission preserves the current lead.
- recurrence_rule is either {"week_days": [...]} for infinite weekly recurrence or {"month_days": [...]} for infinite monthly recurrence. Omit it for a one-time event.
- On update, omit recurrence_rule to preserve it or send null to make the event one-time.
- Recurring events remain one event definition. A missing month day produces no occurrence, and every update changes the complete definition.
- Normal reads hide disabled events; include them only when explicitly requested. Disabling is reversible and deletion is permanent.
- Event results include the user's separate monthly notification limit, remaining allowance, and UTC reset boundary.
- Events never create external calendar work."""

DEFINITIONS = (
    ToolDefinition(
        name="list_events",
        family=FAMILY,
        description=(
            "List events overlapping an inclusive local date range. Disabled "
            "events are optional."
        ),
        argument_model=ListEventsArgs,
        effect=ToolEffect.READ,
        can_run_concurrently=True,
    ),
    ToolDefinition(
        name="create_event",
        family=FAMILY,
        description="Create a one-time or recurring timed or all-day event.",
        argument_model=CreateEventArgs,
        effect=ToolEffect.MODIFY,
        can_run_concurrently=False,
    ),
    ToolDefinition(
        name="update_event",
        family=FAMILY,
        description=(
            "Partially update an owned scheduled event by UUID, optionally "
            "replacing its complete schedule."
        ),
        argument_model=UpdateEventArgs,
        effect=ToolEffect.MODIFY,
        can_run_concurrently=False,
    ),
    ToolDefinition(
        name="disable_event",
        family=FAMILY,
        description="Disable an owned active event by UUID.",
        argument_model=EventIdentifierArgs,
        effect=ToolEffect.MODIFY,
        can_run_concurrently=False,
    ),
    ToolDefinition(
        name="enable_event",
        family=FAMILY,
        description="Re-enable an owned disabled event by UUID.",
        argument_model=EventIdentifierArgs,
        effect=ToolEffect.MODIFY,
        can_run_concurrently=False,
    ),
    ToolDefinition(
        name="delete_event",
        family=FAMILY,
        description="Permanently delete an owned active or disabled event by UUID.",
        argument_model=EventIdentifierArgs,
        effect=ToolEffect.MODIFY,
        can_run_concurrently=False,
    ),
)


def create_internal_events_registration(
    service: EventService,
    notification_quotas: EventNotificationQuotaService,
) -> ToolFamilyRegistration:
    def build_handlers(
        context: ToolExecutionContext,
    ) -> Mapping[str, ToolHandler]:
        return _EventToolHandlers(
            service,
            notification_quotas,
            context,
        ).mapping()

    return _event_registration(build_handlers)


@dataclass(frozen=True, slots=True)
class _EventToolHandlers:
    service: EventService
    notification_quotas: EventNotificationQuotaService
    context: ToolExecutionContext

    def mapping(self) -> Mapping[str, ToolHandler]:
        return {
            "list_events": self.list_events,
            "create_event": self.create_event,
            "update_event": self.update_event,
            "disable_event": self.disable_event,
            "enable_event": self.enable_event,
            "delete_event": self.delete_event,
        }

    async def list_events(self, args: BaseModel) -> ToolCallResult:
        self.context.require_family(FAMILY)
        validated = _require_model(args, ListEventsArgs)
        notification_quota = await self._notification_quota()
        events = await self.service.list_for_range(
            user_id=self.context.user_id,
            query=EventQuery(
                start_date=validated.start_date,
                end_date=validated.end_date,
                timezone_name=self.context.timezone,
                include_disabled=validated.include_disabled,
            ),
        )
        return ToolCallResult(
            called_tool_name="list_events",
            result={
                "ok": True,
                "start_date": validated.start_date.isoformat(),
                "end_date": validated.end_date.isoformat(),
                "events": [_event_payload(event) for event in events],
                "notification_quota": notification_quota,
            },
        )

    async def create_event(self, args: BaseModel) -> ToolCallResult:
        self.context.require_family(FAMILY)
        validated = _require_model(args, CreateEventArgs)
        notification_quota = await self._notification_quota()
        event = await self.service.create(
            user_id=self.context.user_id,
            event=CreateEvent(
                title=validated.title,
                description=validated.description,
                schedule=_schedule(validated, self.context.timezone),
                event_type=validated.event_type,
                notify_before=timedelta(
                    minutes=validated.notify_minutes_before,
                ),
                recurrence_rule=_recurrence_rule(validated.recurrence_rule),
            ),
        )
        return ToolCallResult(
            called_tool_name="create_event",
            result=_mutation_payload(event, "created", notification_quota),
        )

    async def update_event(self, args: BaseModel) -> ToolCallResult:
        self.context.require_family(FAMILY)
        validated = _require_model(args, UpdateEventArgs)
        notification_quota = await self._notification_quota()
        event = await self.service.update(
            user_id=self.context.user_id,
            event_id=validated.event_id,
            changes=UpdateEvent(
                title=validated.title,
                description=validated.description,
                schedule=_optional_schedule(validated, self.context.timezone),
                event_type=validated.event_type,
                notify_before=(
                    timedelta(minutes=validated.notify_minutes_before)
                    if validated.notify_minutes_before is not None
                    else None
                ),
                recurrence_rule=_recurrence_rule(validated.recurrence_rule),
                replace_recurrence=validated.replaces_recurrence,
            ),
        )
        return ToolCallResult(
            called_tool_name="update_event",
            result=_mutation_payload(event, "updated", notification_quota),
        )

    async def disable_event(self, args: BaseModel) -> ToolCallResult:
        self.context.require_family(FAMILY)
        validated = _require_model(args, EventIdentifierArgs)
        notification_quota = await self._notification_quota()
        event = await self.service.disable(
            user_id=self.context.user_id,
            event_id=validated.event_id,
        )
        return ToolCallResult(
            called_tool_name="disable_event",
            result=_mutation_payload(event, "disabled", notification_quota),
        )

    async def enable_event(self, args: BaseModel) -> ToolCallResult:
        self.context.require_family(FAMILY)
        validated = _require_model(args, EventIdentifierArgs)
        notification_quota = await self._notification_quota()
        event = await self.service.enable(
            user_id=self.context.user_id,
            event_id=validated.event_id,
        )
        return ToolCallResult(
            called_tool_name="enable_event",
            result=_mutation_payload(event, "enabled", notification_quota),
        )

    async def delete_event(self, args: BaseModel) -> ToolCallResult:
        self.context.require_family(FAMILY)
        validated = _require_model(args, EventIdentifierArgs)
        notification_quota = await self._notification_quota()
        event = await self.service.delete(
            user_id=self.context.user_id,
            event_id=validated.event_id,
        )
        return ToolCallResult(
            called_tool_name="delete_event",
            result=_mutation_payload(event, "deleted", notification_quota),
        )

    async def _notification_quota(self) -> Mapping[str, object]:
        return await _notification_quota_payload(
            self.notification_quotas,
            self.context,
        )


def _event_registration(
    handler_factory: ToolHandlerFactory,
) -> ToolFamilyRegistration:
    return ToolFamilyRegistration(
        FAMILY,
        SHARED_INSTRUCTIONS,
        DEFINITIONS,
        handler_factory,
    )


def _schedule(
    args: CreateEventArgs | UpdateEventArgs,
    default_timezone: str,
) -> EventSchedule:
    schedule = _optional_schedule(args, default_timezone)
    if schedule is None:
        raise ValueError("A complete event schedule is required.")
    return schedule


def _optional_schedule(
    args: CreateEventArgs | UpdateEventArgs,
    default_timezone: str,
) -> EventSchedule | None:
    kind = _schedule_kind(args, required=False)
    if kind is None:
        return None
    timezone_name = args.timezone or default_timezone
    if kind == "timed":
        assert args.starts_at is not None
        assert args.ends_at is not None
        return TimedEventSchedule(
            starts_at=args.starts_at,
            ends_at=args.ends_at,
            timezone_name=timezone_name,
        )
    assert args.start_date is not None
    assert args.end_date is not None
    return AllDayEventSchedule(
        start_date=args.start_date,
        end_date=args.end_date,
        timezone_name=timezone_name,
    )


def _schedule_kind(
    args: CreateEventArgs | UpdateEventArgs,
    *,
    required: bool,
) -> ScheduleKind | None:
    timed_values = (args.starts_at, args.ends_at)
    all_day_values = (args.start_date, args.end_date)
    has_timed = any(value is not None for value in timed_values)
    has_all_day = any(value is not None for value in all_day_values)
    if has_timed and has_all_day:
        raise ValueError("Use either a timed or an all-day event schedule.")
    if has_timed:
        if any(value is None for value in timed_values):
            raise ValueError("Timed events require both starts_at and ends_at.")
        return "timed"
    if has_all_day:
        if any(value is None for value in all_day_values):
            raise ValueError("All-day events require both start_date and end_date.")
        return "all_day"
    if args.timezone is not None:
        raise ValueError("A timezone can only be supplied with an event schedule.")
    if required:
        raise ValueError("A timed or all-day event schedule is required.")
    return None


def _recurrence_rule(value: RecurrenceArgs | None) -> RecurrenceRule | None:
    if isinstance(value, WeeklyRecurrenceArgs):
        return WeeklyRecurrence(frozenset(value.week_days))
    if isinstance(value, MonthlyRecurrenceArgs):
        return MonthlyRecurrence(frozenset(value.month_days))
    return None


def _recurrence_payload(
    value: RecurrenceRule | None,
) -> Mapping[str, object] | None:
    if isinstance(value, WeeklyRecurrence):
        return {
            "week_days": sorted(day.value for day in value.days),
        }
    if isinstance(value, MonthlyRecurrence):
        return {"month_days": sorted(value.days)}
    return None


def _mutation_payload(
    event: InternalEvent | None,
    operation: str,
    notification_quota: Mapping[str, object],
) -> Mapping[str, object]:
    return {
        "ok": event is not None,
        "operation": operation,
        "reason": None if event is not None else "Event was not found.",
        "event": _event_payload(event) if event is not None else None,
        "notification_quota": notification_quota,
    }


async def _notification_quota_payload(
    service: EventNotificationQuotaService,
    context: ToolExecutionContext,
) -> Mapping[str, object]:
    status = await service.status(
        user_id=context.user_id,
        monthly_limit=context.monthly_notification_limit,
    )
    return {
        "monthly_limit": status.limit,
        "remaining": status.remaining,
        "resets_at": status.resets_at.isoformat().replace("+00:00", "Z"),
    }


def _event_payload(event: InternalEvent) -> Mapping[str, object]:
    timezone_info = ZoneInfo(event.timezone)
    local_start = event.starts_at.astimezone(timezone_info)
    local_end = event.ends_at.astimezone(timezone_info)
    if event.all_day:
        start_value = local_start.date().isoformat()
        end_value = (local_end.date() - timedelta(days=1)).isoformat()
    else:
        start_value = local_start.isoformat()
        end_value = local_end.isoformat()
    return {
        "event_id": str(event.id),
        "title": event.title,
        "description": event.description,
        "local_start": start_value,
        "local_end": end_value,
        "timezone": event.timezone,
        "all_day": event.all_day,
        "event_type": event.event_type.value,
        "status": event.status.value,
        "recurrence_rule": _recurrence_payload(event.recurrence_rule),
        "notification_window_start": event.notification_window_start.astimezone(
            timezone_info,
        ).isoformat(),
        "notify_minutes_before": int(
            (event.starts_at - event.notification_window_start).total_seconds() / 60,
        ),
        "last_notified_at": (
            event.last_notified_at.astimezone(timezone_info).isoformat()
            if event.last_notified_at is not None
            else None
        ),
    }


def _require_model(value: BaseModel, expected: type[ModelT]) -> ModelT:
    if not isinstance(value, expected):
        raise TypeError("Validated tool arguments do not match the tool definition.")
    return value
