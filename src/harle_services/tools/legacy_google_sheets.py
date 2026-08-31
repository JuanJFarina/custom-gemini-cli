from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, TypeVar
from uuid import UUID

from gspread.utils import ValueRenderOption
from pydantic import BaseModel, ConfigDict, Field

from harle_domain.tools import (
    ToolCallResult,
    ToolDefinition,
    ToolEffect,
    ToolExecutionContext,
    ToolFamily,
    ToolHandler,
)
from harle_infrastructure.google_sheets import (
    CATEGORY_COLUMNS,
    LEGACY_EXPENSE_TIMEZONE,
    MONTH_SHEET_MAPPING,
    TOTAL_COLUMN,
    GoogleSheetsClient,
    GoogleSheetsClientFactory,
    TargetYear,
)
from harle_utils import ToolAccessDeniedError

from .registry import ToolFamilyRegistration

DayNumber = Annotated[int, Field(ge=1, le=31)]
MonthNumber = Annotated[int, Field(ge=1, le=12)]
ModelT = TypeVar("ModelT", bound=BaseModel)
LAST_DAY_ROW = 32
FINAL_TOTAL_ROW = LAST_DAY_ROW + 1


class TransactionArgs(BaseModel):
    amount: int = Field(gt=0)
    category: str = Field(pattern=r"^(B|C|D|E|F|G|H|I)$")
    month: MonthNumber = Field(
        default_factory=lambda: datetime.now(LEGACY_EXPENSE_TIMEZONE).month,
    )
    day: DayNumber = Field(
        default_factory=lambda: datetime.now(LEGACY_EXPENSE_TIMEZONE).day,
    )

    model_config = ConfigDict(extra="forbid")


class AddOneTimeTransactionArgs(TransactionArgs):
    is_refund: bool = False


class AddInInstallmentsTransactionArgs(TransactionArgs):
    installments: int = Field(gt=1, le=12)


class Transaction(TransactionArgs):
    is_refund: bool = False


class DayExpensesArgs(BaseModel):
    days: list[DayNumber] = Field(
        default_factory=lambda: [datetime.now(LEGACY_EXPENSE_TIMEZONE).day],
        min_length=1,
        max_length=31,
    )
    month: MonthNumber = Field(
        default_factory=lambda: datetime.now(LEGACY_EXPENSE_TIMEZONE).month,
    )

    model_config = ConfigDict(extra="forbid")


class MonthExpensesArgs(BaseModel):
    months: list[MonthNumber] = Field(
        default_factory=lambda: [datetime.now(LEGACY_EXPENSE_TIMEZONE).month],
        min_length=1,
        max_length=12,
    )

    model_config = ConfigDict(extra="forbid")


class RemoveOrUpdateTransactionArgs(BaseModel):
    old_transaction: Transaction
    new_transaction: Transaction | None = None

    model_config = ConfigDict(extra="forbid")


class TransactionEntry(BaseModel):
    category: str
    day: int
    amount: int | float
    formula: str


class DayExpenses(BaseModel):
    day: int
    transactions: list[TransactionEntry]
    total: int | float


class MonthExpenses(BaseModel):
    sheet: str
    category_totals: Mapping[str, int | float]
    total: int | float


class TransactionLocation(BaseModel):
    sheet_name: str
    cell: str


class FormulaUpdate(BaseModel):
    sheet_modified: str
    cell: str
    old_formula: str
    new_formula: str


class TransactionRemoval(BaseModel):
    old_transaction: Transaction
    location: TransactionLocation
    old_formula: str
    formula_after_removal: str
    removed: bool
    duplicate_matches: int


FAMILY = ToolFamily.LEGACY_GOOGLE_SHEETS_EXPENSES

SHARED_INSTRUCTIONS = """For every legacy expense tool:
- Transactions from 00:00 through 04:00 belong to the previous day; tell the user when applying this rule.
- Categories are B rent/building, C essential services, D non-essential services, E home, F transport, G outings, H shopping, and I other.
- These tools operate only on Juan's private Google Sheets expense tracker."""

