from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar
from uuid import UUID

import asyncpg

from harle_domain.accounts.models import (
    ExternalIdentity,
    Plan,
    ResolvedUser,
    SubscriptionPeriod,
    SubscriptionStatus,
    User,
)

RESOLVED_USER_COLUMNS = """
    users.id AS user_id,
    users.display_name AS user_display_name,
    users.plan_code,
    users.subscription_status,
    users.subscription_valid_until,
    users.subscription_synced_at,
    users.subscription_period_starts_at,
    users.subscription_period_ends_at,
    users.created_at AS user_created_at,
    users.updated_at AS user_updated_at,
    plans.monthly_request_limit,
    plans.monthly_notification_limit,
    plans.active AS plan_active,
    plans.created_at AS plan_created_at,
    plans.updated_at AS plan_updated_at,
    identities.id AS identity_id,
    identities.user_id AS identity_user_id,
    identities.provider,
    identities.external_user_id,
    identities.display_name AS identity_display_name,
    identities.created_at AS identity_created_at,
    identities.updated_at AS identity_updated_at
"""
FieldT = TypeVar("FieldT")


@dataclass(frozen=True, slots=True)
class PostgresAccountRepository:
    pool: asyncpg.Pool

    async def resolve_telegram_identity(
        self,
        *,
        telegram_user_id: int,
    ) -> ResolvedUser | None:
        if telegram_user_id <= 0:
            raise ValueError("Telegram user identifier must be positive.")

        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                SELECT {RESOLVED_USER_COLUMNS}
                FROM external_identities AS identities
                JOIN users ON users.id = identities.user_id
                JOIN plans ON plans.code = users.plan_code
                WHERE identities.provider = 'telegram'
                    AND identities.external_user_id = $1
                """,
                str(telegram_user_id),
            )

        if row is None:
            return None

        return _resolved_user_from_row(row)

    async def resolve_user_telegram_identity(
        self,
        *,
        user_id: UUID,
    ) -> ResolvedUser | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                SELECT {RESOLVED_USER_COLUMNS}
                FROM external_identities AS identities
                JOIN users ON users.id = identities.user_id
                JOIN plans ON plans.code = users.plan_code
                WHERE identities.provider = 'telegram'
                    AND users.id = $1
                ORDER BY identities.created_at, identities.id
                LIMIT 1
                """,
                user_id,
            )
        return _resolved_user_from_row(row) if row is not None else None


def _resolved_user_from_row(row: asyncpg.Record) -> ResolvedUser:
    user_id = _required(row, "user_id", UUID)
    return ResolvedUser(
        user=User(
            id=user_id,
            display_name=_required(row, "user_display_name", str),
            plan_code=_required(row, "plan_code", str),
            subscription_status=SubscriptionStatus(
                _required(row, "subscription_status", str),
            ),
            subscription_valid_until=_optional_datetime(
                row,
                "subscription_valid_until",
            ),
            subscription_synced_at=_optional_datetime(
                row,
                "subscription_synced_at",
            ),
            subscription_period=_optional_subscription_period(row),
            created_at=_required(row, "user_created_at", datetime),
            updated_at=_required(row, "user_updated_at", datetime),
        ),
        plan=Plan(
            code=_required(row, "plan_code", str),
            monthly_request_limit=_required(
                row,
                "monthly_request_limit",
                int,
            ),
            monthly_notification_limit=_required(
                row,
                "monthly_notification_limit",
                int,
            ),
            active=_required(row, "plan_active", bool),
            created_at=_required(row, "plan_created_at", datetime),
            updated_at=_required(row, "plan_updated_at", datetime),
        ),
        identity=ExternalIdentity(
            id=_required(row, "identity_id", UUID),
            user_id=_required(row, "identity_user_id", UUID),
            provider=_required(row, "provider", str),
            external_user_id=_required(row, "external_user_id", str),
            display_name=_required(row, "identity_display_name", str),
            created_at=_required(row, "identity_created_at", datetime),
            updated_at=_required(row, "identity_updated_at", datetime),
        ),
    )


def _required(
    row: asyncpg.Record,
    key: str,
    expected: type[FieldT],
) -> FieldT:
    value: object = row[key]
    if not isinstance(value, expected):
        raise TypeError(f"Unexpected {key} value.")
    return value


def _optional_datetime(
    row: asyncpg.Record,
    key: str,
) -> datetime | None:
    value: object = row[key]
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"Expected {key} to be a datetime or null.")
    return value


def _optional_subscription_period(
    row: asyncpg.Record,
) -> SubscriptionPeriod | None:
    starts_at = _optional_datetime(row, "subscription_period_starts_at")
    ends_at = _optional_datetime(row, "subscription_period_ends_at")
    if starts_at is None and ends_at is None:
        return None
    if starts_at is None or ends_at is None:
        raise TypeError("Subscription period boundaries must be supplied together.")
    return SubscriptionPeriod(starts_at, ends_at)
