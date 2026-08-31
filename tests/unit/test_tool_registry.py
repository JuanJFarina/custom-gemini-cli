import asyncio
from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from harle_agent.prompts import SYSTEM_PROMPT
from harle_domain.accounts import (
    ExternalIdentity,
    Plan,
    ResolvedUser,
    SubscriptionStatus,
    User,
)
from harle_domain.expenses import ExpenseRepository
from harle_domain.tools import (
    ToolCall,
    ToolDefinition,
    ToolEffect,
    ToolFamily,
    require_direct_request,
)
from harle_infrastructure.google_sheets import (
    GoogleSheetsClient,
    GoogleSheetsConnectionSettings,
    LegacyGoogleSheetsSettings,
)
from harle_services.bootstrap import create_tools_injector
from harle_utils import ToolAccessDeniedError, ToolUnavailableError

NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)


class EmptyArgs(BaseModel):
    pass


def resolved_user(user_id: UUID) -> ResolvedUser:
    plan = Plan(
        code="basic",
        monthly_request_limit=480,
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
    incomplete_settings = LegacyGoogleSheetsSettings(
        _env_file=None,
        LEGACY_GOOGLE_SHEETS_USER_ID=juan_id,
    )
    commercial_store = create_tools_injector(
        incomplete_settings,
        expense_repository=expense_repository,
    ).inject(
        resolved_user(uuid4()),
        timezone="America/Argentina/Cordoba",
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
    assert "add_one_time_transaction" not in SYSTEM_PROMPT
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
    ).inject(
        resolved_user(juan_id),
        timezone="America/Argentina/Cordoba",
    )

    assert {tool.name for tool in juan_store.tools} == {
        "add_one_time_transaction",
        "add_in_installments_transaction",
        "get_day_expenses",
        "get_month_expenses",
        "remove_or_update_transaction",
    }


def test_modifying_tools_require_a_direct_current_message_quote() -> None:
    definition = ToolDefinition(
        name="modify",
        family=ToolFamily.LEGACY_GOOGLE_SHEETS_EXPENSES,
        description="Modify data.",
        argument_model=EmptyArgs,
        effect=ToolEffect.MODIFY,
        can_run_concurrently=False,
    )

    with pytest.raises(ToolAccessDeniedError):
        require_direct_request(
            definition=definition,
            call=ToolCall(tool_name="modify", tool_args={}),
            user_message="Read my expenses.",
        )
    with pytest.raises(ToolAccessDeniedError):
        require_direct_request(
            definition=definition,
            call=ToolCall(
                tool_name="modify",
                tool_args={},
                direct_request_quote="add an expense",
            ),
            user_message="Read my expenses.",
        )

    require_direct_request(
        definition=definition,
        call=ToolCall(
            tool_name="modify",
            tool_args={},
            direct_request_quote="Add an expense",
        ),
        user_message="Please add an expense for lunch.",
    )


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
