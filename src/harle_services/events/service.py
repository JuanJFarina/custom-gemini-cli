from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from harle_domain.events import (
    EventDetails,
    EventInterval,
    EventRepository,
    EventStatus,
    EventTimestamps,
    InternalEvent,
    all_day_event_interval,
    event_range,
    timed_event_interval,
)


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

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Event title cannot be empty.")


@dataclass(frozen=True, slots=True)
class UpdateEvent:
    title: str | None = None
    description: str | None = None
    schedule: EventSchedule | None = None

    def __post_init__(self) -> None:
        if self.title is None and self.description is None and self.schedule is None:
            raise ValueError("At least one event change is required.")
        if self.title is not None and not self.title.strip():
            raise ValueError("Event title cannot be empty.")


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
        created = InternalEvent(
            id=uuid4(),
            user_id=user_id,
            details=EventDetails(
                title=event.title.strip(),
                description=event.description.strip(),
                interval=event.schedule.to_interval(),
                status=EventStatus.SCHEDULED,
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
                interval=(
                    changes.schedule.to_interval()
                    if changes.schedule is not None
                    else current.details.interval
                ),
            ),
            timestamps=replace(current.timestamps, updated_at=self._now()),
        )
        return await self.repository.update(user_id=user_id, event=updated)

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
            deleted_at=self._now(),
        )

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Event service clock must return a timezone-aware time.")
        return now.astimezone(timezone.utc)
