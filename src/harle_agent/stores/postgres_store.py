import json
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from harle_agent.models import ConversationRecord, HarleToolInteraction
from harle_agent.settings import get_agent_settings

TOKENS_CAP = get_agent_settings().MAX_CONVERSATION_TOKENS

NO_CONVERSATIONS_MESSAGE = "No conversations yet"


class PostgresConversationStore:
    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        user_id: UUID,
        user_name: str,
        telegram_chat_id: int,
    ) -> None:
        self.pool = pool
        self.user_id = user_id
        self.user_name = user_name
        self.telegram_chat_id = telegram_chat_id

    async def load(self, *, max_tokens: int = TOKENS_CAP) -> str:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT
                    prompt,
                    response,
                    created_at,
                    kind,
                    tool_call_response,
                    tool_result
                FROM conversations
                WHERE user_id = $1 AND telegram_chat_id = $2
                ORDER BY created_at DESC, id DESC
                LIMIT 50
                """,
                self.user_id,
                self.telegram_chat_id,
            )

        if not rows:
            return NO_CONVERSATIONS_MESSAGE

        conversations: list[str] = []
        context_length = 0
        for row in rows:
            conversation = _format_conversation_for_context(
                _record_from_row(row),
            )
            separator_length = 1 if conversations else 0
            next_context_length = context_length + separator_length + len(conversation)
            if (next_context_length / 4) > max_tokens:
                break

            conversations.append(conversation)
            context_length = next_context_length

        if not conversations:
            return NO_CONVERSATIONS_MESSAGE

        return "\n".join(reversed(conversations))

    async def save(self, *, prompt: str, response_text: str, model: str) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO conversations (
                    user_id,
                    telegram_chat_id,
                    prompt,
                    response,
                    model,
                    kind
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                self.user_id,
                self.telegram_chat_id,
                prompt,
                response_text,
                model,
                "conversation",
            )

    async def save_tool_call(
        self,
        *,
        interaction: HarleToolInteraction,
        model: str,
    ) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO conversations (
                    user_id,
                    telegram_chat_id,
                    prompt,
                    response,
                    model,
                    kind,
                    tool_call_response,
                    tool_result
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb)
                """,
                self.user_id,
                self.telegram_chat_id,
                "",
                "",
                model,
                "tool_call",
                json.dumps(interaction.tool_call.model_dump()),
                json.dumps(interaction.tool_result.model_dump()),
            )


async def setup_postgres_conversation_store(
    *,
    pool: asyncpg.Pool,
    telegram_user_id: int,
    user_name: str,
) -> UUID:
    async with pool.acquire() as connection:
        await _ensure_schema(connection)
        return await _ensure_owner_user(
            connection=connection,
            telegram_user_id=telegram_user_id,
            user_name=user_name,
        )


async def _ensure_schema(connection: asyncpg.Connection) -> None:
    await connection.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    await connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            telegram_id BIGINT UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
    )
    await connection.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id BIGSERIAL PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            telegram_chat_id BIGINT,
            prompt TEXT NOT NULL,
            response TEXT NOT NULL,
            model TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'conversation',
            tool_call_response JSONB,
            tool_result JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
    )
    await connection.execute(
        """
        ALTER TABLE conversations
        ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'conversation'
        """,
    )
    await connection.execute(
        """
        ALTER TABLE conversations
        ADD COLUMN IF NOT EXISTS tool_call_response JSONB
        """,
    )
    await connection.execute(
        """
        ALTER TABLE conversations
        ADD COLUMN IF NOT EXISTS tool_result JSONB
        """,
    )
    await connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conversations_chat_user_created_at
        ON conversations (user_id, telegram_chat_id, created_at DESC, id DESC)
        """,
    )


async def _ensure_owner_user(
    *,
    connection: asyncpg.Connection,
    telegram_user_id: int,
    user_name: str,
) -> UUID:
    row = await connection.fetchrow(
        """
        INSERT INTO users (name, telegram_id)
        VALUES ($1, $2)
        ON CONFLICT (telegram_id) DO UPDATE
        SET name = EXCLUDED.name,
            updated_at = NOW()
        RETURNING id
        """,
        user_name,
        telegram_user_id,
    )
    if row is None:
        raise RuntimeError("Could not create or load Postgres user.")

    return row["id"]


def _record_from_row(row: asyncpg.Record) -> ConversationRecord:
    return ConversationRecord(
        prompt=str(row["prompt"]),
        response=str(row["response"]),
        created_at=_format_created_at(row["created_at"]),
        kind=str(row["kind"]),
        tool_call_response=row["tool_call_response"],
        tool_result=row["tool_result"],
    )


def _format_conversation_for_context(record: ConversationRecord) -> str:
    if record.kind == "tool_call":
        return _format_tool_call_conversation_for_context(record)

    return json.dumps(
        {
            "conversation_date": record.created_at,
            "conversation_kind": "conversation",
            "juan_jose_farina_prompt": record.prompt,
            "response": record.response,
        },
        ensure_ascii=False,
        indent=2,
    )


def _format_tool_call_conversation_for_context(record: ConversationRecord) -> str:
    return json.dumps(
        {
            "conversation_date": record.created_at,
            "conversation_kind": "tool_call",
            "gemini_tool_call_response": _json_object(record.tool_call_response),
            "tool_results": _json_object(record.tool_result),
        },
        ensure_ascii=False,
        indent=2,
    )


def _format_created_at(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value)


def _json_object(value: object) -> object:
    if value is None:
        return {}
    if isinstance(value, str):
        return json.loads(value)
    return value


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
