from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class EventStatus(str, Enum):
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class EventInterval:
    starts_at: datetime
    ends_at: datetime
    timezone: str
    all_day: bool

    def __post_init__(self) -> None:
        try:
            timezone = ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone: {self.timezone}.") from exc
        _require_utc(self.starts_at, "Event start")
        _require_utc(self.ends_at, "Event end")
        if self.ends_at <= self.starts_at:
            raise ValueError("Event end must be after its start.")
        if self.all_day:
            local_start = self.starts_at.astimezone(timezone)
            local_end = self.ends_at.astimezone(timezone)
            if local_start.time() != time.min or local_end.time() != time.min:
                raise ValueError("All-day events must use local midnight boundaries.")


@dataclass(frozen=True, slots=True)
class EventDetails:
    title: str
    description: str
    interval: EventInterval
    status: EventStatus

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Event title cannot be empty.")


@dataclass(frozen=True, slots=True)
class EventTimestamps:
    created_at: datetime
    updated_at: datetime
    cancelled_at: datetime | None = None
    deleted_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "Event creation time")
        _require_aware(self.updated_at, "Event update time")
        if self.cancelled_at is not None:
            _require_aware(self.cancelled_at, "Event cancellation time")
        if self.deleted_at is not None:
            _require_aware(self.deleted_at, "Event deletion time")


@dataclass(frozen=True, slots=True)
class InternalEvent:
    id: UUID
    user_id: UUID
    details: EventDetails
    timestamps: EventTimestamps

    def __post_init__(self) -> None:
        if self.status is EventStatus.SCHEDULED and (
            self.cancelled_at is not None or self.deleted_at is not None
        ):
            raise ValueError("A scheduled event cannot be cancelled or deleted.")
        if self.status is EventStatus.CANCELLED and (
            self.cancelled_at is None or self.deleted_at is not None
        ):
            raise ValueError("A cancelled event requires only a cancellation time.")
        if self.status is EventStatus.DELETED and self.deleted_at is None:
            raise ValueError("A deleted event requires a deletion time.")

    @property
    def title(self) -> str:
        return self.details.title

    @property
    def description(self) -> str:
        return self.details.description

    @property
    def starts_at(self) -> datetime:
        return self.details.interval.starts_at

    @property
    def ends_at(self) -> datetime:
        return self.details.interval.ends_at

    @property
    def timezone(self) -> str:
        return self.details.interval.timezone

    @property
    def all_day(self) -> bool:
        return self.details.interval.all_day

    @property
    def status(self) -> EventStatus:
        return self.details.status

    @property
    def created_at(self) -> datetime:
        return self.timestamps.created_at

    @property
    def updated_at(self) -> datetime:
        return self.timestamps.updated_at

    @property
    def cancelled_at(self) -> datetime | None:
        return self.timestamps.cancelled_at

    @property
    def deleted_at(self) -> datetime | None:
        return self.timestamps.deleted_at


def _require_utc(value: datetime, label: str) -> None:
    _require_aware(value, label)
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be stored in UTC.")


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone.")
