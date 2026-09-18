from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import asyncpg

from harle_domain.events import EventNotificationOccurrence


@dataclass(frozen=True, slots=True)
class PostgresEventNotificationUsageRepository:
    pool: asyncpg.Pool

    async def count_deliveries(
        self,
        *,
        user_id: UUID,
        delivered_from: datetime,
        delivered_before: datetime,
    ) -> int:
        _require_utc_period(delivered_from, delivered_before)
        async with self.pool.acquire() as connection:
            count = await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM event_notification_deliveries
                WHERE user_id = $1
                    AND delivered_at >= $2
                    AND delivered_at < $3
                """,
                user_id,
                delivered_from,
                delivered_before,
            )
        if isinstance(count, bool) or not isinstance(count, int):
            raise TypeError("Expected notification delivery count to be an integer.")
        return count

    async def was_delivered(
        self,
        *,
        occurrence: EventNotificationOccurrence,
    ) -> bool:
        async with self.pool.acquire() as connection:
            exists = await connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM event_notification_deliveries
                    WHERE user_id = $1
                        AND event_id = $2
                        AND occurrence_starts_at = $3
                        AND notification_window_start = $4
                )
                """,
                occurrence.user_id,
                occurrence.event_id,
                occurrence.starts_at,
                occurrence.window_start,
            )
        if not isinstance(exists, bool):
            raise TypeError("Expected notification delivery lookup to be boolean.")
        return exists

    async def record_delivery(
        self,
        *,
        occurrence: EventNotificationOccurrence,
        delivered_at: datetime,
    ) -> bool:
        _require_utc(delivered_at, "Notification delivery time")
        async with self.pool.acquire() as connection:
            identifier = await connection.fetchval(
                """
                INSERT INTO event_notification_deliveries (
                    user_id,
                    event_id,
                    occurrence_starts_at,
                    notification_window_start,
                    delivered_at
                )
                SELECT $1, $2, $3, $4, $5
                WHERE EXISTS (
                    SELECT 1
                    FROM internal_events
                    WHERE id = $2
                        AND user_id = $1
                )
                ON CONFLICT ON CONSTRAINT
                    event_notification_delivery_occurrence_key
                DO NOTHING
                RETURNING id
                """,
                occurrence.user_id,
                occurrence.event_id,
                occurrence.starts_at,
                occurrence.window_start,
                delivered_at,
            )
        return identifier is not None

    async def claim_quota_notice(
        self,
        *,
        user_id: UUID,
        period_starts_at: datetime,
        attempted_at: datetime,
    ) -> bool:
        _require_utc(period_starts_at, "Quota period start")
        _require_utc(attempted_at, "Quota notice attempt time")
        async with self.pool.acquire() as connection:
            claimed = await connection.fetchval(
                """
                INSERT INTO event_notification_quota_notices (
                    user_id,
                    period_starts_at,
                    status,
                    attempted_at
                )
                VALUES ($1, $2, 'attempted', $3)
                ON CONFLICT (user_id, period_starts_at) DO NOTHING
                RETURNING TRUE
                """,
                user_id,
                period_starts_at,
                attempted_at,
            )
        return claimed is True

    async def mark_quota_notice_delivered(
        self,
        *,
        user_id: UUID,
        period_starts_at: datetime,
        delivered_at: datetime,
    ) -> None:
        _require_utc(period_starts_at, "Quota period start")
        _require_utc(delivered_at, "Quota notice delivery time")
        async with self.pool.acquire() as connection:
            status = await connection.execute(
                """
                UPDATE event_notification_quota_notices
                SET status = 'delivered',
                    delivered_at = $3
                WHERE user_id = $1
                    AND period_starts_at = $2
                    AND status = 'attempted'
                """,
                user_id,
                period_starts_at,
                delivered_at,
            )
        if status != "UPDATE 1":
            raise RuntimeError("Could not mark quota notice as delivered.")


def _require_utc_period(starts_at: datetime, ends_at: datetime) -> None:
    _require_utc(starts_at, "Notification usage start")
    _require_utc(ends_at, "Notification usage end")
    if ends_at <= starts_at:
        raise ValueError("Notification usage end must follow its start.")


def _require_utc(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must use UTC.")
