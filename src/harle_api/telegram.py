from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

TELEGRAM_API_BASE_URL = "https://api.telegram.org"
TELEGRAM_MESSAGE_LIMIT = 4096


@dataclass(frozen=True)
class IncomingTelegramMessage:
    chat_id: int
    user_id: int
    text: str


def extract_text_message(update: Mapping[str, Any]) -> IncomingTelegramMessage | None:
    message = update.get("message")
    if not isinstance(message, Mapping):
        return None

    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        return None

    chat = message.get("chat")
    from_user = message.get("from")
    if not isinstance(chat, Mapping) or not isinstance(from_user, Mapping):
        return None

    chat_id = _parse_int(chat.get("id"))
    user_id = _parse_int(from_user.get("id"))
    if chat_id is None or user_id is None:
        return None

    return IncomingTelegramMessage(
        chat_id=chat_id,
        user_id=user_id,
        text=text.strip(),
    )


def is_allowed_user(message: IncomingTelegramMessage, allowed_user_id: int) -> bool:
    return message.user_id == allowed_user_id


async def send_typing_action(*, bot_token: str, chat_id: int) -> None:
    await _post_telegram_method(
        bot_token=bot_token,
        method="sendChatAction",
        payload={"chat_id": chat_id, "action": "typing"},
    )


async def send_message(*, bot_token: str, chat_id: int, text: str) -> None:
    chunks = list(_chunk_message(text or "I could not generate a response."))
    for chunk in chunks:
        await _post_telegram_method(
            bot_token=bot_token,
            method="sendMessage",
            payload={"chat_id": chat_id, "text": chunk},
        )


async def _post_telegram_method(
    *,
    bot_token: str,
    method: str,
    payload: Mapping[str, object],
) -> None:
    url = f"{TELEGRAM_API_BASE_URL}/bot{bot_token}/{method}"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, json=dict(payload))
        response.raise_for_status()


def _chunk_message(text: str) -> list[str]:
    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        chunks.append(remaining[:TELEGRAM_MESSAGE_LIMIT])
        remaining = remaining[TELEGRAM_MESSAGE_LIMIT:]

    return chunks


def _parse_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
