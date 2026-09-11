from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class TelegramUpdateState(str, Enum):
    RECEIVED = "received"
    PROCESSING = "processing"
    TOOL_STARTED = "tool_started"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    INTERRUPTED = "interrupted"


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