DEFINITIONS = (
    ToolDefinition(
        name="add_one_time_transaction",
        family=FAMILY,
        description=(
            "Add a one-time expense or refund in Argentine pesos. Month and day "
            "default to the current legacy-expense timezone."
        ),
        argument_model=AddOneTimeTransactionArgs,
        effect=ToolEffect.MODIFY,
        can_run_concurrently=False,
    ),
    ToolDefinition(
        name="add_in_installments_transaction",
        family=FAMILY,
        description=(
            "Split one purchase across 2 to 12 monthly spreadsheet entries. The "
            "first entry uses the supplied day and later entries use day 1."
        ),
        argument_model=AddInInstallmentsTransactionArgs,
        effect=ToolEffect.MODIFY,
        can_run_concurrently=False,
    ),
    ToolDefinition(
        name="get_day_expenses",
        family=FAMILY,
        description="Read per-category expenses for one or more days in one month.",
        argument_model=DayExpensesArgs,
        effect=ToolEffect.READ,
        can_run_concurrently=True,
    ),
    ToolDefinition(
        name="get_month_expenses",
        family=FAMILY,
        description="Read category totals for one or more months.",
        argument_model=MonthExpensesArgs,
        effect=ToolEffect.READ,
        can_run_concurrently=True,
    ),
    ToolDefinition(
        name="remove_or_update_transaction",
        family=FAMILY,
        description=(
            "Remove one matching transaction or replace it with a validated new "
            "transaction."
        ),
        argument_model=RemoveOrUpdateTransactionArgs,
        effect=ToolEffect.MODIFY,
        can_run_concurrently=False,
    ),
)


def create_legacy_google_sheets_registration(
    client_factory: GoogleSheetsClientFactory,
) -> ToolFamilyRegistration:
    def build_handlers(
        context: ToolExecutionContext,
    ) -> Mapping[str, ToolHandler]:
        client = client_factory.create(context)
        legacy_user_id = client_factory.settings.LEGACY_GOOGLE_SHEETS_USER_ID
        assert legacy_user_id is not None

        async def add_one_time(args: BaseModel) -> ToolCallResult:
            _require_modify_access(context, legacy_user_id)
            return await _add_one_time_transaction(
                client,
                _require_model(args, AddOneTimeTransactionArgs),
            )

        async def add_installments(args: BaseModel) -> ToolCallResult:
            _require_modify_access(context, legacy_user_id)
            return await _add_in_installments_transaction(
                client,
                _require_model(args, AddInInstallmentsTransactionArgs),
            )

        async def get_day(args: BaseModel) -> ToolCallResult:
            context.require_family(FAMILY)
            return await _get_day_expenses(
                client,
                _require_model(args, DayExpensesArgs),
            )

        async def get_month(args: BaseModel) -> ToolCallResult:
            context.require_family(FAMILY)
            return await _get_month_expenses(
                client,
                _require_model(args, MonthExpensesArgs),
            )

        async def remove_or_update(args: BaseModel) -> ToolCallResult:
            _require_modify_access(context, legacy_user_id)
            return await _remove_or_update_transaction(
                client,
                _require_model(args, RemoveOrUpdateTransactionArgs),
            )

        return {
            "add_one_time_transaction": add_one_time,
            "add_in_installments_transaction": add_installments,
            "get_day_expenses": get_day,
            "get_month_expenses": get_month,
            "remove_or_update_transaction": remove_or_update,
        }

    return ToolFamilyRegistration(
        family=FAMILY,
        instructions=SHARED_INSTRUCTIONS,
        definitions=DEFINITIONS,
        handler_factory=build_handlers,
    )


async def _add_one_time_transaction(
    client: GoogleSheetsClient,
    args: AddOneTimeTransactionArgs,
) -> ToolCallResult:
    cell = f"{args.category}{args.day + 1}"
    month_string = MONTH_SHEET_MAPPING[args.month]
    old_formula = await client.get_formula(sheet_name=month_string, cell=cell)
    new_formula = client.build_updated_formula(
        old_formula=old_formula,
        amount=args.amount,
        refund=args.is_refund,
    )
    await client.update_formula(
        sheet_name=month_string,
        cell=cell,
        formula=new_formula,
    )
    return ToolCallResult(
        called_tool_name="add_one_time_transaction",
        result={
            "ok": True,
            "sheet_modified": month_string,
            "cell": cell,
            "category": args.category,
            "amount": args.amount,
            "was_refund": args.is_refund,
            "old_formula": old_formula,
            "new_formula": new_formula,
        },
    )


