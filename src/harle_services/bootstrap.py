from dataclasses import dataclass
from uuid import UUID

import asyncpg

from harle_domain.conversations.ports import ConversationStore
from harle_domain.expenses import ExpenseRepository
from harle_infrastructure.google_sheets import (
    GoogleSheetsClientFactory,
    LegacyGoogleSheetsSettings,
)
from harle_infrastructure.postgres import (
    PostgresAccountRepository,
    PostgresAssistantProfileRepository,
    PostgresConversationRepository,
    PostgresConversationStore,
    PostgresExpenseRepository,
    PostgresUserProfileRepository,
    create_postgres_pool,
    validate_postgres_schema,
)
from harle_services.access import IdentityService, SubscriptionService
from harle_services.expenses import ExpenseService
from harle_services.runtime import UserRuntimeFactory
from harle_services.tools import (
    ToolAccessPolicy,
    ToolFamilyRegistration,
    ToolRegistry,
    ToolsInjector,
    create_internal_expenses_registration,
    create_legacy_google_sheets_registration,
)


@dataclass(frozen=True, slots=True)
class ProcessRuntime:
    pool: asyncpg.Pool
    users: UserRuntimeFactory
    tools: ToolsInjector


def create_tools_injector(
    settings: LegacyGoogleSheetsSettings | None = None,
    *,
    expense_repository: ExpenseRepository | None = None,
) -> ToolsInjector:
    legacy_settings = settings or LegacyGoogleSheetsSettings()
    registrations: list[ToolFamilyRegistration] = [
        create_legacy_google_sheets_registration(
            GoogleSheetsClientFactory(legacy_settings),
        ),
    ]
    if expense_repository is not None:
        registrations.append(
            create_internal_expenses_registration(
                ExpenseService(expense_repository),
            ),
        )
    registry = ToolRegistry(
        registrations=registrations,
    )
    return ToolsInjector(
        registry=registry,
        access_policy=ToolAccessPolicy(
            legacy_settings.LEGACY_GOOGLE_SHEETS_USER_ID,
        ),
    )


async def create_process_runtime(
    *,
    database_url: str,
    pool_min_size: int,
    pool_max_size: int,
    legacy_google_sheets_settings: LegacyGoogleSheetsSettings | None = None,
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
    tools = create_tools_injector(
        legacy_google_sheets_settings,
        expense_repository=PostgresExpenseRepository(pool),
    )

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
            tools=tools,
        ),
        tools=tools,
    )


async def close_process_runtime(runtime: ProcessRuntime) -> None:
    await runtime.pool.close()
