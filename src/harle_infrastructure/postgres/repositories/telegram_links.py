from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

import asyncpg

from harle_domain.accounts import (
    ExternalIdentity,
    TelegramLinkCommandRecord,
    TelegramLinkOutcome,
    TelegramLinkResult,
    TelegramLinkState,
    TelegramLinkStatus,
)
from harle_infrastructure.postgres.repositories.accounts import (
    insert_external_identity,
)


@dataclass(frozen=True, slots=True)
class PostgresTelegramLinkRepository:
    pool: asyncpg.Pool

    async def issue(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
        created_at: datetime,
    ) -> None:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                owner = await connection.fetchval(
                    "SELECT id FROM users WHERE id = $1 FOR UPDATE",
                    user_id,
                )
                if owner != user_id:
                    raise RuntimeError("Telegram link owner does not exist.")
                await connection.execute(
                    """
                    UPDATE telegram_link_tokens
                    SET consumed_at = $2
                    WHERE user_id = $1
                        AND consumed_at IS NULL
                    """,
                    user_id,
                    created_at,
                )
                await connection.execute(
                    """
                    INSERT INTO telegram_link_tokens (
                        user_id,
                        token_hash,
                        expires_at,
                        created_at
                    )
                    VALUES ($1, $2, $3, $4)
                    """,
                    user_id,
                    token_hash,
                    expires_at,
                    created_at,
                )

    async def get_status(
        self,
        *,
        user_id: UUID,
        current_time: datetime,
    ) -> TelegramLinkStatus:
        async with self.pool.acquire() as connection:
            linked = await connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM external_identities
                    WHERE user_id = $1
                        AND provider = 'telegram'
                )
                """,
                user_id,
            )
            if linked is True:
                return TelegramLinkStatus(TelegramLinkState.CONNECTED)
            expires_at = await connection.fetchval(
                """
                SELECT expires_at
                FROM telegram_link_tokens
                WHERE user_id = $1
                    AND consumed_at IS NULL
                    AND expires_at > $2
                ORDER BY created_at DESC
                LIMIT 1
                """,
                user_id,
                current_time,
            )
        if isinstance(expires_at, datetime):
            return TelegramLinkStatus(
                TelegramLinkState.PENDING,
                expires_at=expires_at,
            )
        return TelegramLinkStatus(TelegramLinkState.DISCONNECTED)

    async def process_command(
        self,
        *,
        command: TelegramLinkCommandRecord,
    ) -> TelegramLinkResult:
        if command.telegram_user_id <= 0:
            raise ValueError("Telegram user identifier must be positive.")
        if not command.telegram_display_name.strip():
            raise ValueError("Telegram display name cannot be empty.")
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock($1)",
                    command.update_id,
                )
                update = await connection.fetchrow(
                    """
                    SELECT telegram_user_id, telegram_chat_id, status
                    FROM telegram_update_claims
                    WHERE update_id = $1
                    FOR UPDATE
                    """,
                    command.update_id,
                )
                if update is None:
                    raise RuntimeError("Telegram link update was not persisted.")
                _require_matching_update(update, command)
                status = update["status"]
                if status == "delivered":
                    return TelegramLinkResult(TelegramLinkOutcome.DUPLICATE)
                if status not in {"received", "failed"}:
                    return TelegramLinkResult(TelegramLinkOutcome.DUPLICATE)
                await connection.execute(
                    """
                    UPDATE telegram_update_claims
                    SET status = 'processing',
                        updated_at = $2
                    WHERE update_id = $1
                    """,
                    command.update_id,
                    command.processed_at,
                )
                result = await _consume_link_token(connection, command)
                delivered = await connection.execute(
                    """
                    UPDATE telegram_update_claims
                    SET status = 'delivered',
                        delivered_at = $2,
                        updated_at = $2
                    WHERE update_id = $1
                        AND status = 'processing'
                    """,
                    command.update_id,
                    command.processed_at,
                )
                if delivered != "UPDATE 1":
                    raise RuntimeError("Could not complete the Telegram link update.")
                return result


def _require_matching_update(
    row: asyncpg.Record,
    command: TelegramLinkCommandRecord,
) -> None:
    if (
        row["telegram_user_id"] != command.telegram_user_id
        or row["telegram_chat_id"] != command.telegram_chat_id
    ):
        raise ValueError("Telegram update identity does not match link command.")


async def _consume_link_token(
    connection: asyncpg.Connection,
    command: TelegramLinkCommandRecord,
) -> TelegramLinkResult:
    row = await connection.fetchrow(
        """
        SELECT user_id
        FROM telegram_link_tokens
        WHERE token_hash = $1
            AND consumed_at IS NULL
            AND expires_at > $2
        FOR UPDATE
        """,
        command.token_hash,
        command.processed_at,
    )
    if row is None:
        return TelegramLinkResult(TelegramLinkOutcome.INVALID)
    user_id = row["user_id"]
    if not isinstance(user_id, UUID):
        raise TypeError("Unexpected Telegram link owner.")
    existing_owner = await connection.fetchval(
        """
        SELECT user_id
        FROM external_identities
        WHERE provider = 'telegram'
            AND external_user_id = $1
        """,
        str(command.telegram_user_id),
    )
    current_identity = await connection.fetchval(
        """
        SELECT external_user_id
        FROM external_identities
        WHERE user_id = $1
            AND provider = 'telegram'
        """,
        user_id,
    )
    await connection.execute(
        """
        UPDATE telegram_link_tokens
        SET consumed_at = $2
        WHERE token_hash = $1
        """,
        command.token_hash,
        command.processed_at,
    )
    if existing_owner == user_id:
        return TelegramLinkResult(
            TelegramLinkOutcome.ALREADY_LINKED,
            user_id=user_id,
        )
    if existing_owner is not None or current_identity is not None:
        return TelegramLinkResult(
            TelegramLinkOutcome.CONFLICT,
            user_id=user_id,
        )
    await insert_external_identity(
        connection,
        identity=ExternalIdentity(
            id=uuid4(),
            user_id=user_id,
            provider="telegram",
            external_user_id=str(command.telegram_user_id),
            display_name=command.telegram_display_name,
            created_at=command.processed_at,
            updated_at=command.processed_at,
        ),
    )
    return TelegramLinkResult(
        TelegramLinkOutcome.LINKED,
        user_id=user_id,
    )
