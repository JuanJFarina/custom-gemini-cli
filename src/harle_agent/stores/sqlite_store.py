import asyncio
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from harle_agent.settings import get_agent_settings

TOKENS_CAP = get_agent_settings().MAX_CONVERSATION_TOKENS

NO_CONVERSATIONS_MESSAGE = "No conversations yet"


@dataclass(frozen=True)
class ConversationRecord:
    chat_id: int
    user_id: int
    prompt: str
    response: str
    model: str
    created_at: str


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
                SELECT telegram_chat_id, telegram_user_id, prompt, response, model, created_at
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
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.chat_id,
                        self.user_id,
                        prompt,
                        response_text,
                        model,
                        created_at,
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
                        created_at TEXT NOT NULL
                    )
                    """,
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
        chat_id=cast(int, row[0]),
        user_id=cast(int, row[1]),
        prompt=str(row[2]),
        response=str(row[3]),
        model=str(row[4]),
        created_at=str(row[5]),
    )


def _format_conversation_for_context(record: ConversationRecord) -> str:
    return json.dumps(
        {
            "conversation_date": record.created_at,
            "telegram_chat_id": record.chat_id,
            "telegram_user_id": record.user_id,
            "juan_jose_farina_prompt": record.prompt,
            "response": record.response,
        },
        ensure_ascii=False,
        indent=2,
    )
