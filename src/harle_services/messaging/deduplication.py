from dataclasses import dataclass

from harle_domain.messaging import TelegramUpdateClaimRepository


@dataclass(frozen=True, slots=True)
class TelegramUpdateDeduplicator:
    repository: TelegramUpdateClaimRepository

    async def claim(
        self,
        *,
        update_id: int,
        telegram_user_id: int,
        telegram_chat_id: int,
    ) -> bool:
        return await self.repository.claim(
            update_id=update_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
        )
