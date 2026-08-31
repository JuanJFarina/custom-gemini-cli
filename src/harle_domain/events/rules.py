from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import EventInterval


@dataclass(frozen=True, slots=True)
class EventRange:
    starts_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        if self.ends_at <= self.starts_at:
            raise ValueError("Event range end must be on or after its start date.")


def timed_event_interval(
    *,
    starts_at: datetime,
    ends_at: datetime,
    timezone_name: str,
) -> EventInterval:
    timezone_info = _timezone(timezone_name)
    return EventInterval(
        starts_at=_local_datetime_to_utc(starts_at, timezone_info),
        ends_at=_local_datetime_to_utc(ends_at, timezone_info),
        timezone=timezone_name,
        all_day=False,
    )


def all_day_event_interval(
    *,
    start_date: date,
    end_date: date,
    timezone_name: str,
) -> EventInterval:
    if end_date < start_date:
        raise ValueError("All-day event end date cannot precede its start date.")
    timezone_info = _timezone(timezone_name)
    return EventInterval(
        starts_at=_local_midnight(start_date, timezone_info),
        ends_at=_local_midnight(_following_day(end_date), timezone_info),
        timezone=timezone_name,
        all_day=True,
    )


def event_range(
    *,
    start_date: date,
    end_date: date,
    timezone_name: str,
) -> EventRange:
    if end_date < start_date:
        raise ValueError("Event range end date cannot precede its start date.")
    timezone_info = _timezone(timezone_name)
    return EventRange(
        starts_at=_local_midnight(start_date, timezone_info),
        ends_at=_local_midnight(_following_day(end_date), timezone_info),
    )


def _local_datetime_to_utc(
    value: datetime,
    timezone_info: ZoneInfo,
) -> datetime:
    if value.tzinfo is not None or value.utcoffset() is not None:
        raise ValueError("Event date-times must be local values without UTC offsets.")
    candidates = (
        value.replace(tzinfo=timezone_info, fold=0),
        value.replace(tzinfo=timezone_info, fold=1),
    )
    valid_utc_values = {
        candidate.astimezone(timezone.utc)
        for candidate in candidates
        if candidate.astimezone(timezone.utc)
        .astimezone(timezone_info)
        .replace(tzinfo=None)
        == value
    }
    if not valid_utc_values:
        raise ValueError("Event date-time does not exist in the selected timezone.")
    if len(valid_utc_values) > 1:
        raise ValueError("Event date-time is ambiguous in the selected timezone.")
    return valid_utc_values.pop()


def _local_midnight(value: date, timezone_info: ZoneInfo) -> datetime:
    return datetime.combine(value, time.min, timezone_info).astimezone(timezone.utc)


def _following_day(value: date) -> date:
    try:
        return value + timedelta(days=1)
    except OverflowError as exc:
        raise ValueError("Event date exceeds the supported range.") from exc


def _timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown IANA timezone: {timezone_name}.") from exc
