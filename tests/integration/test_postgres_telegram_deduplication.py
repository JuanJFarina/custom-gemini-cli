import asyncio
import os
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from harle_domain.tools import (
    InternalToolCallInteraction,
    ToolCall,
    ToolCallResult,
)
from harle_infrastructure.postgres import (
    PostgresConversationRepository,
    PostgresConversationStore,
    PostgresTelegramUpdateClaimRepository,
    create_postgres_pool,
    validate_postgres_schema,
)

DATABASE_URL = os.environ.get("TEST_POSTGRES_DATABASE_URL")
ROOT = Path(__file__).parents[2]
SCHEMA_PATHS = (
    ROOT / "scripts" / "apply_multi_user_runtime.sql",
    ROOT / "scripts" / "apply_internal_expenses.sql",
    ROOT / "scripts" / "apply_internal_events.sql",
    ROOT / "scripts" / "apply_telegram_dedup_ordering.sql",
)


async def verify_persistent_deduplication(database_url: str) -> None:
    user_id = uuid4()
    update_id = user_id.int % 8_000_000_000 + 1
    telegram_user_id = update_id + 1
    chat_id = update_id + 2
    connection = await asyncpg.connect(database_url)
    try:
        for schema_path in SCHEMA_PATHS:
            await connection.execute(schema_path.read_text(encoding="utf-8"))
        await connection.execute(
            """
            INSERT INTO users (
                id, name, display_name, plan_code,
                subscription_status, subscription_synced_at
            )
            VALUES ($1, 'Dedup User', 'Dedup User', 'free', 'active', NOW())
            """,
            user_id,
        )
    finally:
        await connection.close()

    pool = await create_postgres_pool(
        database_url=database_url,
        min_size=1,
        max_size=5,
    )
    try:
        claims = PostgresTelegramUpdateClaimRepository(pool)
        results = await asyncio.gather(
            *(
                claims.claim(
                    update_id=update_id,
                    telegram_user_id=telegram_user_id,
                    telegram_chat_id=chat_id,
                )
                for _ in range(5)
            ),
        )
        assert results.count(True) == 1
    finally:
        await pool.close()

    restarted_pool = await create_postgres_pool(
        database_url=database_url,
        min_size=1,
        max_size=2,
    )
    try:
        await validate_postgres_schema(restarted_pool)
        claims = PostgresTelegramUpdateClaimRepository(restarted_pool)
        assert not await claims.claim(
            update_id=update_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=chat_id,
        )

        conversations = PostgresConversationStore(
            repository=PostgresConversationRepository(restarted_pool),
            user_id=user_id,
            telegram_chat_id=chat_id,
            telegram_update_id=update_id,
        )
        interaction = InternalToolCallInteraction(
            tool_calls=[ToolCall(tool_name="list_events", tool_args={})],
            tool_results=[
                ToolCallResult(called_tool_name="list_events", result={"ok": True}),
            ],
        )
        for _ in range(2):
            await conversations.save_tool_call(
                interaction=interaction,
                interaction_index=0,
                model="fake",
            )
            await conversations.save(
                prompt="hello",
                response_text="hi",
                model="fake",
            )

        async with restarted_pool.acquire() as check:
            counts = await check.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE kind = 'conversation') AS conversations,
                    COUNT(*) FILTER (WHERE kind = 'tool_call') AS tool_calls
                FROM conversations
                WHERE telegram_update_id = $1
                """,
                update_id,
            )
        assert counts is not None
        assert counts["conversations"] == 1
        assert counts["tool_calls"] == 1
    finally:
        await restarted_pool.close()
        cleanup = await asyncpg.connect(database_url)
        try:
            await cleanup.execute(
                "DELETE FROM telegram_update_claims WHERE update_id = $1",
                update_id,
            )
            await cleanup.execute("DELETE FROM users WHERE id = $1", user_id)
        finally:
            await cleanup.close()


@pytest.mark.skipif(
    DATABASE_URL is None,
    reason="TEST_POSTGRES_DATABASE_URL is not configured",
)
def test_postgres_update_deduplication_survives_restart() -> None:
    assert DATABASE_URL is not None
    asyncio.run(verify_persistent_deduplication(DATABASE_URL))
