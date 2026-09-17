from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from harle_domain.messaging import MediaContent, TelegramMediaReference
from harle_utils import MediaDownloadError, MessageDeliveryError

TELEGRAM_API_BASE_URL = "https://api.telegram.org"
TELEGRAM_MESSAGE_LIMIT = 4096


class TelegramFileResult(BaseModel):
    file_path: str = Field(min_length=1)


class TelegramFileResponse(BaseModel):
    ok: Literal[True]
    result: TelegramFileResult


@dataclass(frozen=True, slots=True)
class TelegramMessenger:
    bot_token: str
    maximum_media_size: int = 15 * 1024 * 1024

    def __post_init__(self) -> None:
        if not self.bot_token.strip():
            raise ValueError("Telegram bot token cannot be empty.")
        if self.maximum_media_size <= 0:
            raise ValueError("Telegram media size limit must be positive.")

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

    async def download(
        self,
        reference: TelegramMediaReference,
    ) -> MediaContent:
        if (
            reference.file_size is not None
            and reference.file_size > self.maximum_media_size
        ):
            raise MediaDownloadError("Telegram media exceeds the size limit.")
        file_path = await self._file_path(reference.file_id)
        data = await self._download_file(file_path)
        return MediaContent(reference=reference, data=data)

    async def _file_path(self, file_id: str) -> str:
        url = f"{TELEGRAM_API_BASE_URL}/bot{self.bot_token}/getFile"
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(url, json={"file_id": file_id})
            response.raise_for_status()
            payload = TelegramFileResponse.model_validate(response.json())
        except (httpx.HTTPError, ValidationError) as exc:
            raise MediaDownloadError("Telegram file lookup failed.") from exc
        return payload.result.file_path

    async def _download_file(self, file_path: str) -> bytes:
        url = f"{TELEGRAM_API_BASE_URL}/file/bot{self.bot_token}/{file_path}"
        data = bytearray()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    content_length = response.headers.get("content-length")
                    if (
                        content_length is not None
                        and int(content_length) > self.maximum_media_size
                    ):
                        raise MediaDownloadError(
                            "Telegram media exceeds the size limit.",
                        )
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > self.maximum_media_size:
                            raise MediaDownloadError(
                                "Telegram media exceeds the size limit.",
                            )
        except (httpx.HTTPError, ValueError) as exc:
            raise MediaDownloadError("Telegram file download failed.") from exc
        if not data:
            raise MediaDownloadError("Telegram file download returned no data.")
        return bytes(data)

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
