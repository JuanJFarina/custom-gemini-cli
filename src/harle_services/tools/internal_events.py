from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Literal, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harle_domain.events import InternalEvent
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
    EventQuery,
    EventSchedule,
    EventService,
    TimedEventSchedule,
    UpdateEvent,
)

from .registry import ToolFamilyRegistration, ToolHandlerFactory

ModelT = TypeVar("ModelT", bound=BaseModel)
ScheduleKind = Literal["timed", "all_day"]


class ListEventsArgs(BaseModel):
    start_date: date
    end_date: date
    include_cancelled: bool = False

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

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_changes(self) -> "UpdateEventArgs":
        schedule_kind = _schedule_kind(self, required=False)
        if self.title is None and self.description is None and schedule_kind is None:
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
- Normal reads hide cancelled events; include them only when explicitly requested. Deleted events are always hidden and retained without automatic purging.
- These passive one-time events never create recurrence, reminders, notifications, external calendar work, or background jobs."""

DEFINITIONS = (
    ToolDefinition(
        name="list_events",
        family=FAMILY,
        description=(
            "List events overlapping an inclusive local date range. Cancelled "
            "events are optional and deleted events are excluded."
        ),
        argument_model=ListEventsArgs,
        effect=ToolEffect.READ,
        can_run_concurrently=True,
    ),
    ToolDefinition(
        name="create_event",
        family=FAMILY,
        description="Create one timed or all-day internal event.",
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
        name="cancel_event",
        family=FAMILY,
        description="Cancel an owned scheduled event by UUID.",
        argument_model=EventIdentifierArgs,
        effect=ToolEffect.MODIFY,
        can_run_concurrently=False,
    ),
    ToolDefinition(
        name="delete_event",
        family=FAMILY,
        description="Soft-delete an owned scheduled or cancelled event by UUID.",
        argument_model=EventIdentifierArgs,
        effect=ToolEffect.MODIFY,
        can_run_concurrently=False,
    ),
)


def create_internal_events_registration(
    service: EventService,
) -> ToolFamilyRegistration:
    def build_handlers(
        context: ToolExecutionContext,
    ) -> Mapping[str, ToolHandler]:
        async def list_events(args: BaseModel) -> ToolCallResult:
            context.require_family(FAMILY)
            validated = _require_model(args, ListEventsArgs)
            events = await service.list_for_range(
                user_id=context.user_id,
                query=EventQuery(
                    start_date=validated.start_date,
                    end_date=validated.end_date,
                    timezone_name=context.timezone,
                    include_cancelled=validated.include_cancelled,
                ),
            )
            return ToolCallResult(
                called_tool_name="list_events",
                result={
                    "ok": True,
                    "start_date": validated.start_date.isoformat(),
                    "end_date": validated.end_date.isoformat(),
                    "events": [_event_payload(event) for event in events],
                },
            )

        async def create_event(args: BaseModel) -> ToolCallResult:
            context.require_family(FAMILY)
            validated = _require_model(args, CreateEventArgs)
            event = await service.create(
                user_id=context.user_id,
                event=CreateEvent(
                    title=validated.title,
                    description=validated.description,
                    schedule=_schedule(validated, context.timezone),
                ),
            )
            return ToolCallResult(
                called_tool_name="create_event",
                result=_mutation_payload(event, "created"),
            )

        async def update_event(args: BaseModel) -> ToolCallResult:
            context.require_family(FAMILY)
            validated = _require_model(args, UpdateEventArgs)
            event = await service.update(
                user_id=context.user_id,
                event_id=validated.event_id,
                changes=UpdateEvent(
                    title=validated.title,
                    description=validated.description,
                    schedule=_optional_schedule(validated, context.timezone),
                ),
            )
            return ToolCallResult(
                called_tool_name="update_event",
                result=_mutation_payload(event, "updated"),
            )

        async def cancel_event(args: BaseModel) -> ToolCallResult:
            context.require_family(FAMILY)
            validated = _require_model(args, EventIdentifierArgs)
            event = await service.cancel(
                user_id=context.user_id,
                event_id=validated.event_id,
            )
            return ToolCallResult(
                called_tool_name="cancel_event",
                result=_mutation_payload(event, "cancelled"),
            )

        async def delete_event(args: BaseModel) -> ToolCallResult:
            context.require_family(FAMILY)
            validated = _require_model(args, EventIdentifierArgs)
            event = await service.delete(
                user_id=context.user_id,
                event_id=validated.event_id,
            )
            return ToolCallResult(
                called_tool_name="delete_event",
                result=_mutation_payload(event, "deleted"),
            )

        return {
            "list_events": list_events,
            "create_event": create_event,
            "update_event": update_event,
            "cancel_event": cancel_event,
            "delete_event": delete_event,
        }

    return _event_registration(build_handlers)


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


def _mutation_payload(
    event: InternalEvent | None,
    operation: str,
) -> Mapping[str, object]:
    return {
        "ok": event is not None,
        "operation": operation,
        "reason": None if event is not None else "Event was not found.",
        "event": _event_payload(event) if event is not None else None,
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
        "status": event.status.value,
    }


def _require_model(value: BaseModel, expected: type[ModelT]) -> ModelT:
    if not isinstance(value, expected):
        raise TypeError("Validated tool arguments do not match the tool definition.")
    return value
