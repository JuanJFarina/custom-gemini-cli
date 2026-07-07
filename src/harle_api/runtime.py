from dataclasses import dataclass
from uuid import UUID

import asyncpg

from harle_agent.stores.postgres_store import setup_postgres_conversation_store
from harle_api.settings import ApiSettings


@dataclass(frozen=True)
class PostgresRuntime:
    pool: asyncpg.Pool
    owner_user_id: UUID
    owner_user_name: str


@dataclass(frozen=True)
class ApiRuntime:
    postgres: PostgresRuntime | None = None


async def create_runtime(settings: ApiSettings) -> ApiRuntime:
    if not settings.POSTGRES_DATABASE_URL:
        return ApiRuntime()

    pool = await asyncpg.create_pool(
        dsn=settings.POSTGRES_DATABASE_URL,
        min_size=settings.POSTGRES_POOL_MIN_SIZE,
        max_size=settings.POSTGRES_POOL_MAX_SIZE,
    )
    if pool is None:
        raise RuntimeError("Could not create Postgres connection pool.")

    owner_user_name = settings.TELEGRAM_USER_NAME or (
        f"Telegram user {settings.TELEGRAM_ALLOWED_USER_ID}"
    )
    try:
        owner_user_id = await setup_postgres_conversation_store(
            pool=pool,
            telegram_user_id=settings.TELEGRAM_ALLOWED_USER_ID,
            user_name=owner_user_name,
        )
    except Exception:
        await pool.close()
        raise

    return ApiRuntime(
        postgres=PostgresRuntime(
            pool=pool,
            owner_user_id=owner_user_id,
            owner_user_name=owner_user_name,
        ),
    )


async def close_runtime(runtime: ApiRuntime) -> None:
    if runtime.postgres is not None:
        await runtime.postgres.pool.close()
