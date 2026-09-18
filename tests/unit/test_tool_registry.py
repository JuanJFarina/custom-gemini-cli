import asyncio
from collections.abc import Mapping
from datetime import date, datetime, timezone
from typing import cast
from uuid import UUID, uuid4

import pytest

from harle_domain.accounts import (
    ExternalIdentity,
    Plan,
    ResolvedUser,
    SubscriptionStatus,
    User,
)
from harle_domain.events import EventRepository, InternalEvent
from harle_domain.expenses import ExpenseRepository
from harle_infrastructure.google_sheets import (
    GoogleSheetsClient,
    GoogleSheetsConnectionSettings,
    LegacyGoogleSheetsSettings,
)
from harle_services.bootstrap import EventToolDependencies, create_tools_injector
from harle_services.events import (
    EventNotificationQuotaService,
    NotificationQuotaStatus,
)
from harle_services.tools import ToolInjectionContext
from harle_services.tools.internal_events import EventIdentifierArgs, ListEventsArgs
from harle_utils import ToolAccessDeniedError, ToolUnavailableError

NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)


class EmptyEventRepository:
    async def list_for_range(self, **_: object) -> list[InternalEvent]:
        return []

    async def disable(self, **_: object) -> InternalEvent | None:
        return None


class FakeNotificationQuotas:
    async def status(
        self,
        *,
        user_id: UUID,
        monthly_limit: int,
    ) -> NotificationQuotaStatus:
        del user_id
        return NotificationQuotaStatus(
            limit=monthly_limit,
            remaining=monthly_limit - 1,
            resets_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )


def resolved_user(user_id: UUID) -> ResolvedUser:
    plan = Plan(
        code="basic",
        monthly_request_limit=480,
        monthly_notification_limit=60,
        active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    user = User(
        id=user_id,
        display_name="Beta User",
        plan_code=plan.code,
        subscription_status=SubscriptionStatus.ACTIVE,
        subscription_valid_until=None,
        subscription_synced_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    identity = ExternalIdentity(
        id=uuid4(),
        user_id=user_id,
        provider="telegram",
        external_user_id="123",
        display_name=user.display_name,
        created_at=NOW,
        updated_at=NOW,
    )
    return ResolvedUser(user=user, plan=plan, identity=identity)


def test_tool_access_matrix_and_lazy_sheets_configuration() -> None:
    juan_id = uuid4()
    expense_repository = cast(ExpenseRepository, object())
    event_repository = cast(EventRepository, object())
    event_tools = EventToolDependencies(
        repository=event_repository,
        notification_quotas=cast(EventNotificationQuotaService, object()),
    )
    incomplete_settings = LegacyGoogleSheetsSettings(
        _env_file=None,
        LEGACY_GOOGLE_SHEETS_USER_ID=juan_id,
    )
    commercial_store = create_tools_injector(
        incomplete_settings,
        expense_repository=expense_repository,
        event_tools=event_tools,
    ).inject(
        ToolInjectionContext(
            resolved_user=resolved_user(uuid4()),
            prompt="Show my expenses",
            timezone="America/Argentina/Cordoba",
        ),
    )

    assert {tool.name for tool in commercial_store.tools} == {
        "add_expense",
        "add_refund",
        "add_installment_expense",
        "list_expenses",
        "summarize_expenses",
        "update_expense",
        "delete_expense",
    }
    assert "Google Sheets" not in commercial_store.prompt
    with pytest.raises(ToolUnavailableError):
        commercial_store.get("add_one_time_transaction")

    configured_settings = LegacyGoogleSheetsSettings(
        _env_file=None,
        LEGACY_GOOGLE_SHEETS_USER_ID=juan_id,
        EXPENSES_SPREADSHEET_ID="current",
        EXPENSES_NEXT_YEAR_SPREADSHEET_ID="next",
        GOOGLE_SERVICE_ACCOUNT_JSON_BASE64="e30=",
    )
    juan_store = create_tools_injector(
        configured_settings,
        expense_repository=expense_repository,
        event_tools=event_tools,
    ).inject(
        ToolInjectionContext(
            resolved_user=resolved_user(juan_id),
            prompt="Show my expenses",
            timezone="America/Argentina/Cordoba",
        ),
    )

    assert {tool.name for tool in juan_store.tools} == {
        "add_one_time_transaction",
        "add_in_installments_transaction",
        "get_day_expenses",
        "get_month_expenses",
        "remove_or_update_transaction",
    }
    event_store = create_tools_injector(
        configured_settings,
        expense_repository=expense_repository,
        event_tools=event_tools,
    ).inject(
        ToolInjectionContext(
            resolved_user=resolved_user(juan_id),
            prompt="Create an event tomorrow",
            timezone="America/Argentina/Cordoba",
        ),
    )
    assert {tool.name for tool in event_store.tools} == {
        "list_events",
        "create_event",
        "update_event",
        "disable_event",
        "enable_event",
        "delete_event",
    }


def test_tool_filter_uses_complete_terms_and_falls_back_to_all_families() -> None:
    store = create_tools_injector(
        LegacyGoogleSheetsSettings(_env_file=None),
        expense_repository=cast(ExpenseRepository, object()),
        event_tools=EventToolDependencies(
            repository=cast(EventRepository, object()),
            notification_quotas=cast(EventNotificationQuotaService, object()),
        ),
    ).inject(
        ToolInjectionContext(
            resolved_user=resolved_user(uuid4()),
            prompt="I will eventually log lunch",
            timezone="America/Argentina/Cordoba",
        ),
    )

    names = {tool.name for tool in store.tools}
    assert "add_expense" in names
    assert "create_event" in names


def test_event_tools_expose_plan_notification_allowance() -> None:
    store = create_tools_injector(
        event_tools=EventToolDependencies(
            repository=cast(EventRepository, EmptyEventRepository()),
            notification_quotas=cast(
                EventNotificationQuotaService,
                FakeNotificationQuotas(),
            ),
        ),
    ).inject(
        ToolInjectionContext(
            resolved_user=resolved_user(uuid4()),
            prompt="List my events",
            timezone="UTC",
        ),
    )

    result = asyncio.run(
        store.get("list_events").handler(
            ListEventsArgs(
                start_date=date(2026, 8, 31),
                end_date=date(2026, 8, 31),
            ),
        ),
    )
    mutation_result = asyncio.run(
        store.get("disable_event").handler(
            EventIdentifierArgs(event_id=uuid4()),
        ),
    )

    for tool_result in (result, mutation_result):
        assert isinstance(tool_result.result, Mapping)
        assert tool_result.result["notification_quota"] == {
            "monthly_limit": 60,
            "remaining": 59,
            "resets_at": "2026-09-01T00:00:00Z",
        }


def test_google_sheets_client_rechecks_uuid_before_write() -> None:
    client = GoogleSheetsClient(
        settings=GoogleSheetsConnectionSettings(
            current_year_spreadsheet_id="current",
            next_year_spreadsheet_id="next",
            service_account_json_base64="e30=",
        ),
        execution_user_id=uuid4(),
        authorized_user_id=uuid4(),
    )

    with pytest.raises(ToolAccessDeniedError):
        asyncio.run(
            client.update_formula(
                sheet_name="enero",
                cell="E2",
                formula="=10",
            ),
        )
