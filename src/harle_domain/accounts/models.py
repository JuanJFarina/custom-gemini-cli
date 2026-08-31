from dataclasses import dataclass
from datetime import datetime
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
class Plan(TimestampedRecord):
    code: str
    monthly_request_limit: int
    active: bool

    def __post_init__(self) -> None:
        _require_non_empty(self.code, field_name="plan code")
        if self.monthly_request_limit <= 0:
            raise ValueError("Monthly request limit must be positive.")


@dataclass(frozen=True, slots=True)
class User(TimestampedRecord):
    id: UUID
    display_name: str
    plan_code: str
    subscription_status: SubscriptionStatus
    subscription_valid_until: datetime | None
    subscription_synced_at: datetime | None

    def __post_init__(self) -> None:
        _require_non_empty(self.display_name, field_name="user display name")
        _require_non_empty(self.plan_code, field_name="user plan code")


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
