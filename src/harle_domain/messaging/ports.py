from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable
from uuid import UUID

from .models import MediaContent, RecentMedia, TelegramMediaReference


class TelegramUpdateState(str, Enum):
    RECEIVED = "received"
    PROCESSING = "processing"
    TOOL_STARTED = "tool_started"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    INTERRUPTED = "interrupted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class TelegramUpdateReceipt:
    state: TelegramUpdateState
    newly_persisted: bool


@runtime_checkable
class TelegramUpdateRepository(Protocol):
    async def receive(
        self,
        *,
        update_id: int,
        telegram_user_id: int,
        telegram_chat_id: int,
        message_text: str,
    ) -> TelegramUpdateReceipt: ...

    async def mark_processing(self, update_ids: Sequence[int]) -> None: ...

    async def mark_tool_started(self, update_ids: Sequence[int]) -> None: ...

    async def mark_delivering(self, update_ids: Sequence[int]) -> None: ...

    async def mark_failed(self, update_ids: Sequence[int]) -> None: ...

    async def mark_rate_limited(self, update_ids: Sequence[int]) -> None: ...

    async def mark_interrupted(self, update_ids: Sequence[int]) -> None: ...

    async def mark_rejected(self, update_ids: Sequence[int]) -> None: ...


@runtime_checkable
class OutboundMessenger(Protocol):
    async def send_message(self, *, chat_id: int, text: str) -> None: ...

    async def send_typing_action(self, *, chat_id: int) -> None: ...


@runtime_checkable
class TelegramMediaDownloader(Protocol):
    async def download(
        self,
        reference: TelegramMediaReference,
    ) -> MediaContent: ...


@runtime_checkable
class RecentMediaStore(Protocol):
    def add(
        self,
        *,
        user_id: UUID,
        reference: TelegramMediaReference,
    ) -> RecentMedia: ...

    def list_recent(self, *, user_id: UUID) -> Sequence[RecentMedia]: ...

    def get(
        self,
        *,
        user_id: UUID,
        attachment_id: UUID,
    ) -> RecentMedia | None: ...