async def _add_in_installments_transaction(
    client: GoogleSheetsClient,
    args: AddInInstallmentsTransactionArgs,
) -> ToolCallResult:
    installment_amount = args.amount / args.installments
    updated_cells: list[Mapping[str, object]] = []
    for month_offset in range(args.installments):
        remaining_installments = args.installments - month_offset
        absolute_month_index = args.month - 1 + month_offset
        target_month = (absolute_month_index % 12) + 1
        target_spreadsheet: TargetYear = (
            "next_year" if absolute_month_index >= 12 else "current_year"
        )
        target_day = args.day if month_offset == 0 else 1
        cell = f"{args.category}{target_day + 1}"
        amount_formula = (
            f"({installment_amount:.2f} * "
            f"{remaining_installments} / {remaining_installments})"
        )
        sheet_name = MONTH_SHEET_MAPPING[target_month]
        old_formula = await client.get_formula(
            sheet_name=sheet_name,
            cell=cell,
            target_spreadsheet=target_spreadsheet,
        )
        new_formula = client.build_updated_formula(
            old_formula=old_formula,
            amount=amount_formula,
            refund=False,
        )
        await client.update_formula(
            sheet_name=sheet_name,
            cell=cell,
            formula=new_formula,
            target_spreadsheet=target_spreadsheet,
        )
        updated_cells.append(
            {
                "spreadsheet_year": target_spreadsheet,
                "spreadsheet_month": target_month,
                "day_updated": target_day,
                "installment_amount": f"{installment_amount:.2f}",
                "installment_number": month_offset + 1,
            },
        )

    return ToolCallResult(
        called_tool_name="add_in_installments_transaction",
        result={
            "ok": True,
            "category": args.category,
            "updated_cells": updated_cells,
        },
    )


async def _get_day_expenses(
    client: GoogleSheetsClient,
    args: DayExpensesArgs,
) -> ToolCallResult:
    days = sorted(set(args.days))
    sheet_name = MONTH_SHEET_MAPPING[args.month]
    ranges = [_day_range_name(sheet_name=sheet_name, day=day) for day in days]
    formulas = await client.get_values_for_ranges(
        ranges=ranges,
        render_option=ValueRenderOption.formula,
    )
    values = await client.get_values_for_ranges(
        ranges=ranges,
        render_option=ValueRenderOption.unformatted,
    )
    day_expenses = [
        _day_expenses_from_rows(
            client=client,
            formula_row=_first_formula_row(_range_at(formulas, index)),
            value_row=_first_value_row(_range_at(values, index)),
            day=day,
        )
        for index, day in enumerate(days)
    ]
    return ToolCallResult(
        called_tool_name="get_day_expenses",
        result={
            "ok": True,
            "month": args.month,
            "sheet": sheet_name,
            "days": [expenses.model_dump() for expenses in day_expenses],
        },
    )


async def _get_month_expenses(
    client: GoogleSheetsClient,
    args: MonthExpensesArgs,
) -> ToolCallResult:
    months = sorted(set(args.months))
    ranges = [_month_range_name(month=month) for month in months]
    values = await client.get_values_for_ranges(
        ranges=ranges,
        render_option=ValueRenderOption.unformatted,
    )
    month_expenses = [
        _month_expenses_from_rows(
            sheet=MONTH_SHEET_MAPPING[month],
            value_rows=_range_at(values, index),
        )
        for index, month in enumerate(months)
    ]
    return ToolCallResult(
        called_tool_name="get_month_expenses",
        result={
            "ok": True,
            "months": [expenses.model_dump() for expenses in month_expenses],
        },
    )


