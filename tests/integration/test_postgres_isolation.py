import asyncio
import os
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from harle_infrastructure.postgres import (
    PostgresAccountRepository,
    PostgresAssistantProfileRepository,
    PostgresConversationRepository,
    PostgresConversationStore,
    PostgresUserProfileRepository,
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


async def verify_isolation(database_url: str) -> None:
    first_id = uuid4()
    second_id = uuid4()
    first_telegram_id = first_id.int % 8_000_000_000 + 1
    second_telegram_id = second_id.int % 8_000_000_000 + 1
    connection = await asyncpg.connect(database_url)
    try:
        for schema_path in SCHEMA_PATHS:
            await connection.execute(schema_path.read_text(encoding="utf-8"))
        for user_id, telegram_id, name in (
            (first_id, first_telegram_id, "First"),
            (second_id, second_telegram_id, "Second"),
        ):
            await connection.execute(
                """
                INSERT INTO users (
                    id, name, telegram_id, display_name, plan_code,
                    subscription_status, subscription_synced_at
                )
                VALUES ($1, $2, $3, $2, 'free', 'active', NOW())
                """,
                user_id,
                name,
                telegram_id,
            )
            await connection.execute(
                """
                INSERT INTO external_identities (
                    user_id, provider, external_user_id, display_name
                )
                VALUES ($1, 'telegram', $2, $3)
                """,
                user_id,
                str(telegram_id),
                name,
            )
            await connection.execute(
                """
                INSERT INTO user_profiles (
                    user_id, preferred_name, locale, timezone, personal_history
                )
                VALUES ($1, $2, 'en-US', 'UTC', $3)
                """,
                user_id,
                name,
                f"{name} history",
            )
            await connection.execute(
                """
                INSERT INTO assistant_profiles (user_id, display_name, profile_text)
                VALUES ($1, 'Harle', $2)
                """,
                user_id,
                f"Assistant for {name}",
            )
    finally:
        await connection.close()

    pool = await create_postgres_pool(
        database_url=database_url,
        min_size=1,
        max_size=2,
    )
    try:
        await validate_postgres_schema(pool)
        accounts = PostgresAccountRepository(pool)
        first_user = await accounts.resolve_telegram_identity(
            telegram_user_id=first_telegram_id,
        )
        second_user = await accounts.resolve_telegram_identity(
            telegram_user_id=second_telegram_id,
        )
        assert first_user is not None and first_user.user.id == first_id
        assert second_user is not None and second_user.user.id == second_id

        user_profiles = PostgresUserProfileRepository(pool)
        assistant_profiles = PostgresAssistantProfileRepository(pool)
        first_profile = await user_profiles.get(user_id=first_id)
        second_assistant = await assistant_profiles.get(user_id=second_id)
        assert first_profile is not None
        assert second_assistant is not None
        assert first_profile.personal_history == "First history"
        assert second_assistant.profile_text == "Assistant for Second"

        conversations = PostgresConversationRepository(pool)
        first_store = PostgresConversationStore(conversations, first_id, 10)
        second_store = PostgresConversationStore(conversations, second_id, 20)
        await first_store.save(prompt="first prompt", response_text="one", model="fake")
        await second_store.save(
            prompt="second prompt",
            response_text="two",
            model="fake",
        )
        first_context = await first_store.load()
        second_context = await second_store.load()
        assert "first prompt" in first_context and "second prompt" not in first_context
        assert (
            "second prompt" in second_context and "first prompt" not in second_context
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
def test_postgres_accounts_profiles_and_conversations_are_isolated() -> None:
    assert DATABASE_URL is not None
    asyncio.run(verify_isolation(DATABASE_URL))
