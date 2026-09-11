from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg

from harle_domain.accounts.models import (
    ExternalIdentity,
    Plan,
    ResolvedUser,
    SubscriptionStatus,
    User,
)


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
                """
                SELECT
                    users.id AS user_id,
                    users.display_name AS user_display_name,
                    users.plan_code,
                    users.subscription_status,
                    users.subscription_valid_until,
                    users.subscription_synced_at,
                    users.created_at AS user_created_at,
                    users.updated_at AS user_updated_at,
                    plans.monthly_request_limit,
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

        user_id = _uuid(row, "user_id")
        return ResolvedUser(
            user=User(
                id=user_id,
                display_name=_text(row, "user_display_name"),
                plan_code=_text(row, "plan_code"),
                subscription_status=SubscriptionStatus(
                    _text(row, "subscription_status"),
                ),
                subscription_valid_until=_optional_datetime(
                    row,
                    "subscription_valid_until",
                ),
                subscription_synced_at=_optional_datetime(
                    row,
                    "subscription_synced_at",
                ),
                created_at=_datetime(row, "user_created_at"),
                updated_at=_datetime(row, "user_updated_at"),
            ),
            plan=Plan(
                code=_text(row, "plan_code"),
                monthly_request_limit=_integer(
                    row,
                    "monthly_request_limit",
                ),
                active=_boolean(row, "plan_active"),
                created_at=_datetime(row, "plan_created_at"),
                updated_at=_datetime(row, "plan_updated_at"),
            ),
            identity=ExternalIdentity(
                id=_uuid(row, "identity_id"),
                user_id=_uuid(row, "identity_user_id"),
                provider=_text(row, "provider"),
                external_user_id=_text(row, "external_user_id"),
                display_name=_text(row, "identity_display_name"),
                created_at=_datetime(row, "identity_created_at"),
                updated_at=_datetime(row, "identity_updated_at"),
            ),
        )


def _text(row: asyncpg.Record, key: str) -> str:
    value: object = row[key]
    if not isinstance(value, str):
        raise TypeError(f"Expected {key} to be text.")
    return value


def _uuid(row: asyncpg.Record, key: str) -> UUID:
    value: object = row[key]
    if not isinstance(value, UUID):
        raise TypeError(f"Expected {key} to be a UUID.")
    return value


def _datetime(row: asyncpg.Record, key: str) -> datetime:
    value: object = row[key]
    if not isinstance(value, datetime):
        raise TypeError(f"Expected {key} to be a datetime.")
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


def _integer(row: asyncpg.Record, key: str) -> int:
    value: object = row[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"Expected {key} to be an integer.")
    return value


def _boolean(row: asyncpg.Record, key: str) -> bool:
    value: object = row[key]
    if not isinstance(value, bool):
        raise TypeError(f"Expected {key} to be a boolean.")
    return value
