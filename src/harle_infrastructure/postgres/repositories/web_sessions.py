from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar
from uuid import UUID

import asyncpg

from harle_domain.accounts import BrowserSession

FieldT = TypeVar("FieldT")


@dataclass(frozen=True, slots=True)
class PostgresBrowserSessionRepository:
    pool: asyncpg.Pool

    async def create(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
        created_at: datetime,
    ) -> BrowserSession:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO web_sessions (
                    user_id,
                    session_token_hash,
                    expires_at,
                    last_used_at,
                    created_at
                )
                VALUES ($1, $2, $3, $4, $4)
                RETURNING id, user_id, expires_at, created_at
                """,
                user_id,
                token_hash,
                expires_at,
                created_at,
            )
        if row is None:
            raise RuntimeError("Could not create the browser session.")
        return _session(row)

    async def resolve(
        self,
        *,
        token_hash: str,
        current_time: datetime,
    ) -> BrowserSession | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE web_sessions
                SET last_used_at = $2
                WHERE session_token_hash = $1
                    AND revoked_at IS NULL
                    AND expires_at > $2
                RETURNING id, user_id, expires_at, created_at
                """,
                token_hash,
                current_time,
            )
        return _session(row) if row is not None else None

    async def revoke(
        self,
        *,
        token_hash: str,
        revoked_at: datetime,
    ) -> bool:
        async with self.pool.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE web_sessions
                SET revoked_at = $2
                WHERE session_token_hash = $1
                    AND revoked_at IS NULL
                """,
                token_hash,
                revoked_at,
            )
        return result == "UPDATE 1"


def _session(row: asyncpg.Record) -> BrowserSession:
    return BrowserSession(
        id=_required(row, "id", UUID),
        user_id=_required(row, "user_id", UUID),
        expires_at=_required(row, "expires_at", datetime),
        created_at=_required(row, "created_at", datetime),
    )


def _required(
    row: asyncpg.Record,
    key: str,
    expected: type[FieldT],
) -> FieldT:
    value: object = row[key]
    if not isinstance(value, expected):
        raise TypeError(f"Unexpected {key} value.")
    return value
