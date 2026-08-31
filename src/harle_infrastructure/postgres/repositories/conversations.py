import json
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
                WHERE user_id = $1 AND telegram_chat_id = $2
                ORDER BY created_at DESC, id DESC
                LIMIT $3
                """,
                user_id,
                telegram_chat_id,
                MAX_CONTEXT_RECORDS,
            )

        return _bounded_context(rows=rows, max_tokens=max_tokens)

    async def save(
        self,
        *,
        user_id: UUID,
        telegram_chat_id: int,
        telegram_update_id: int | None,
        conversation: _ConversationWrite,
    ) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO conversations (
                    user_id, telegram_chat_id, prompt, response,
                    model, kind, telegram_update_id
                )
                VALUES ($1, $2, $3, $4, $5, 'conversation', $6)
                ON CONFLICT DO NOTHING
                """,
                user_id,
                telegram_chat_id,
                conversation.prompt,
                conversation.response_text,
                conversation.model,
                telegram_update_id,
            )

    async def save_tool_call(
        self,
        *,
        user_id: UUID,
        telegram_chat_id: int,
        telegram_update_id: int | None,
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
                    telegram_update_id, tool_interaction_index
                )
                VALUES (
                    $1, $2, '', '', $3, 'tool_call', $4::jsonb, $5::jsonb,
                    $6, $7
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
                telegram_update_id,
                tool_call.interaction_index,
            )


@dataclass(frozen=True, slots=True)
class PostgresConversationStore:
    repository: PostgresConversationRepository
    user_id: UUID
    telegram_chat_id: int
    telegram_update_id: int | None = None
    max_tokens: int = DEFAULT_CONVERSATION_TOKENS

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError("Conversation token limit must be positive.")
        if (
            isinstance(self.telegram_update_id, bool)
            or self.telegram_update_id is not None
            and self.telegram_update_id < 0
        ):
            raise ValueError("Telegram update identifier must be non-negative.")

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
    ) -> None:
        await self.repository.save(
            user_id=self.user_id,
            telegram_chat_id=self.telegram_chat_id,
            telegram_update_id=self.telegram_update_id,
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
            telegram_update_id=self.telegram_update_id,
            tool_call=_ToolCallWrite(
                interaction=interaction,
                interaction_index=interaction_index,
                model=model,
            ),
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
        prompt=_text(row, "prompt"),
        response=_text(row, "response"),
        created_at=_format_created_at(row["created_at"]),
        kind=_text(row, "kind"),
        tool_call_response=row["tool_call_response"],
        tool_result=row["tool_result"],
    )


def _format_conversation_for_context(record: ConversationRecord) -> str:
    if record.kind == "tool_call":
        return _format_tool_call_for_context(record)

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