async def _remove_or_update_transaction(
    client: GoogleSheetsClient,
    args: RemoveOrUpdateTransactionArgs,
) -> ToolCallResult:
    removal = await _transaction_removal(
        client=client,
        old_transaction=args.old_transaction,
    )
    if not removal.removed:
        return _not_found_result(removal)
    updates = await _transaction_updates(
        client=client,
        removal=removal,
        new_transaction=args.new_transaction,
    )
    return _transaction_update_result(
        old_transaction=args.old_transaction,
        new_transaction=args.new_transaction,
        duplicate_matches=removal.duplicate_matches,
        updates=updates,
    )


async def _transaction_removal(
    *,
    client: GoogleSheetsClient,
    old_transaction: Transaction,
) -> TransactionRemoval:
    location = _transaction_location(old_transaction)
    old_formula = await client.get_formula(
        sheet_name=location.sheet_name,
        cell=location.cell,
    )
    removal_result = client.build_formula_without_amount(
        old_formula=old_formula,
        amount=_signed_amount(old_transaction),
    )
    return TransactionRemoval(
        old_transaction=old_transaction,
        location=location,
        old_formula=old_formula,
        formula_after_removal=removal_result.formula,
        removed=removal_result.removed,
        duplicate_matches=removal_result.duplicate_matches,
    )


async def _transaction_updates(
    *,
    client: GoogleSheetsClient,
    removal: TransactionRemoval,
    new_transaction: Transaction | None,
) -> list[FormulaUpdate]:
    if new_transaction is None:
        return [
            await _update_formula(
                client=client,
                location=removal.location,
                old_formula=removal.old_formula,
                new_formula=removal.formula_after_removal,
            ),
        ]

    new_location = _transaction_location(new_transaction)
    if removal.location == new_location:
        return [
            await _same_cell_update(
                client=client,
                removal=removal,
                new_transaction=new_transaction,
            ),
        ]
    return await _moved_transaction_updates(
        client=client,
        removal=removal,
        new_transaction=new_transaction,
        new_location=new_location,
    )


async def _same_cell_update(
    *,
    client: GoogleSheetsClient,
    removal: TransactionRemoval,
    new_transaction: Transaction,
) -> FormulaUpdate:
    final_formula = client.build_updated_formula(
        old_formula=removal.formula_after_removal,
        amount=new_transaction.amount,
        refund=new_transaction.is_refund,
    )
    return await _update_formula(
        client=client,
        location=removal.location,
        old_formula=removal.old_formula,
        new_formula=final_formula,
    )


async def _moved_transaction_updates(
    *,
    client: GoogleSheetsClient,
    removal: TransactionRemoval,
    new_transaction: Transaction,
    new_location: TransactionLocation,
) -> list[FormulaUpdate]:
    removal_update = await _update_formula(
        client=client,
        location=removal.location,
        old_formula=removal.old_formula,
        new_formula=removal.formula_after_removal,
    )
    old_new_formula = await client.get_formula(
        sheet_name=new_location.sheet_name,
        cell=new_location.cell,
    )
    final_new_formula = client.build_updated_formula(
        old_formula=old_new_formula,
        amount=new_transaction.amount,
        refund=new_transaction.is_refund,
    )
    new_update = await _update_formula(
        client=client,
        location=new_location,
        old_formula=old_new_formula,
        new_formula=final_new_formula,
    )
    return [removal_update, new_update]


async def _update_formula(
    *,
    client: GoogleSheetsClient,
    location: TransactionLocation,
    old_formula: str,
    new_formula: str,
) -> FormulaUpdate:
    await client.update_formula(
        sheet_name=location.sheet_name,
        cell=location.cell,
        formula=new_formula,
    )
    return FormulaUpdate(
        sheet_modified=location.sheet_name,
        cell=location.cell,
        old_formula=old_formula,
        new_formula=new_formula,
    )


def _day_expenses_from_rows(
    *,
    client: GoogleSheetsClient,
    formula_row: list[str],
    value_row: list[object],
    day: int,
) -> DayExpenses:
    transactions: list[TransactionEntry] = []
    for column_index, category in enumerate(CATEGORY_COLUMNS):
        formula = _formula_at(formula_row, column_index)
        amount = client.formula_total(formula)
        if amount:
            transactions.append(
                TransactionEntry(
                    category=category,
                    day=day,
                    amount=amount,
                    formula=formula,
                ),
            )
    return DayExpenses(
        day=day,
        transactions=transactions,
        total=_row_total(value_row),
    )


