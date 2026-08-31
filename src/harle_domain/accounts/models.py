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


@dataclass(frozen=True, slots=True)
class User(TimestampedRecord):
    id: UUID
    display_name: str
    plan_code: str
    subscription_status: SubscriptionStatus
    subscription_valid_until: datetime | None
    subscription_synced_at: datetime | None


@dataclass(frozen=True, slots=True)
class ExternalIdentity(TimestampedRecord):
    id: UUID
    user_id: UUID
    provider: str
    external_user_id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class ResolvedUser:
    user: User
    plan: Plan
    identity: ExternalIdentity
