import asyncio
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from harle_agent.models import ConversationRecord, HarleToolInteraction
from harle_agent.settings import get_agent_settings

TOKENS_CAP = get_agent_settings().MAX_CONVERSATION_TOKENS

NO_CONVERSATIONS_MESSAGE = "No conversations yet"


class SQLiteConversationStore:
    def __init__(self, *, database_path: Path, chat_id: int, user_id: int) -> None:
        self.database_path = database_path
        self.chat_id = chat_id
        self.user_id = user_id

    async def load(self, *, max_tokens: int = TOKENS_CAP) -> str:
        return await asyncio.to_thread(self._load_sync, max_tokens=max_tokens)

    def _load_sync(self, *, max_tokens: int = TOKENS_CAP) -> str:
        self._ensure_schema()

        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT
                    prompt,
                    response,
                    created_at,
                    kind,
                    tool_call_response,
                    tool_result
                FROM conversations
                WHERE telegram_chat_id = ? AND telegram_user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 50
                """,
                (self.chat_id, self.user_id),
            ).fetchall()

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

    async def save(self, *, prompt: str, response_text: str, model: str) -> None:
        await asyncio.to_thread(
            self._save_sync,
            prompt=prompt,
            response_text=response_text,
            model=model,
        )

    async def save_tool_call(
        self,
        *,
        interaction: HarleToolInteraction,
        model: str,
    ) -> None:
        await asyncio.to_thread(
            self._save_tool_call_sync,
            interaction=interaction,
            model=model,
        )

    def _save_sync(self, *, prompt: str, response_text: str, model: str) -> None:
        self._ensure_schema()
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO conversations (
                        telegram_chat_id,
                        telegram_user_id,
                        prompt,
                        response,
                        model,
                        created_at,
                        kind
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.chat_id,
                        self.user_id,
                        prompt,
                        response_text,
                        model,
                        created_at,
                        "conversation",
                    ),
                )

    def _save_tool_call_sync(
        self,
        *,
        interaction: HarleToolInteraction,
        model: str,
    ) -> None:
        self._ensure_schema()
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO conversations (
                        telegram_chat_id,
                        telegram_user_id,
                        prompt,
                        response,
                        model,
                        created_at,
                        kind,
                        tool_call_response,
                        tool_result
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.chat_id,
                        self.user_id,
                        "",
                        "",
                        model,
                        created_at,
                        "tool_call",
                        json.dumps(interaction.tool_call.model_dump()),
                        json.dumps(interaction.tool_result.model_dump()),
                    ),
                )

    def _ensure_schema(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conversations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_chat_id INTEGER NOT NULL,
                        telegram_user_id INTEGER NOT NULL,
                        prompt TEXT NOT NULL,
                        response TEXT NOT NULL,
                        model TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        kind TEXT NOT NULL DEFAULT 'conversation',
                        tool_call_response TEXT,
                        tool_result TEXT
                    )
                    """,
                )
                _ensure_column(
                    connection=connection,
                    column_name="kind",
                    definition="kind TEXT NOT NULL DEFAULT 'conversation'",
                )
                _ensure_column(
                    connection=connection,
                    column_name="tool_call_response",
                    definition="tool_call_response TEXT",
                )
                _ensure_column(
                    connection=connection,
                    column_name="tool_result",
                    definition="tool_result TEXT",
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_conversations_chat_user_created_at
                    ON conversations (telegram_chat_id, telegram_user_id, created_at)
                    """,
                )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)


def _record_from_row(row: sqlite3.Row | tuple[object, ...]) -> ConversationRecord:
    return ConversationRecord(
        prompt=str(row[0]),
        response=str(row[1]),
        created_at=str(row[2]),
        kind=str(row[3]),
        tool_call_response=cast(str | None, row[4]),
        tool_result=cast(str | None, row[5]),
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
            "gemini_tool_call_response": json.loads(
                _json_text(record.tool_call_response),
            ),
            "tool_results": json.loads(_json_text(record.tool_result)),
        },
        ensure_ascii=False,
        indent=2,
    )


def _ensure_column(
    *,
    connection: sqlite3.Connection,
    column_name: str,
    definition: str,
) -> None:
    columns = connection.execute("PRAGMA table_info(conversations)").fetchall()
    column_names = {str(column[1]) for column in columns}
    if column_name not in column_names:
        connection.execute(f"ALTER TABLE conversations ADD COLUMN {definition}")


def _json_text(value: object) -> str:
    if value is None:
        return "{}"
    if not isinstance(value, str):
        raise TypeError(f"Expected JSON text, got {type(value).__name__}")
    return value
