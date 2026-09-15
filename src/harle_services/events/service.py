from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

from harle_domain.events import (
    EventDetails,
    EventInterval,
    EventNotification,
    EventRepository,
    EventStatus,
    EventTimestamps,
    EventType,
    InternalEvent,
    NotificationStatus,
    all_day_event_interval,
    event_range,
    timed_event_interval,
)

DEFAULT_NOTIFICATION_LEAD = timedelta(minutes=15)
DEFAULT_DUE_EVENT_LIMIT = 100


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class TimedEventSchedule:
    starts_at: datetime
    ends_at: datetime
    timezone_name: str

    def to_interval(self) -> EventInterval:
        return timed_event_interval(
            starts_at=self.starts_at,
            ends_at=self.ends_at,
            timezone_name=self.timezone_name,
        )


@dataclass(frozen=True, slots=True)
class AllDayEventSchedule:
    start_date: date
    end_date: date
    timezone_name: str

    def to_interval(self) -> EventInterval:
        return all_day_event_interval(
            start_date=self.start_date,
            end_date=self.end_date,
            timezone_name=self.timezone_name,
        )


EventSchedule = TimedEventSchedule | AllDayEventSchedule


@dataclass(frozen=True, slots=True)
class CreateEvent:
    title: str
    description: str
    schedule: EventSchedule
    event_type: EventType = EventType.USER_EVENT
    notify_before: timedelta = DEFAULT_NOTIFICATION_LEAD
    notifications_enabled: bool = True

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Event title cannot be empty.")
        _require_notification_lead(self.notify_before)


@dataclass(frozen=True, slots=True)
class UpdateEvent:
    title: str | None = None
    description: str | None = None
    schedule: EventSchedule | None = None
    event_type: EventType | None = None
    notify_before: timedelta | None = None
    notifications_enabled: bool | None = None

    def __post_init__(self) -> None:
        changes = (
            self.title,
            self.description,
            self.schedule,
            self.event_type,
            self.notify_before,
            self.notifications_enabled,
        )
        if all(change is None for change in changes):
            raise ValueError("At least one event change is required.")
        if self.title is not None and not self.title.strip():
            raise ValueError("Event title cannot be empty.")
        if self.notify_before is not None:
            _require_notification_lead(self.notify_before)


@dataclass(frozen=True, slots=True)
class EventQuery:
    start_date: date
    end_date: date
    timezone_name: str
    include_cancelled: bool = False


@dataclass(frozen=True, slots=True)
class EventService:
    repository: EventRepository
    clock: Callable[[], datetime] = utc_now

    async def list_for_range(
        self,
        *,
        user_id: UUID,
        query: EventQuery,
    ) -> Sequence[InternalEvent]:
        bounded_range = event_range(
            start_date=query.start_date,
            end_date=query.end_date,
            timezone_name=query.timezone_name,
        )
        return await self.repository.list_for_range(
            user_id=user_id,
            starts_at=bounded_range.starts_at,
            ends_at=bounded_range.ends_at,
            include_cancelled=query.include_cancelled,
        )

    async def create(
        self,
        *,
        user_id: UUID,
        event: CreateEvent,
    ) -> InternalEvent:
        now = self._now()
        interval = event.schedule.to_interval()
        notification_lead = _normalize_notification_lead(event.notify_before)
        created = InternalEvent(
            id=uuid4(),
            user_id=user_id,
            details=EventDetails(
                title=event.title.strip(),
                description=event.description.strip(),
                interval=interval,
                event_type=event.event_type,
                status=EventStatus.SCHEDULED,
            ),
            notification=EventNotification(
                window_start=interval.starts_at - notification_lead,
                status=(
                    NotificationStatus.PENDING
                    if event.notifications_enabled
                    else NotificationStatus.DISABLED
                ),
            ),
            timestamps=EventTimestamps(
                created_at=now,
                updated_at=now,
            ),
        )
        return await self.repository.create(user_id=user_id, event=created)

    async def update(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        changes: UpdateEvent,
    ) -> InternalEvent | None:
        current = await self.repository.get(
            user_id=user_id,
            event_id=event_id,
        )
        if current is None:
            return None
        interval = (
            changes.schedule.to_interval()
            if changes.schedule is not None
            else current.details.interval
        )
        notification_lead = (
            _normalize_notification_lead(changes.notify_before)
            if changes.notify_before is not None
            else current.starts_at - current.notification_window_start
        )
        notification_window_start = interval.starts_at - notification_lead
        notification_changed = (
            interval.starts_at != current.starts_at
            or notification_window_start != current.notification_window_start
        )
        updated = replace(
            current,
            details=replace(
                current.details,
                title=(
                    changes.title.strip()
                    if changes.title is not None
                    else current.title
                ),
                description=(
                    changes.description.strip()
                    if changes.description is not None
                    else current.description
                ),
                interval=interval,
                event_type=changes.event_type or current.event_type,
            ),
            notification=replace(
                current.notification,
                window_start=notification_window_start,
                status=_updated_notification_status(
                    current.notification_status,
                    notifications_enabled=changes.notifications_enabled,
                    notification_changed=notification_changed,
                ),
            ),
            timestamps=replace(current.timestamps, updated_at=self._now()),
        )
        return await self.repository.update(user_id=user_id, event=updated)

    async def list_due_for_notification(
        self,
        *,
        limit: int = DEFAULT_DUE_EVENT_LIMIT,
    ) -> Sequence[InternalEvent]:
        if limit <= 0:
            raise ValueError("Due event limit must be positive.")
        return await self.repository.list_due_for_notification(
            current_time=self._now(),
            limit=limit,
        )

    async def mark_notification_delivered(
        self,
        *,
        event: InternalEvent,
    ) -> InternalEvent | None:
        return await self.repository.mark_notification_delivered(
            user_id=event.user_id,
            event_id=event.id,
            expected_updated_at=event.updated_at,
            updated_at=self._now(),
        )

    async def cancel(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
    ) -> InternalEvent | None:
        return await self.repository.cancel(
            user_id=user_id,
            event_id=event_id,
            cancelled_at=self._now(),
        )

    async def delete(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
    ) -> InternalEvent | None:
        return await self.repository.delete(
            user_id=user_id,
            event_id=event_id,
        )

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Event service clock must return a timezone-aware time.")
        return now.astimezone(timezone.utc)


def _require_notification_lead(value: timedelta) -> None:
    if value < timedelta(0):
        raise ValueError("Event notification lead cannot be negative.")


def _normalize_notification_lead(value: timedelta) -> timedelta:
    _require_notification_lead(value)
    return DEFAULT_NOTIFICATION_LEAD if value == timedelta(0) else value


def _updated_notification_status(
    current: NotificationStatus,
    *,
    notifications_enabled: bool | None,
    notification_changed: bool,
) -> NotificationStatus:
    if notifications_enabled is False:
        return NotificationStatus.DISABLED
    if current is NotificationStatus.DISABLED:
        return (
            NotificationStatus.PENDING
            if notifications_enabled
            else NotificationStatus.DISABLED
        )
    if notification_changed:
        return NotificationStatus.PENDING
    return current
