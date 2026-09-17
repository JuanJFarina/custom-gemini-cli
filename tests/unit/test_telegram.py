import asyncio
from collections.abc import AsyncIterator, Mapping

import pytest
from pytest import MonkeyPatch

import harle_infrastructure.telegram.client as telegram_client_module
from harle_api.telegram import (
    IncomingTelegramMessage,
    UnsupportedTelegramMedia,
    extract_telegram_message,
)
from harle_domain.messaging import MediaKind, TelegramMediaReference
from harle_infrastructure.telegram import TelegramMessenger
from harle_utils import MediaDownloadError


def test_extract_telegram_message_includes_valid_text_update() -> None:
    message = extract_telegram_message(
        {
            "update_id": 123,
            "message": {
                "text": " Hello ",
                "chat": {"id": 456},
                "from": {
                    "id": 789,
                    "first_name": "Beta",
                    "last_name": "User",
                },
            },
        },
    )

    assert isinstance(message, IncomingTelegramMessage)
    assert message.update_id == 123
    assert message.chat_id == 456
    assert message.user_id == 789
    assert message.user_name == "Beta User"
    assert message.text == "Hello"
    assert message.media is None


def test_extract_telegram_message_rejects_invalid_update_id() -> None:
    for update_id in (None, True, -1, "123"):
        assert (
            extract_telegram_message(
                {
                    "update_id": update_id,
                    "message": {
                        "text": "Hello",
                        "chat": {"id": 456},
                        "from": {"id": 789},
                    },
                },
            )
            is None
        )


def test_extract_telegram_message_accepts_media_and_rejects_unsupported_files() -> None:
    photo = extract_telegram_message(
        {
            "update_id": 123,
            "message": {
                "photo": [
                    {
                        "file_id": "small",
                        "file_unique_id": "small-unique",
                        "width": 90,
                        "height": 90,
                    },
                    {
                        "file_id": "large",
                        "file_unique_id": "large-unique",
                        "width": 1280,
                        "height": 720,
                    },
                ],
                "caption": "¿Qué muestra esto?",
                "chat": {"id": 456},
                "from": {"id": 789},
            },
        },
    )
    unsupported = extract_telegram_message(
        {
            "update_id": 124,
            "message": {
                "document": {
                    "file_id": "document",
                    "file_unique_id": "document-unique",
                    "mime_type": "application/pdf",
                },
                "chat": {"id": 456},
                "from": {"id": 789},
            },
        },
    )

    assert isinstance(photo, IncomingTelegramMessage)
    assert photo.media is not None
    assert photo.media.file_id == "large"
    assert photo.media.kind is MediaKind.IMAGE
    assert photo.text == "[Imagen adjunta]\n¿Qué muestra esto?"
    assert isinstance(unsupported, UnsupportedTelegramMedia)
    assert unsupported.reason == "unsupported_media_type"


def test_telegram_media_download_is_bounded(
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeResponse:
        headers: Mapping[str, str] = {"content-length": "4"}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> Mapping[str, object]:
            return {"ok": True, "result": {"file_path": "photos/file.jpg"}}

        async def aiter_bytes(self) -> AsyncIterator[bytes]:
            yield b"data"

    class FakeStream:
        async def __aenter__(self) -> FakeResponse:
            return FakeResponse()

        async def __aexit__(self, *_: object) -> None:
            return None

    class FakeClient:
        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def post(self, *_: object, **__: object) -> FakeResponse:
            return FakeResponse()

        def stream(self, *_: object, **__: object) -> FakeStream:
            return FakeStream()

    async def verify() -> None:
        monkeypatch.setattr(
            telegram_client_module.httpx,
            "AsyncClient",
            lambda **_: FakeClient(),
        )
        messenger = TelegramMessenger("token", maximum_media_size=4)
        reference = TelegramMediaReference(
            update_id=1,
            file_id="file",
            file_unique_id="unique",
            kind=MediaKind.IMAGE,
            mime_type="image/jpeg",
            file_size=4,
        )

        content = await messenger.download(reference)

        assert content.data == b"data"
        with pytest.raises(MediaDownloadError):
            await messenger.download(
                TelegramMediaReference(
                    update_id=2,
                    file_id="large",
                    file_unique_id="large-unique",
                    kind=MediaKind.IMAGE,
                    mime_type="image/jpeg",
                    file_size=5,
                ),
            )

    asyncio.run(verify())
