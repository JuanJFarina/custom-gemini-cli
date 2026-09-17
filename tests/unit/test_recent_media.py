import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from harle_domain.messaging import MediaContent, MediaKind, TelegramMediaReference
from harle_domain.tools import ToolExecutionContext, ToolFamily
from harle_infrastructure.telegram import InMemoryRecentMediaStore
from harle_services.tools.recent_media import (
    LoadRecentMediaArgs,
    create_recent_media_registration,
)

NOW = datetime(2026, 9, 16, 18, tzinfo=timezone.utc)


def _reference(update_id: int) -> TelegramMediaReference:
    return TelegramMediaReference(
        update_id=update_id,
        file_id=f"file-{update_id}",
        file_unique_id=f"unique-{update_id}",
        kind=MediaKind.IMAGE,
        mime_type="image/jpeg",
    )


def test_recent_media_isolates_users_and_keeps_newest_references() -> None:
    first_user = uuid4()
    second_user = uuid4()
    store = InMemoryRecentMediaStore(
        maximum_per_user=2,
        clock=lambda: NOW,
    )

    for update_id in (1, 2, 3):
        store.add(user_id=first_user, reference=_reference(update_id))
    store.add(user_id=second_user, reference=_reference(4))

    first = store.list_recent(user_id=first_user)
    second = store.list_recent(user_id=second_user)
    assert [item.reference.update_id for item in first] == [3, 2]
    assert [item.reference.update_id for item in second] == [4]
    assert (
        store.get(
            user_id=second_user,
            attachment_id=first[0].attachment_id,
        )
        is None
    )


def test_recent_media_expires_after_retention_window() -> None:
    current_time = [NOW]
    user_id = uuid4()
    store = InMemoryRecentMediaStore(
        retention=timedelta(hours=12),
        clock=lambda: current_time[0],
    )
    store.add(user_id=user_id, reference=_reference(1))

    current_time[0] += timedelta(hours=12, seconds=1)

    assert not store.list_recent(user_id=user_id)


def test_recent_media_tool_loads_only_the_owners_attachment() -> None:
    class FakeDownloader:
        async def download(
            self,
            reference: TelegramMediaReference,
        ) -> MediaContent:
            return MediaContent(reference=reference, data=b"image")

    async def verify() -> None:
        owner_id = uuid4()
        other_id = uuid4()
        store = InMemoryRecentMediaStore(clock=lambda: NOW)
        recent = store.add(user_id=owner_id, reference=_reference(1))
        registration = create_recent_media_registration(store, FakeDownloader())
        owner_handler = registration.handler_factory(
            ToolExecutionContext(
                user_id=owner_id,
                timezone="UTC",
                authorized_families=frozenset({ToolFamily.RECENT_MEDIA}),
            ),
        )["load_recent_media"]
        other_handler = registration.handler_factory(
            ToolExecutionContext(
                user_id=other_id,
                timezone="UTC",
                authorized_families=frozenset({ToolFamily.RECENT_MEDIA}),
            ),
        )["load_recent_media"]

        loaded = await owner_handler(
            LoadRecentMediaArgs(attachment_id=recent.attachment_id)
        )
        denied = await other_handler(
            LoadRecentMediaArgs(attachment_id=recent.attachment_id)
        )

        assert loaded.media is not None
        assert loaded.media.data == b"image"
        assert denied.media is None
        assert denied.result == {
            "ok": False,
            "reason": "Recent attachment was not found or expired.",
        }

    asyncio.run(verify())
