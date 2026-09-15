from dataclasses import dataclass
from uuid import UUID

import asyncpg

from harle_domain.conversations.ports import ConversationStore
from harle_domain.events import EventRepository
from harle_domain.expenses import ExpenseRepository
from harle_domain.messaging import OutboundMessenger
from harle_infrastructure.google_sheets import (
    GoogleSheetsClientFactory,
    LegacyGoogleSheetsSettings,
)
from harle_infrastructure.postgres import (
    PostgresAccountRepository,
    PostgresAssistantProfileRepository,
    PostgresConversationRepository,
    PostgresConversationStore,
    PostgresEventRepository,
    PostgresExpenseRepository,
    PostgresTelegramUpdateRepository,
    PostgresUserProfileRepository,
    create_postgres_pool,
    validate_postgres_schema,
)
from harle_infrastructure.telegram import TelegramMessenger
from harle_services.access import PreflightService
from harle_services.events import (
    AgentsScheduler,
    EventNotificationService,
    EventService,
)
from harle_services.expenses import ExpenseService
from harle_services.messaging import MessageCoordinator
from harle_services.runtime import UserRuntimeFactory
from harle_services.tools import (
    ToolAccessPolicy,
    ToolFamilyRegistration,
    ToolRegistry,
    ToolsInjector,
    create_internal_events_registration,
    create_internal_expenses_registration,
    create_legacy_google_sheets_registration,
)


@dataclass(frozen=True, slots=True)
class ProcessRuntime:
    pool: asyncpg.Pool
    preflight: PreflightService
    users: UserRuntimeFactory
    tools: ToolsInjector
    messages: MessageCoordinator
    messenger: OutboundMessenger
    scheduler: AgentsScheduler


@dataclass(frozen=True, slots=True)
class ProcessRuntimeConfig:
    database_url: str
    pool_min_size: int
    pool_max_size: int
    telegram_bot_token: str
    scheduler_interval_seconds: float = 300


def create_tools_injector(
    settings: LegacyGoogleSheetsSettings | None = None,
    *,
    expense_repository: ExpenseRepository | None = None,
    event_repository: EventRepository | None = None,
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
    if event_repository is not None:
        registrations.append(
            create_internal_events_registration(
                EventService(event_repository),
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
    config: ProcessRuntimeConfig,
    *,
    legacy_google_sheets_settings: LegacyGoogleSheetsSettings | None = None,
) -> ProcessRuntime:
    pool = await create_postgres_pool(
        database_url=config.database_url,
        min_size=config.pool_min_size,
        max_size=config.pool_max_size,
    )
    try:
        await validate_postgres_schema(pool)
    except Exception:
        await pool.close()
        raise

    return _build_process_runtime(
        pool,
        config,
        legacy_google_sheets_settings,
    )


def _build_process_runtime(
    pool: asyncpg.Pool,
    config: ProcessRuntimeConfig,
    legacy_settings: LegacyGoogleSheetsSettings | None,
) -> ProcessRuntime:
    accounts = PostgresAccountRepository(pool)
    conversations = PostgresConversationRepository(pool)
    event_repository = PostgresEventRepository(pool)
    messenger = TelegramMessenger(config.telegram_bot_token)
    users = _create_user_runtime_factory(
        pool,
        conversations,
    )
    preflight = PreflightService(
        accounts=accounts,
        conversations=conversations,
    )
    notifications = EventNotificationService(
        preflight=preflight,
        users=users,
        messenger=messenger,
    )
    return ProcessRuntime(
        pool=pool,
        preflight=preflight,
        users=users,
        tools=create_tools_injector(
            legacy_settings,
            expense_repository=PostgresExpenseRepository(pool),
            event_repository=event_repository,
        ),
        messages=MessageCoordinator(
            PostgresTelegramUpdateRepository(pool),
            preflight.check_rate_limit,
        ),
        messenger=messenger,
        scheduler=AgentsScheduler(
            events=EventService(event_repository),
            notifications=notifications,
            interval_seconds=config.scheduler_interval_seconds,
        ),
    )


def _create_user_runtime_factory(
    pool: asyncpg.Pool,
    conversations: PostgresConversationRepository,
) -> UserRuntimeFactory:
    def conversation_store(
        user_id: UUID,
        chat_id: int,
    ) -> ConversationStore:
        return PostgresConversationStore(
            repository=conversations,
            user_id=user_id,
            telegram_chat_id=chat_id,
        )

    return UserRuntimeFactory(
        user_profiles=PostgresUserProfileRepository(pool),
        assistant_profiles=PostgresAssistantProfileRepository(pool),
        conversation_store_builder=conversation_store,
    )


async def close_process_runtime(runtime: ProcessRuntime) -> None:
    await runtime.scheduler.stop()
    await runtime.pool.close()
