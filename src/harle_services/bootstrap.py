from dataclasses import dataclass
from uuid import UUID

import asyncpg

from harle_domain.conversations.ports import ConversationStore
from harle_infrastructure.postgres import (
    PostgresAccountRepository,
    PostgresAssistantProfileRepository,
    PostgresConversationRepository,
    PostgresConversationStore,
    PostgresUserProfileRepository,
    create_postgres_pool,
    validate_postgres_schema,
)
from harle_services.access import IdentityService, SubscriptionService
from harle_services.runtime import UserRuntimeFactory


@dataclass(frozen=True, slots=True)
class ProcessRuntime:
    pool: asyncpg.Pool
    users: UserRuntimeFactory


async def create_process_runtime(
    *,
    database_url: str,
    pool_min_size: int,
    pool_max_size: int,
) -> ProcessRuntime:
    pool = await create_postgres_pool(
        database_url=database_url,
        min_size=pool_min_size,
        max_size=pool_max_size,
    )
    try:
        await validate_postgres_schema(pool)
    except Exception:
        await pool.close()
        raise

    conversations = PostgresConversationRepository(pool)

    def conversation_store(user_id: UUID, chat_id: int) -> ConversationStore:
        return PostgresConversationStore(
            repository=conversations,
            user_id=user_id,
            telegram_chat_id=chat_id,
        )

    return ProcessRuntime(
        pool=pool,
        users=UserRuntimeFactory(
            identity=IdentityService(PostgresAccountRepository(pool)),
            subscriptions=SubscriptionService(),
            user_profiles=PostgresUserProfileRepository(pool),
            assistant_profiles=PostgresAssistantProfileRepository(pool),
            conversation_store_builder=conversation_store,
        ),
    )


async def close_process_runtime(runtime: ProcessRuntime) -> None:
    await runtime.pool.close()
