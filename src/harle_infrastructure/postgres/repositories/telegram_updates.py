from collections.abc import Sequence
from dataclasses import dataclass

import asyncpg

from harle_domain.messaging import TelegramUpdateReceipt, TelegramUpdateState


@dataclass(frozen=True, slots=True)
class PostgresTelegramUpdateRepository:
    pool: asyncpg.Pool

    async def receive(
        self,
        *,
        update_id: int,
        telegram_user_id: int,
        telegram_chat_id: int,
        message_text: str,
    ) -> TelegramUpdateReceipt:
        _validate_identifiers(
            update_id=update_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
        )
        if not message_text.strip():
            raise ValueError("Telegram message text cannot be empty.")
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock($1)",
                    update_id,
                )
                row = await connection.fetchrow(
                    """
                    SELECT
                        telegram_user_id,
                        telegram_chat_id,
                        message_text,
                        status
                    FROM telegram_update_claims
                    WHERE update_id = $1
                    """,
                    update_id,
                )
                newly_persisted = row is None
                if newly_persisted:
                    row = await connection.fetchrow(
                        """
                        INSERT INTO telegram_update_claims (
                            update_id,
                            telegram_user_id,
                            telegram_chat_id,
                            message_text,
                            status
                        )
                        VALUES ($1, $2, $3, $4, 'received')
                        RETURNING
                            telegram_user_id,
                            telegram_chat_id,
                            message_text,
                            status
                        """,
                        update_id,
                        telegram_user_id,
                        telegram_chat_id,
                        message_text,
                    )
                else:
                    row = await connection.fetchrow(
                        """
                        UPDATE telegram_update_claims
                        SET message_text = CASE
                                WHEN message_text = '' THEN $2
                                ELSE message_text
                            END,
                            status = CASE
                                WHEN status = 'failed' THEN 'received'
                                ELSE status
                            END,
                            updated_at = NOW()
                        WHERE update_id = $1
                        RETURNING
                            telegram_user_id,
                            telegram_chat_id,
                            message_text,
                            status
                        """,
                        update_id,
                        message_text,
                    )
        if row is None:
            raise RuntimeError("Could not persist the Telegram update.")
        if (
            _integer(row, "telegram_user_id") != telegram_user_id
            or _integer(row, "telegram_chat_id") != telegram_chat_id
            or _text(row, "message_text") != message_text
        ):
            raise ValueError(
                "Telegram update identifier was reused with different data.",
            )
        return TelegramUpdateReceipt(
            state=TelegramUpdateState(_text(row, "status")),
            newly_persisted=newly_persisted,
        )

    async def mark_processing(self, update_ids: Sequence[int]) -> None:
        await self._set_state(
            update_ids,
            state=TelegramUpdateState.PROCESSING,
            allowed=(
                TelegramUpdateState.RECEIVED,
                TelegramUpdateState.PROCESSING,
                TelegramUpdateState.FAILED,
            ),
        )

    async def mark_tool_started(self, update_ids: Sequence[int]) -> None:
        await self._set_state(
            update_ids,
            state=TelegramUpdateState.TOOL_STARTED,
            allowed=(
                TelegramUpdateState.RECEIVED,
                TelegramUpdateState.PROCESSING,
                TelegramUpdateState.TOOL_STARTED,
            ),
        )

    async def mark_delivering(self, update_ids: Sequence[int]) -> None:
        await self._set_state(
            update_ids,
            state=TelegramUpdateState.DELIVERING,
            allowed=(
                TelegramUpdateState.PROCESSING,
                TelegramUpdateState.TOOL_STARTED,
                TelegramUpdateState.DELIVERING,
            ),
        )

    async def mark_failed(self, update_ids: Sequence[int]) -> None:
        await self._set_state(
            update_ids,
            state=TelegramUpdateState.FAILED,
            allowed=(
                TelegramUpdateState.RECEIVED,
                TelegramUpdateState.PROCESSING,
                TelegramUpdateState.FAILED,
            ),
        )

    async def mark_rate_limited(self, update_ids: Sequence[int]) -> None:
        await self._set_state(
            update_ids,
            state=TelegramUpdateState.RATE_LIMITED,
            allowed=(TelegramUpdateState.RECEIVED,),
        )

    async def mark_interrupted(self, update_ids: Sequence[int]) -> None:
        await self._set_state(
            update_ids,
            state=TelegramUpdateState.INTERRUPTED,
            allowed=(
                TelegramUpdateState.RECEIVED,
                TelegramUpdateState.PROCESSING,
                TelegramUpdateState.TOOL_STARTED,
                TelegramUpdateState.DELIVERING,
                TelegramUpdateState.INTERRUPTED,
            ),
        )

    async def mark_rejected(self, update_ids: Sequence[int]) -> None:
        await self._set_state(
            update_ids,
            state=TelegramUpdateState.REJECTED,
            allowed=(
                TelegramUpdateState.RECEIVED,
                TelegramUpdateState.REJECTED,
            ),
        )

    async def _set_state(
        self,
        update_ids: Sequence[int],
        *,
        state: TelegramUpdateState,
        allowed: Sequence[TelegramUpdateState],
    ) -> None:
        identifiers = _validate_update_ids(update_ids)
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                UPDATE telegram_update_claims
                SET status = $2,
                    updated_at = NOW(),
                    tool_started_at = CASE
                        WHEN $2 = 'tool_started' THEN NOW()
                        ELSE tool_started_at
                    END
                WHERE update_id = ANY($1::bigint[])
                    AND status = ANY($3::text[])
                RETURNING update_id
                """,
                identifiers,
                state.value,
                [item.value for item in allowed],
            )
        updated_ids = {_integer(row, "update_id") for row in rows}
        if updated_ids != set(identifiers):
            raise RuntimeError("Could not update every Telegram message state.")


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


def _validate_update_ids(update_ids: Sequence[int]) -> list[int]:
    identifiers = list(update_ids)
    if not identifiers:
        raise ValueError("At least one Telegram update identifier is required.")
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Telegram update identifiers must be unique.")
    if any(isinstance(update_id, bool) or update_id < 0 for update_id in identifiers):
        raise ValueError("Telegram update identifiers must be non-negative.")
    return identifiers


def _integer(row: asyncpg.Record, key: str) -> int:
    value: object = row[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"Expected {key} to be an integer.")
    return value


def _text(row: asyncpg.Record, key: str) -> str:
    value: object = row[key]
    if not isinstance(value, str):
        raise TypeError(f"Expected {key} to be text.")
    return value