def _month_expenses_from_rows(
    *,
    sheet: str,
    value_rows: list[list[object]],
) -> MonthExpenses:
    total_row = _first_value_row(value_rows)
    return MonthExpenses(
        sheet=sheet,
        category_totals=_category_totals_from_row(total_row),
        total=_row_total(total_row),
    )


def _category_totals_from_row(row: list[object]) -> Mapping[str, int | float]:
    totals: dict[str, int | float] = {}
    for column_index, category in enumerate(CATEGORY_COLUMNS):
        total = _amount_from_value(_value_at(row, column_index))
        if total:
            totals[category] = total
    return totals


def _day_range_name(*, sheet_name: str, day: int) -> str:
    row = day + 1
    return f"'{sheet_name}'!{CATEGORY_COLUMNS[0]}{row}:{TOTAL_COLUMN}{row}"


def _month_range_name(*, month: int) -> str:
    sheet_name = MONTH_SHEET_MAPPING[month]
    return (
        f"'{sheet_name}'!"
        f"{CATEGORY_COLUMNS[0]}{FINAL_TOTAL_ROW}:{TOTAL_COLUMN}{FINAL_TOTAL_ROW}"
    )


def _range_at(
    ranges: list[list[list[object]]],
    index: int,
) -> list[list[object]]:
    return ranges[index] if index < len(ranges) else []


def _first_formula_row(rows: list[list[object]]) -> list[str]:
    return [str(value or "") for value in _first_value_row(rows)]


def _first_value_row(rows: list[list[object]]) -> list[object]:
    return rows[0] if rows else []


def _formula_at(row: list[str], index: int) -> str:
    return row[index] if index < len(row) else ""


def _value_at(row: list[object], index: int) -> object:
    return row[index] if index < len(row) else 0


def _row_total(row: list[object]) -> int | float:
    return _amount_from_value(_value_at(row, len(CATEGORY_COLUMNS)))


def _amount_from_value(value: object) -> int | float:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    if isinstance(value, str) and value.strip():
        number = float(value)
        return int(number) if number.is_integer() else number
    return 0


def _transaction_location(transaction: Transaction) -> TransactionLocation:
    return TransactionLocation(
        sheet_name=MONTH_SHEET_MAPPING[transaction.month],
        cell=f"{transaction.category}{transaction.day + 1}",
    )


def _signed_amount(transaction: Transaction) -> int:
    return -transaction.amount if transaction.is_refund else transaction.amount


def _not_found_result(removal: TransactionRemoval) -> ToolCallResult:
    return ToolCallResult(
        called_tool_name="remove_or_update_transaction",
        result={
            "ok": False,
            "reason": "No matching transaction amount was found.",
            "old_transaction": removal.old_transaction.model_dump(),
            "previous_cell": removal.location.cell,
            "previous_formula": removal.old_formula,
        },
    )


def _transaction_update_result(
    *,
    old_transaction: Transaction,
    new_transaction: Transaction | None,
    duplicate_matches: int,
    updates: list[FormulaUpdate],
) -> ToolCallResult:
    return ToolCallResult(
        called_tool_name="remove_or_update_transaction",
        result={
            "ok": True,
            "old_transaction": old_transaction.model_dump(),
            "new_transaction": (
                new_transaction.model_dump() if new_transaction is not None else None
            ),
            "duplicate_matches": duplicate_matches,
            "note": (
                "Only the first matching transaction amount was removed."
                if duplicate_matches > 1
                else None
            ),
            "updates": [update.model_dump() for update in updates],
        },
    )


def _require_modify_access(
    context: ToolExecutionContext,
    legacy_user_id: UUID,
) -> None:
    context.require_family(FAMILY)
    if context.user_id != legacy_user_id:
        raise ToolAccessDeniedError("Google Sheets access is not authorized.")


def _require_model(value: BaseModel, expected: type[ModelT]) -> ModelT:
    if not isinstance(value, expected):
        raise TypeError("Validated tool arguments do not match the tool definition.")
    return value
