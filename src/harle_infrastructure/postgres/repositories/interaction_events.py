from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar
from uuid import UUID

import asyncpg

from harle_domain.events import (
    EventStatus,
    InteractionEvent,
    InteractionEventCandidate,
)
from harle_domain.profiles import InteractionFrequency

INTERACTION_EVENT_COLUMNS = """
    id,
    user_id,
    status,
    last_user_message_at,
    last_agent_message_at,
    created_at,
    updated_at
"""
FieldT = TypeVar("FieldT")


@dataclass(frozen=True, slots=True)
class PostgresInteractionEventRepository:
    pool: asyncpg.Pool

    async def get_for_user(
        self,
        *,
        user_id: UUID,
    ) -> InteractionEvent | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                SELECT {INTERACTION_EVENT_COLUMNS}
                FROM interaction_events
                WHERE user_id = $1
                """,
                user_id,
            )
        return _event_from_row(row) if row is not None else None

    async def list_active(
        self,
        *,
        limit: int,
        user_message_from: datetime,
        current_time: datetime,
    ) -> Sequence[InteractionEventCandidate]:
        if limit <= 0:
            raise ValueError("Interaction event limit must be positive.")
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT
                    interactions.id,
                    interactions.user_id,
                    interactions.status,
                    interactions.last_user_message_at,
                    interactions.last_agent_message_at,
                    interactions.created_at,
                    interactions.updated_at,
                    profiles.interaction_frequency
                FROM interaction_events AS interactions
                JOIN users AS owners
                    ON owners.id = interactions.user_id
                JOIN plans
                    ON plans.code = owners.plan_code
                JOIN assistant_profiles AS profiles
                    ON profiles.user_id = interactions.user_id
                WHERE interactions.status = 'active'
                    AND interactions.last_user_message_at >= $2
                    AND owners.subscription_status = 'active'
                    AND (
                        owners.subscription_valid_until IS NULL
                        OR owners.subscription_valid_until > $3
                    )
                    AND owners.subscription_period_starts_at <= $3
                    AND owners.subscription_period_ends_at > $3
                    AND plans.active
                ORDER BY GREATEST(
                    interactions.last_user_message_at,
                    COALESCE(
                        interactions.last_agent_message_at,
                        interactions.last_user_message_at
                    )
                ), interactions.id
                LIMIT $1
                """,
                limit,
                user_message_from,
                current_time,
            )
        return [
            InteractionEventCandidate(
                event=_event_from_row(row),
                interaction_frequency=InteractionFrequency(
                    _required(row, "interaction_frequency", str),
                ),
            )
            for row in rows
        ]

    async def disable(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        updated_at: datetime,
    ) -> InteractionEvent | None:
        return await self._set_status(
            user_id=user_id,
            event_id=event_id,
            new_status=EventStatus.DISABLED,
            updated_at=updated_at,
        )

    async def enable(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        updated_at: datetime,
    ) -> InteractionEvent | None:
        return await self._set_status(
            user_id=user_id,
            event_id=event_id,
            new_status=EventStatus.ACTIVE,
            updated_at=updated_at,
        )

    async def record_user_message(
        self,
        *,
        user_id: UUID,
        update_ids: Sequence[int],
    ) -> InteractionEvent | None:
        if not update_ids:
            raise ValueError("At least one update identifier is required.")
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                WITH activity AS (
                    SELECT MAX(claims.claimed_at) AS occurred_at
                    FROM telegram_update_claims AS claims
                    JOIN external_identities AS identities
                        ON identities.provider = 'telegram'
                        AND identities.external_user_id =
                            claims.telegram_user_id::TEXT
                    WHERE claims.update_id = ANY($2::bigint[])
                        AND identities.user_id = $1
                )
                UPDATE interaction_events
                SET last_user_message_at = CASE
                        WHEN last_user_message_at IS NULL
                            OR last_user_message_at < activity.occurred_at
                        THEN activity.occurred_at
                        ELSE last_user_message_at
                    END,
                    updated_at = GREATEST(updated_at, activity.occurred_at)
                FROM activity
                WHERE user_id = $1
                    AND activity.occurred_at IS NOT NULL
                RETURNING {INTERACTION_EVENT_COLUMNS}
                """,
                user_id,
                list(update_ids),
            )
        return _event_from_row(row) if row is not None else None

    async def record_agent_message(
        self,
        *,
        user_id: UUID,
        occurred_at: datetime,
    ) -> InteractionEvent | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                UPDATE interaction_events
                SET last_agent_message_at = CASE
                        WHEN last_agent_message_at IS NULL
                            OR last_agent_message_at < $2
                        THEN $2
                        ELSE last_agent_message_at
                    END,
                    updated_at = GREATEST(updated_at, $2)
                WHERE user_id = $1
                RETURNING {INTERACTION_EVENT_COLUMNS}
                """,
                user_id,
                occurred_at,
            )
        return _event_from_row(row) if row is not None else None

    async def _set_status(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        new_status: EventStatus,
        updated_at: datetime,
    ) -> InteractionEvent | None:
        current_status = (
            EventStatus.DISABLED
            if new_status is EventStatus.ACTIVE
            else EventStatus.ACTIVE
        )
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                UPDATE interaction_events
                SET status = $4,
                    updated_at = GREATEST(updated_at, $5)
                WHERE id = $1
                    AND user_id = $2
                    AND status = $3
                RETURNING {INTERACTION_EVENT_COLUMNS}
                """,
                event_id,
                user_id,
                current_status.value,
                new_status.value,
                updated_at,
            )
        return _event_from_row(row) if row is not None else None


def _event_from_row(row: asyncpg.Record) -> InteractionEvent:
    return InteractionEvent(
        id=_required(row, "id", UUID),
        user_id=_required(row, "user_id", UUID),
        status=EventStatus(_required(row, "status", str)),
        last_user_message_at=_optional_datetime(row, "last_user_message_at"),
        last_agent_message_at=_optional_datetime(row, "last_agent_message_at"),
        created_at=_required(row, "created_at", datetime),
        updated_at=_required(row, "updated_at", datetime),
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


def _optional_datetime(row: asyncpg.Record, key: str) -> datetime | None:
    value: object = row[key]
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"Expected {key} to be a datetime or null.")
    return value
