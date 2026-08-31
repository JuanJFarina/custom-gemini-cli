from typing import Protocol, runtime_checkable


@runtime_checkable
class TelegramUpdateClaimRepository(Protocol):
    async def claim(
        self,
        *,
        update_id: int,
        telegram_user_id: int,
        telegram_chat_id: int,
    ) -> bool: ...
