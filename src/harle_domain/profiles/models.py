from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class InteractionFrequency(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def scale(self) -> timedelta:
        if self is InteractionFrequency.HIGH:
            return timedelta(hours=12)
        if self is InteractionFrequency.MEDIUM:
            return timedelta(hours=24)
        return timedelta(hours=48)


@dataclass(frozen=True, slots=True)
class _ProfileRecord:
    user_id: UUID
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class UserProfile(_ProfileRecord):
    preferred_name: str
    locale: str
    timezone: str
    latitude: Decimal | None
    longitude: Decimal | None
    personal_history: str

    def __post_init__(self) -> None:
        _require_non_empty(
            self.preferred_name,
            field_name="preferred name",
        )
        _require_non_empty(self.locale, field_name="locale")
        _validate_timezone(self.timezone)
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be supplied together.")
        if self.latitude is not None and not Decimal("-90") <= self.latitude <= Decimal(
            "90",
        ):
            raise ValueError("Latitude must be between -90 and 90.")
        if self.longitude is not None and not Decimal(
            "-180",
        ) <= self.longitude <= Decimal("180"):
            raise ValueError("Longitude must be between -180 and 180.")


@dataclass(frozen=True, slots=True)
class AssistantProfile(_ProfileRecord):
    display_name: str
    profile_text: str
    interaction_frequency: InteractionFrequency = InteractionFrequency.HIGH

    def __post_init__(self) -> None:
        _require_non_empty(
            self.display_name,
            field_name="assistant display name",
        )
        _require_non_empty(self.profile_text, field_name="assistant profile")
        if not isinstance(self.interaction_frequency, InteractionFrequency):
            raise TypeError("Interaction frequency must be high, medium, or low.")


def _require_non_empty(value: str, *, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name.capitalize()} cannot be empty.")


def _validate_timezone(value: str) -> None:
    _require_non_empty(value, field_name="timezone")
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown IANA timezone: {value}.") from exc
