import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg

from harle_domain.conversations.models import ConversationRecord
from harle_domain.tools.models import InternalToolCallInteraction

DEFAULT_CONVERSATION_TOKENS = 1000
MAX_CONTEXT_RECORDS = 50
NO_CONVERSATIONS_MESSAGE = "No conversations yet"


@dataclass(frozen=True, slots=True)
class _ConversationWrite:
    prompt: str
    response_text: str
    model: str


@dataclass(frozen=True, slots=True)
class _ToolCallWrite:
    interaction: InternalToolCallInteraction
    interaction_index: int
    model: str


@dataclass(frozen=True, slots=True)
class PostgresConversationRepository:
    pool: asyncpg.Pool

    async def load(
        self,
        *,
        user_id: UUID,
        telegram_chat_id: int,
        max_tokens: int,
    ) -> str:
        if max_tokens <= 0:
            raise ValueError("Conversation token limit must be positive.")

        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT prompt, response, created_at, kind,
                    tool_call_response, tool_result
                FROM conversations
                WHERE user_id = $1
                    AND telegram_chat_id = $2
                    AND status = 'completed'
                ORDER BY created_at DESC, id DESC
                LIMIT $3
                """,
                user_id,
                telegram_chat_id,
                MAX_CONTEXT_RECORDS,
            )

        return _bounded_context(rows=rows, max_tokens=max_tokens)

    async def count_completed_conversations(
        self,
        *,
        user_id: UUID,
        created_from: datetime,
        created_before: datetime,
    ) -> int:
        _validate_utc_period(created_from, created_before)
        async with self.pool.acquire() as connection:
            count = await connection.fetchval(
                """
                SELECT COUNT(*)
                FROM conversations
                WHERE user_id = $1
                    AND kind = 'conversation'
                    AND status = 'completed'
                    AND created_at >= $2
                    AND created_at < $3
                """,
                user_id,
                created_from,
                created_before,
            )
        if isinstance(count, bool) or not isinstance(count, int):
            raise TypeError(
                "Expected the completed conversation count to be an integer.",
            )
        return count

    async def save(
        self,
        *,
        user_id: UUID,
        telegram_chat_id: int,
        telegram_update_ids: Sequence[int],
        conversation: _ConversationWrite,
    ) -> None:
        update_ids = _validate_update_ids(telegram_update_ids)
        primary_update_id = update_ids[0] if update_ids else None
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                conversation_id = await connection.fetchval(
                    """
                    INSERT INTO conversations (
                        user_id, telegram_chat_id, prompt, response,
                        model, kind, telegram_update_id, status, completed_at
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, 'conversation', $6, 'completed', NOW()
                    )
                    ON CONFLICT DO NOTHING
                    RETURNING id
                    """,
                    user_id,
                    telegram_chat_id,
                    conversation.prompt,
                    conversation.response_text,
                    conversation.model,
                    primary_update_id,
                )
                if conversation_id is None and primary_update_id is not None:
                    conversation_id = await connection.fetchval(
                        """
                        SELECT id
                        FROM conversations
                        WHERE telegram_update_id = $1
                            AND kind = 'conversation'
                        """,
                        primary_update_id,
                    )
                if isinstance(conversation_id, bool) or not isinstance(
                    conversation_id,
                    int,
                ):
                    raise RuntimeError("Could not persist the delivered conversation.")
                if update_ids:
                    rows = await connection.fetch(
                        """
                        UPDATE telegram_update_claims
                        SET status = 'delivered',
                            conversation_id = $2,
                            delivered_at = NOW(),
                            updated_at = NOW()
                        WHERE update_id = ANY($1::bigint[])
                            AND (
                                status <> 'delivered'
                                OR conversation_id = $2
                            )
                        RETURNING update_id
                        """,
                        update_ids,
                        conversation_id,
                    )
                    delivered_ids = {_integer(row, "update_id") for row in rows}
                    if delivered_ids != set(update_ids):
                        raise RuntimeError(
                            "Could not associate every update with the conversation.",
                        )

    async def save_tool_call(
        self,
        *,
        user_id: UUID,
        telegram_chat_id: int,
        tool_call: _ToolCallWrite,
    ) -> None:
        if (
            isinstance(tool_call.interaction_index, bool)
            or tool_call.interaction_index < 0
        ):
            raise ValueError("Tool interaction index must be non-negative.")
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO conversations (
                    user_id, telegram_chat_id, prompt, response, model,
                    kind, tool_call_response, tool_result,
                    tool_interaction_index,
                    status, completed_at
                )
                VALUES (
                    $1, $2, '', '', $3, 'tool_call', $4::jsonb, $5::jsonb,
                    $6, 'completed', NOW()
                )
                ON CONFLICT DO NOTHING
                """,
                user_id,
                telegram_chat_id,
                tool_call.model,
                json.dumps(tool_call.interaction.tool_call_response.model_dump()),
                json.dumps(
                    [
                        result.model_dump()
                        for result in tool_call.interaction.tool_results
                    ],
                ),
                tool_call.interaction_index,
            )

    async def save_scheduled(
        self,
        *,
        user_id: UUID,
        telegram_chat_id: int,
        response_text: str,
        model: str,
    ) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO conversations (
                    user_id, telegram_chat_id, prompt, response, model,
                    kind, status, completed_at
                )
                VALUES (
                    $1, $2, NULL, $3, $4,
                    'scheduled_message', 'completed', NOW()
                )
                """,
                user_id,
                telegram_chat_id,
                response_text,
                model,
            )


@dataclass(frozen=True, slots=True)
class PostgresConversationStore:
    repository: PostgresConversationRepository
    user_id: UUID
    telegram_chat_id: int
    max_tokens: int = DEFAULT_CONVERSATION_TOKENS

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError("Conversation token limit must be positive.")

    async def load(self) -> str:
        return await self.repository.load(
            user_id=self.user_id,
            telegram_chat_id=self.telegram_chat_id,
            max_tokens=self.max_tokens,
        )

    async def save(
        self,
        *,
        prompt: str,
        response_text: str,
        model: str,
        telegram_update_ids: Sequence[int] = (),
    ) -> None:
        await self.repository.save(
            user_id=self.user_id,
            telegram_chat_id=self.telegram_chat_id,
            telegram_update_ids=telegram_update_ids,
            conversation=_ConversationWrite(
                prompt=prompt,
                response_text=response_text,
                model=model,
            ),
        )

    async def save_tool_call(
        self,
        *,
        interaction: InternalToolCallInteraction,
        interaction_index: int,
        model: str,
    ) -> None:
        await self.repository.save_tool_call(
            user_id=self.user_id,
            telegram_chat_id=self.telegram_chat_id,
            tool_call=_ToolCallWrite(
                interaction=interaction,
                interaction_index=interaction_index,
                model=model,
            ),
        )

    async def save_scheduled(
        self,
        *,
        response_text: str,
        model: str,
    ) -> None:
        await self.repository.save_scheduled(
            user_id=self.user_id,
            telegram_chat_id=self.telegram_chat_id,
            response_text=response_text,
            model=model,
        )


def _bounded_context(
    *,
    rows: list[asyncpg.Record],
    max_tokens: int,
) -> str:
    if not rows:
        return NO_CONVERSATIONS_MESSAGE

    conversations: list[str] = []
    context_length = 0
    for row in rows:
        conversation = _format_conversation_for_context(_record_from_row(row))
        separator_length = 1 if conversations else 0
        next_context_length = context_length + separator_length + len(conversation)
        if (next_context_length / 4) > max_tokens:
            break

        conversations.append(conversation)
        context_length = next_context_length

    if not conversations:
        return NO_CONVERSATIONS_MESSAGE

    return "\n".join(reversed(conversations))


def _record_from_row(row: asyncpg.Record) -> ConversationRecord:
    return ConversationRecord(
        prompt=_optional_text(row, "prompt"),
        response=_text(row, "response"),
        created_at=_format_created_at(row["created_at"]),
        kind=_text(row, "kind"),
        tool_call_response=row["tool_call_response"],
        tool_result=row["tool_result"],
    )


def _format_conversation_for_context(record: ConversationRecord) -> str:
    if record.kind == "tool_call":
        return _format_tool_call_for_context(record)
    if record.kind == "scheduled_message":
        return json.dumps(
            {
                "conversation_date": record.created_at,
                "conversation_kind": "scheduled_message",
                "assistant_message": record.response,
            },
            ensure_ascii=False,
            indent=2,
        )

    return json.dumps(
        {
            "conversation_date": record.created_at,
            "conversation_kind": "conversation",
            "user_prompt": record.prompt,
            "response": record.response,
        },
        ensure_ascii=False,
        indent=2,
    )


def _format_tool_call_for_context(record: ConversationRecord) -> str:
    return json.dumps(
        {
            "conversation_date": record.created_at,
            "conversation_kind": "tool_call",
            "tool_call_response": _json_value(record.tool_call_response),
            "tool_results": _json_value(record.tool_result),
        },
        ensure_ascii=False,
        indent=2,
    )


def _format_created_at(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value)


def _json_value(value: object) -> object:
    if value is None:
        return {}
    if isinstance(value, str):
        return json.loads(value)
    return value


def _text(row: asyncpg.Record, key: str) -> str:
    value: object = row[key]
    if not isinstance(value, str):
        raise TypeError(f"Expected {key} to be text.")
    return value


def _optional_text(row: asyncpg.Record, key: str) -> str | None:
    value: object = row[key]
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"Expected {key} to be text or null.")
    return value


def _validate_utc_period(created_from: datetime, created_before: datetime) -> None:
    start_offset = created_from.utcoffset()
    end_offset = created_before.utcoffset()
    if start_offset is None or end_offset is None:
        raise ValueError("Conversation usage boundaries must include a timezone.")
    if start_offset.total_seconds() != 0:
        raise ValueError("Conversation usage start must use UTC.")
    if end_offset.total_seconds() != 0:
        raise ValueError("Conversation usage end must use UTC.")
    if created_before <= created_from:
        raise ValueError("Conversation usage end must follow its start.")


def _validate_update_ids(update_ids: Sequence[int]) -> list[int]:
    identifiers = list(update_ids)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Telegram update identifiers must be unique.")
    if any(isinstance(update_id, bool) or update_id < 0 for update_id in identifiers):
        raise ValueError("Telegram update identifiers must be non-negative.")
    return identifiers


def _integer(row: asyncpg.Record, key: str) -> int:
    value: object = row[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"Expected {key} to be an integer.")
    return value
