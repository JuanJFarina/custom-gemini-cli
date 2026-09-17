import asyncio

import pytest

from harle_agent.agent import _gemini_contents
from harle_api.assistant import _download_media
from harle_domain.messaging import MediaContent, MediaKind, TelegramMediaReference
from harle_domain.tools import ToolCallResult
from harle_services.messaging import MessageFragment, MessageTurn
from harle_utils import MediaDownloadError


def test_gemini_contents_include_unique_media_without_persisting_bytes() -> None:
    media = MediaContent(
        reference=TelegramMediaReference(
            update_id=123,
            file_id="telegram-file",
            file_unique_id="unique-file",
            kind=MediaKind.IMAGE,
            mime_type="image/jpeg",
        ),
        data=b"image-bytes",
    )
    tool_result = ToolCallResult(
        called_tool_name="load_recent_media",
        result={"attachment_id": str(media.reference.attachment_id)},
        media=media,
    )

    contents = _gemini_contents("Describe the image", [media], [tool_result])

    assert len(contents) == 2
    assert not isinstance(contents[0], str)
    assert contents[0].inline_data is not None
    assert contents[0].inline_data.mime_type == "image/jpeg"
    assert contents[0].inline_data.data == b"image-bytes"
    assert contents[1] == "Describe the image"
    assert tool_result.model_dump() == {
        "called_tool_name": "load_recent_media",
        "result": {"attachment_id": str(media.reference.attachment_id)},
    }


def test_download_media_enforces_combined_request_size() -> None:
    class FakeDownloader:
        async def download(
            self,
            reference: TelegramMediaReference,
        ) -> MediaContent:
            return MediaContent(reference=reference, data=b"1234567")

    async def verify() -> None:
        references = [
            TelegramMediaReference(
                update_id=update_id,
                file_id=f"file-{update_id}",
                file_unique_id=f"unique-{update_id}",
                kind=MediaKind.IMAGE,
                mime_type="image/jpeg",
            )
            for update_id in (1, 2)
        ]
        turn = MessageTurn(
            telegram_user_id=1,
            telegram_chat_id=2,
            messages=[
                MessageFragment(1, 1, 2, "[Imagen adjunta]", references[0]),
                MessageFragment(2, 1, 2, "[Imagen adjunta]", references[1]),
            ],
            generation=0,
        )

        with pytest.raises(MediaDownloadError):
            await _download_media(turn, FakeDownloader(), 12)

    asyncio.run(verify())
