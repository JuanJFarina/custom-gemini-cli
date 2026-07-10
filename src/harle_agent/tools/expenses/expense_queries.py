from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from harle_agent.models import HarleTool, HarleToolResult

from .utils import (
    CATEGORY_COLUMNS,
    MONTH_SHEET_MAPPING,
    TOTAL_COLUMN,
    DayExpensesArgs,
    GoogleSheetsClient,
    MonthExpensesArgs,
)

FIRST_DAY_ROW = 2
LAST_DAY_ROW = 32
FINAL_TOTAL_ROW = LAST_DAY_ROW + 1
EXPENSES_TIMEZONE = timezone(timedelta(hours=-3), name="ART")


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
    category_totals: dict[str, int | float]
    days: list[DayExpenses]
    total: int | float


async def get_day_expenses(args: Mapping[str, object] | None = None) -> HarleToolResult:
    args = args or {}
    sheets_client = GoogleSheetsClient()
    today = _current_expenses_date()
    validated_args = DayExpensesArgs(
        day=args.get("day", today.day),
        month=args.get("month", today.month),
    )
    sheet_name = MONTH_SHEET_MAPPING[validated_args.month]
    row_number = validated_args.day + 1
    formulas = await sheets_client.get_formulas(
        sheet_name=sheet_name,
        range_name=f"{CATEGORY_COLUMNS[0]}{row_number}:{TOTAL_COLUMN}{row_number}",
    )
    values = await sheets_client.get_values(
        sheet_name=sheet_name,
        range_name=f"{CATEGORY_COLUMNS[0]}{row_number}:{TOTAL_COLUMN}{row_number}",
    )
    day_expenses = _day_expenses_from_rows(
        sheets_client=sheets_client,
        formula_row=_first_formula_row(formulas),
        value_row=_first_value_row(values),
        day=validated_args.day,
    )

    return HarleToolResult(
        called_tool_name="get_day_expenses",
        result={
            "ok": True,
            "month": validated_args.month,
            "sheet": sheet_name,
            **day_expenses.model_dump(),
        },
    )


async def get_month_expenses(
    args: Mapping[str, object] | None = None,
) -> HarleToolResult:
    args = args or {}
    sheets_client = GoogleSheetsClient()
    today = _current_expenses_date()
    validated_args = MonthExpensesArgs(month=args.get("month", today.month))
    sheet_name = MONTH_SHEET_MAPPING[validated_args.month]
    formulas = await sheets_client.get_formulas(
        sheet_name=sheet_name,
        range_name=(
            f"{CATEGORY_COLUMNS[0]}{FIRST_DAY_ROW}:{CATEGORY_COLUMNS[-1]}{LAST_DAY_ROW}"
        ),
    )
    values = await sheets_client.get_values(
        sheet_name=sheet_name,
        range_name=(
            f"{CATEGORY_COLUMNS[0]}{FIRST_DAY_ROW}:{TOTAL_COLUMN}{FINAL_TOTAL_ROW}"
        ),
    )
    month_expenses = _month_expenses_from_rows(
        sheets_client=sheets_client,
        formula_rows=formulas,
        value_rows=values,
    )

    return HarleToolResult(
        called_tool_name="get_month_expenses",
        result={
            "ok": True,
            "month": validated_args.month,
            "sheet": sheet_name,
            **month_expenses.model_dump(),
        },
    )


def _day_expenses_from_rows(
    *,
    sheets_client: GoogleSheetsClient,
    formula_row: list[str],
    value_row: list[object],
    day: int,
) -> DayExpenses:
    transactions: list[TransactionEntry] = []
    for column_index, category in enumerate(CATEGORY_COLUMNS):
        formula = _formula_at(formula_row, column_index)
        amount = sheets_client.formula_total(formula)
        if not amount:
            continue

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
    sheets_client: GoogleSheetsClient,
    formula_rows: list[list[str]],
    value_rows: list[list[object]],
) -> MonthExpenses:
    days: list[DayExpenses] = []
    for row_index, formula_row in enumerate(formula_rows):
        day_expenses = _day_expenses_from_rows(
            sheets_client=sheets_client,
            formula_row=formula_row,
            value_row=_value_row_at(value_rows, row_index),
            day=row_index + 1,
        )
        if day_expenses.transactions or day_expenses.total:
            days.append(day_expenses)

    total_row = _value_row_at(
        value_rows,
        FINAL_TOTAL_ROW - FIRST_DAY_ROW,
    )
    return MonthExpenses(
        category_totals=_category_totals_from_row(total_row),
        days=days,
        total=_row_total(total_row),
    )


def _category_totals_from_row(row: list[object]) -> dict[str, int | float]:
    totals: dict[str, int | float] = {}
    for column_index, category in enumerate(CATEGORY_COLUMNS):
        total = _amount_from_value(_value_at(row, column_index))
        if total:
            totals[category] = total
    return totals


def _first_formula_row(rows: list[list[str]]) -> list[str]:
    return rows[0] if rows else []


def _first_value_row(rows: list[list[object]]) -> list[object]:
    return _value_row_at(rows, 0)


def _value_row_at(rows: list[list[object]], index: int) -> list[object]:
    return rows[index] if index < len(rows) else []


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


def _current_expenses_date() -> datetime:
    return datetime.now(EXPENSES_TIMEZONE)


GET_DAY_EXPENSES_PROMPT = """
## "get_day_expenses" tool

- Tool for reading all the transactions for one day from the expenses spreadsheet.
- Args:
  - "day": Optional integer of the day to read, from 1 to 31. Defaults to the current day.
  - "month": Optional integer of the month to read, from 1 to 12. Defaults to the current month.
- Example:
{
  "day": 5,
  "month": 7
}
- No args example:
{}"""


GET_MONTH_EXPENSES_PROMPT = """
## "get_month_expenses" tool

- Tool for reading all the transactions for one entire month from the expenses spreadsheet.
- Args:
  - "month": Optional integer of the month to read, from 1 to 12. Defaults to the current month.
- Example:
{
  "month": 7
}
- No args example:
{}"""


GET_DAY_EXPENSES_TOOL = HarleTool(
    name="get_day_expenses",
    func=get_day_expenses,
    prompt=GET_DAY_EXPENSES_PROMPT,
)


GET_MONTH_EXPENSES_TOOL = HarleTool(
    name="get_month_expenses",
    func=get_month_expenses,
    prompt=GET_MONTH_EXPENSES_PROMPT,
)
