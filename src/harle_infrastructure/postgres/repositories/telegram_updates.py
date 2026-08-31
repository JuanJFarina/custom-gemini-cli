from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True, slots=True)
class PostgresTelegramUpdateClaimRepository:
    pool: asyncpg.Pool

    async def claim(
        self,
        *,
        update_id: int,
        telegram_user_id: int,
        telegram_chat_id: int,
    ) -> bool:
        _validate_identifiers(
            update_id=update_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
        )
        async with self.pool.acquire() as connection:
            claimed = await connection.fetchval(
                """
                INSERT INTO telegram_update_claims (
                    update_id,
                    telegram_user_id,
                    telegram_chat_id
                )
                VALUES ($1, $2, $3)
                ON CONFLICT (update_id) DO NOTHING
                RETURNING TRUE
                """,
                update_id,
                telegram_user_id,
                telegram_chat_id,
            )
        return claimed is True


def _validate_identifiers(
    *,
    update_id: int,
    telegram_user_id: int,
    telegram_chat_id: int,
) -> None:
    if isinstance(update_id, bool) or update_id < 0:
        raise ValueError("Telegram update identifier must be non-negative.")
    if isinstance(telegram_user_id, bool) or telegram_user_id <= 0:
        raise ValueError("Telegram user identifier must be positive.")
    if isinstance(telegram_chat_id, bool) or telegram_chat_id == 0:
        raise ValueError("Telegram chat identifier cannot be zero.")
