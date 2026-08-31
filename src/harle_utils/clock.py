from collections.abc import Callable
from datetime import datetime, timezone

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Clock values must include a timezone.")
    return value.astimezone(timezone.utc)
