import asyncio
import os
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest

from harle_domain.events import EventStatus
from harle_infrastructure.postgres import (
    PostgresEventRepository,
    create_postgres_pool,
)
from harle_services.events import (
    CreateEvent,
    EventQuery,
    EventService,
    TimedEventSchedule,
    UpdateEvent,
)

DATABASE_URL = os.environ.get("TEST_POSTGRES_DATABASE_URL")
ROOT = Path(__file__).parents[2]
SCHEMA_PATHS = (
    ROOT / "scripts" / "apply_multi_user_runtime.sql",
    ROOT / "scripts" / "apply_internal_events.sql",
)
NOW = datetime(2026, 8, 31, 12, tzinfo=timezone.utc)


async def _insert_user(
    connection: asyncpg.Connection,
    user_id: UUID,
    name: str,
) -> None:
    await connection.execute(
        """
        INSERT INTO users (
            id, name, display_name, plan_code,
            subscription_status, subscription_synced_at
        )
        VALUES ($1, $2, $2, 'free', 'active', NOW())
        """,
        user_id,
        name,
    )


async def verify_event_isolation(database_url: str) -> None:
    first_id = uuid4()
    second_id = uuid4()
    connection = await asyncpg.connect(database_url)
    try:
        for schema_path in SCHEMA_PATHS:
            await connection.execute(schema_path.read_text(encoding="utf-8"))
        await _insert_user(connection, first_id, "First Event User")
        await _insert_user(connection, second_id, "Second Event User")
    finally:
        await connection.close()

    pool = await create_postgres_pool(
        database_url=database_url,
        min_size=1,
        max_size=2,
    )
    try:
        service = EventService(
            PostgresEventRepository(pool),
            clock=lambda: NOW,
        )
        first = await service.create(
            user_id=first_id,
            event=CreateEvent(
                title="First event",
                description="Private",
                schedule=TimedEventSchedule(
                    starts_at=datetime(2026, 9, 1, 10),
                    ends_at=datetime(2026, 9, 1, 11),
                    timezone_name="UTC",
                ),
            ),
        )
        await service.create(
            user_id=second_id,
            event=CreateEvent(
                title="Second event",
                description="Private",
                schedule=TimedEventSchedule(
                    starts_at=datetime(2026, 9, 1, 12),
                    ends_at=datetime(2026, 9, 1, 13),
                    timezone_name="UTC",
                ),
            ),
        )

        first_events = await service.list_for_range(
            user_id=first_id,
            query=EventQuery(
                start_date=date(2026, 9, 1),
                end_date=date(2026, 9, 1),
                timezone_name="UTC",
            ),
        )
        second_events = await service.list_for_range(
            user_id=second_id,
            query=EventQuery(
                start_date=date(2026, 9, 1),
                end_date=date(2026, 9, 1),
                timezone_name="UTC",
            ),
        )
        assert {event.user_id for event in first_events} == {first_id}
        assert {event.user_id for event in second_events} == {second_id}

        assert await service.update(
            user_id=second_id,
            event_id=first.id,
            changes=UpdateEvent(title="Denied"),
        ) is None
        assert await service.cancel(user_id=second_id, event_id=first.id) is None
        assert await service.delete(user_id=second_id, event_id=first.id) is None

        updated = await service.update(
            user_id=first_id,
            event_id=first.id,
            changes=UpdateEvent(title="Updated first event"),
        )
        assert updated is not None
        assert updated.title == "Updated first event"
        cancelled = await service.cancel(user_id=first_id, event_id=first.id)
        assert cancelled is not None
        assert cancelled.status is EventStatus.CANCELLED
        deleted = await service.delete(user_id=first_id, event_id=first.id)
        assert deleted is not None
        assert deleted.status is EventStatus.DELETED
        assert not await service.list_for_range(
            user_id=first_id,
            query=EventQuery(
                start_date=date(2026, 9, 1),
                end_date=date(2026, 9, 1),
                timezone_name="UTC",
                include_cancelled=True,
            ),
        )
    finally:
        await pool.close()
        cleanup = await asyncpg.connect(database_url)
        try:
            await cleanup.execute(
                "DELETE FROM users WHERE id = ANY($1::uuid[])",
                [first_id, second_id],
            )
        finally:
            await cleanup.close()


@pytest.mark.skipif(
    DATABASE_URL is None,
    reason="TEST_POSTGRES_DATABASE_URL is not configured",
)
def test_postgres_event_isolation_and_lifecycle() -> None:
    assert DATABASE_URL is not None
    asyncio.run(verify_event_isolation(DATABASE_URL))
