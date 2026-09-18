import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg

from harle_domain.events import (
    EventDetails,
    EventInterval,
    EventNotification,
    EventStatus,
    EventTimestamps,
    EventType,
    InternalEvent,
    MonthlyRecurrence,
    RecurrenceRule,
    WeekDay,
    WeeklyRecurrence,
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
    event_type,
    status,
    notification_window_start,
    last_notified_at,
    recurrence_rule,
    created_at,
    updated_at
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
        if event.status is not EventStatus.ACTIVE:
            raise ValueError("A new event must be active.")
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
                    event_type,
                    status,
                    notification_window_start,
                    last_notified_at,
                    recurrence_rule,
                    created_at,
                    updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7,
                    $8, $9, $10, $11, $12, $13::jsonb, $14, $15
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
                event.event_type.value,
                event.status.value,
                event.notification_window_start,
                event.last_notified_at,
                _recurrence_json(event.recurrence_rule),
                event.created_at,
                event.updated_at,
            )
        if row is None:
            raise RuntimeError("Could not create internal event.")
        return _event_from_row(row)

    async def get(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        include_disabled: bool = False,
    ) -> InternalEvent | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                SELECT {EVENT_COLUMNS}
                FROM internal_events
                WHERE id = $1
                    AND user_id = $2
                    AND (
                        status = 'active'
                        OR ($3 AND status = 'disabled')
                    )
                """,
                event_id,
                user_id,
                include_disabled,
            )
        return _event_from_row(row) if row is not None else None

    async def list_for_range(
        self,
        *,
        user_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        include_disabled: bool = False,
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
                    AND (
                        recurrence_rule IS NOT NULL
                        OR ends_at > $2
                    )
                    AND (
                        status = 'active'
                        OR ($4 AND status = 'disabled')
                    )
                ORDER BY starts_at, ends_at, id
                """,
                user_id,
                starts_at,
                ends_at,
                include_disabled,
            )
        return [_event_from_row(row) for row in rows]

    async def list_due_for_notification(
        self,
        *,
        current_time: datetime,
        limit: int,
    ) -> Sequence[InternalEvent]:
        if current_time.tzinfo is None or current_time.utcoffset() is None:
            raise ValueError("Current time must include a timezone.")
        if limit <= 0:
            raise ValueError("Due event limit must be positive.")
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                f"""
                WITH one_time_due AS (
                    SELECT {EVENT_COLUMNS}
                    FROM internal_events
                    WHERE status = 'active'
                        AND recurrence_rule IS NULL
                        AND last_notified_at IS NULL
                        AND notification_window_start <= $1
                        AND ends_at > $1
                    ORDER BY notification_window_start, starts_at, id
                    LIMIT $2
                )
                SELECT {EVENT_COLUMNS}
                FROM internal_events
                WHERE status = 'active'
                    AND recurrence_rule IS NOT NULL
                UNION ALL
                SELECT {EVENT_COLUMNS}
                FROM one_time_due
                ORDER BY notification_window_start, starts_at, id
                """,
                current_time,
                limit,
            )
        return [_event_from_row(row) for row in rows]

    async def update(
        self,
        *,
        user_id: UUID,
        event: InternalEvent,
    ) -> InternalEvent | None:
        _require_event_owner(user_id, event)
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
                    event_type = $9,
                    notification_window_start = $10,
                    last_notified_at = $11,
                    recurrence_rule = $12::jsonb,
                    updated_at = $13
                WHERE id = $1
                    AND user_id = $2
                    AND status IN ('active', 'disabled')
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
                event.event_type.value,
                event.notification_window_start,
                event.last_notified_at,
                _recurrence_json(event.recurrence_rule),
                event.updated_at,
            )
        return _event_from_row(row) if row is not None else None

    async def mark_notification_delivered(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        expected_updated_at: datetime,
        updated_at: datetime,
    ) -> InternalEvent | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                UPDATE internal_events
                SET last_notified_at = $4,
                    updated_at = $4
                WHERE id = $1
                    AND user_id = $2
                    AND status = 'active'
                    AND updated_at = $3
                RETURNING {EVENT_COLUMNS}
                """,
                event_id,
                user_id,
                expected_updated_at,
                updated_at,
            )
        return _event_from_row(row) if row is not None else None

    async def disable(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        updated_at: datetime,
    ) -> InternalEvent | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                UPDATE internal_events
                SET status = 'disabled',
                    updated_at = $3
                WHERE id = $1
                    AND user_id = $2
                    AND status = 'active'
                RETURNING {EVENT_COLUMNS}
                """,
                event_id,
                user_id,
                updated_at,
            )
        return _event_from_row(row) if row is not None else None

    async def enable(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        updated_at: datetime,
    ) -> InternalEvent | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                UPDATE internal_events
                SET status = 'active',
                    updated_at = $3
                WHERE id = $1
                    AND user_id = $2
                    AND status = 'disabled'
                RETURNING {EVENT_COLUMNS}
                """,
                event_id,
                user_id,
                updated_at,
            )
        return _event_from_row(row) if row is not None else None

    async def delete(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
    ) -> InternalEvent | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                DELETE FROM internal_events
                WHERE id = $1
                    AND user_id = $2
                    AND status IN ('active', 'disabled')
                RETURNING {EVENT_COLUMNS}
                """,
                event_id,
                user_id,
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
            event_type=EventType(_text(row, "event_type")),
            status=EventStatus(_text(row, "status")),
        ),
        notification=EventNotification(
            window_start=_datetime(row, "notification_window_start"),
            last_notified_at=_optional_datetime(row, "last_notified_at"),
        ),
        timestamps=EventTimestamps(
            created_at=_datetime(row, "created_at"),
            updated_at=_datetime(row, "updated_at"),
        ),
        recurrence_rule=_recurrence_rule(row["recurrence_rule"]),
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


def _recurrence_json(rule: RecurrenceRule | None) -> str | None:
    if isinstance(rule, WeeklyRecurrence):
        return json.dumps(
            {"week_days": sorted(day.value for day in rule.days)},
        )
    if isinstance(rule, MonthlyRecurrence):
        return json.dumps({"month_days": sorted(rule.days)})
    if rule is None:
        return None
    raise TypeError("Unknown recurrence rule.")


def _recurrence_rule(value: object) -> RecurrenceRule | None:
    if value is None:
        return None
    decoded: object = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, Mapping):
        raise TypeError("Expected recurrence_rule to be a JSON object.")
    week_days = decoded.get("week_days")
    month_days = decoded.get("month_days")
    if isinstance(week_days, list) and month_days is None:
        if not all(isinstance(day, str) for day in week_days):
            raise TypeError("Expected recurrence weekdays to be text.")
        return WeeklyRecurrence(frozenset(WeekDay(day) for day in week_days))
    if isinstance(month_days, list) and week_days is None:
        if not all(isinstance(day, int) for day in month_days):
            raise TypeError("Expected recurrence month days to be integers.")
        return MonthlyRecurrence(frozenset(month_days))
    raise ValueError("Recurrence rule must contain week_days or month_days.")


def _boolean(row: asyncpg.Record, key: str) -> bool:
    value: object = row[key]
    if not isinstance(value, bool):
        raise TypeError(f"Expected {key} to be a boolean.")
    return value
