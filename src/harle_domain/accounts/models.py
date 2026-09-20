from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class TimestampedRecord:
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SubscriptionPeriod:
    starts_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        _require_utc(self.starts_at, field_name="subscription period start")
        _require_utc(self.ends_at, field_name="subscription period end")
        if self.ends_at <= self.starts_at:
            raise ValueError("Subscription period end must follow its start.")


@dataclass(frozen=True, slots=True)
class Plan(TimestampedRecord):
    code: str
    monthly_request_limit: int
    monthly_notification_limit: int
    active: bool

    def __post_init__(self) -> None:
        _require_non_empty(self.code, field_name="plan code")
        if min(self.monthly_request_limit, self.monthly_notification_limit) <= 0:
            raise ValueError("Monthly plan limits must be positive.")


@dataclass(frozen=True, slots=True)
class User(TimestampedRecord):
    id: UUID
    display_name: str
    plan_code: str
    subscription_status: SubscriptionStatus
    subscription_valid_until: datetime | None
    subscription_synced_at: datetime | None
    subscription_period: SubscriptionPeriod | None

    def __post_init__(self) -> None:
        _require_non_empty(self.display_name, field_name="user display name")
        _require_non_empty(self.plan_code, field_name="user plan code")

    def require_subscription_period(self) -> SubscriptionPeriod:
        if self.subscription_period is None:
            raise ValueError("Subscription period boundaries are required.")
        return self.subscription_period


@dataclass(frozen=True, slots=True)
class ExternalIdentity(TimestampedRecord):
    id: UUID
    user_id: UUID
    provider: str
    external_user_id: str
    display_name: str

    def __post_init__(self) -> None:
        _require_non_empty(self.provider, field_name="identity provider")
        _require_non_empty(
            self.external_user_id,
            field_name="external user identifier",
        )
        _require_non_empty(
            self.display_name,
            field_name="identity display name",
        )


@dataclass(frozen=True, slots=True)
class ResolvedUser:
    user: User
    plan: Plan
    identity: ExternalIdentity

    def __post_init__(self) -> None:
        if self.plan.code != self.user.plan_code:
            raise ValueError("Resolved plan does not match the user's plan.")
        if self.identity.user_id != self.user.id:
            raise ValueError("Resolved identity does not belong to the user.")


def _require_non_empty(value: str, *, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name.capitalize()} cannot be empty.")


def _require_utc(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name.capitalize()} must use UTC.")
