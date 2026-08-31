from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg

from harle_domain.events import (
    EventDetails,
    EventInterval,
    EventStatus,
    EventTimestamps,
    InternalEvent,
)

EVENT_COLUMNS = """
    id,
    user_id,
    title,
    description,
    starts_at,
    ends_at,
    timezone,
    all_day,
    status,
    created_at,
    updated_at,
    cancelled_at,
    deleted_at
"""


@dataclass(frozen=True, slots=True)
class PostgresEventRepository:
    pool: asyncpg.Pool

    async def create(
        self,
        *,
        user_id: UUID,
        event: InternalEvent,
    ) -> InternalEvent:
        _require_event_owner(user_id, event)
        if event.status is not EventStatus.SCHEDULED:
            raise ValueError("A new event must be scheduled.")
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                INSERT INTO internal_events (
                    id,
                    user_id,
                    title,
                    description,
                    starts_at,
                    ends_at,
                    timezone,
                    all_day,
                    status,
                    created_at,
                    updated_at,
                    cancelled_at,
                    deleted_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7,
                    $8, $9, $10, $11, $12, $13
                )
                RETURNING {EVENT_COLUMNS}
                """,
                event.id,
                event.user_id,
                event.title,
                event.description,
                event.starts_at,
                event.ends_at,
                event.timezone,
                event.all_day,
                event.status.value,
                event.created_at,
                event.updated_at,
                event.cancelled_at,
                event.deleted_at,
            )
        if row is None:
            raise RuntimeError("Could not create internal event.")
        return _event_from_row(row)

    async def get(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        include_cancelled: bool = False,
    ) -> InternalEvent | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                SELECT {EVENT_COLUMNS}
                FROM internal_events
                WHERE id = $1
                    AND user_id = $2
                    AND (
                        status = 'scheduled'
                        OR ($3 AND status = 'cancelled')
                    )
                """,
                event_id,
                user_id,
                include_cancelled,
            )
        return _event_from_row(row) if row is not None else None

    async def list_for_range(
        self,
        *,
        user_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        include_cancelled: bool = False,
    ) -> Sequence[InternalEvent]:
        if ends_at <= starts_at:
            raise ValueError("Event range end must be after its start.")
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT {EVENT_COLUMNS}
                FROM internal_events
                WHERE user_id = $1
                    AND starts_at < $3
                    AND ends_at > $2
                    AND (
                        status = 'scheduled'
                        OR ($4 AND status = 'cancelled')
                    )
                ORDER BY starts_at, ends_at, id
                """,
                user_id,
                starts_at,
                ends_at,
                include_cancelled,
            )
        return [_event_from_row(row) for row in rows]

    async def update(
        self,
        *,
        user_id: UUID,
        event: InternalEvent,
    ) -> InternalEvent | None:
        _require_event_owner(user_id, event)
        if event.status is not EventStatus.SCHEDULED:
            raise ValueError("Only scheduled events can be updated.")
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                UPDATE internal_events
                SET title = $3,
                    description = $4,
                    starts_at = $5,
                    ends_at = $6,
                    timezone = $7,
                    all_day = $8,
                    updated_at = $9
                WHERE id = $1
                    AND user_id = $2
                    AND status = 'scheduled'
                RETURNING {EVENT_COLUMNS}
                """,
                event.id,
                user_id,
                event.title,
                event.description,
                event.starts_at,
                event.ends_at,
                event.timezone,
                event.all_day,
                event.updated_at,
            )
        return _event_from_row(row) if row is not None else None

    async def cancel(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        cancelled_at: datetime,
    ) -> InternalEvent | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                UPDATE internal_events
                SET status = 'cancelled',
                    updated_at = $3,
                    cancelled_at = $3
                WHERE id = $1
                    AND user_id = $2
                    AND status = 'scheduled'
                RETURNING {EVENT_COLUMNS}
                """,
                event_id,
                user_id,
                cancelled_at,
            )
        return _event_from_row(row) if row is not None else None

    async def delete(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        deleted_at: datetime,
    ) -> InternalEvent | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                UPDATE internal_events
                SET status = 'deleted',
                    updated_at = $3,
                    deleted_at = $3
                WHERE id = $1
                    AND user_id = $2
                    AND status IN ('scheduled', 'cancelled')
                RETURNING {EVENT_COLUMNS}
                """,
                event_id,
                user_id,
                deleted_at,
            )
        return _event_from_row(row) if row is not None else None


def _event_from_row(row: asyncpg.Record) -> InternalEvent:
    return InternalEvent(
        id=_uuid(row, "id"),
        user_id=_uuid(row, "user_id"),
        details=EventDetails(
            title=_text(row, "title"),
            description=_text(row, "description"),
            interval=EventInterval(
                starts_at=_datetime(row, "starts_at"),
                ends_at=_datetime(row, "ends_at"),
                timezone=_text(row, "timezone"),
                all_day=_boolean(row, "all_day"),
            ),
            status=EventStatus(_text(row, "status")),
        ),
        timestamps=EventTimestamps(
            created_at=_datetime(row, "created_at"),
            updated_at=_datetime(row, "updated_at"),
            cancelled_at=_optional_datetime(row, "cancelled_at"),
            deleted_at=_optional_datetime(row, "deleted_at"),
        ),
    )


def _require_event_owner(user_id: UUID, event: InternalEvent) -> None:
    if event.user_id != user_id:
        raise ValueError("Event owner does not match user identifier.")


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


def _optional_datetime(row: asyncpg.Record, key: str) -> datetime | None:
    value: object = row[key]
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"Expected {key} to be a datetime or null.")
    return value


def _boolean(row: asyncpg.Record, key: str) -> bool:
    value: object = row[key]
    if not isinstance(value, bool):
        raise TypeError(f"Expected {key} to be a boolean.")
    return value
