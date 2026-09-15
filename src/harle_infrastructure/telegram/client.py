from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from harle_utils import MessageDeliveryError

TELEGRAM_API_BASE_URL = "https://api.telegram.org"
TELEGRAM_MESSAGE_LIMIT = 4096


@dataclass(frozen=True, slots=True)
class TelegramMessenger:
    bot_token: str

    def __post_init__(self) -> None:
        if not self.bot_token.strip():
            raise ValueError("Telegram bot token cannot be empty.")

    async def send_typing_action(self, *, chat_id: int) -> None:
        await self._post(
            method="sendChatAction",
            payload={"chat_id": chat_id, "action": "typing"},
        )

    async def send_message(self, *, chat_id: int, text: str) -> None:
        for chunk in _chunk_message(text or "I could not generate a response."):
            await self._post(
                method="sendMessage",
                payload={"chat_id": chat_id, "text": chunk},
            )

    async def _post(
        self,
        *,
        method: str,
        payload: Mapping[str, object],
    ) -> None:
        url = f"{TELEGRAM_API_BASE_URL}/bot{self.bot_token}/{method}"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(url, json=dict(payload))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MessageDeliveryError("Telegram delivery failed.") from exc


def _chunk_message(text: str) -> list[str]:
    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        chunks.append(remaining[:TELEGRAM_MESSAGE_LIMIT])
        remaining = remaining[TELEGRAM_MESSAGE_LIMIT:]
    return chunks
