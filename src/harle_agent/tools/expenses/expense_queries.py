from collections.abc import Mapping

from gspread.utils import ValueRenderOption
from pydantic import BaseModel

from harle_agent.models import HarleTool, ToolCallResult

from .utils import (
    CATEGORY_COLUMNS,
    MONTH_SHEET_MAPPING,
    TOTAL_COLUMN,
    DayExpensesArgs,
    GoogleSheetsClient,
    MonthExpensesArgs,
)

LAST_DAY_ROW = 32
FINAL_TOTAL_ROW = LAST_DAY_ROW + 1


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
    category_totals: dict[str, int | float]
    total: int | float


async def get_day_expenses(args: Mapping[str, object]) -> ToolCallResult:
    sheets_client = GoogleSheetsClient()
    validated_args = DayExpensesArgs.model_validate(args)
    days = sorted(set(validated_args.days))
    sheet_name = MONTH_SHEET_MAPPING[validated_args.month]
    ranges = [_day_range_name(sheet_name=sheet_name, day=day) for day in days]
    formulas = await sheets_client.get_values_for_ranges(
        ranges=ranges,
        render_option=ValueRenderOption.formula,
    )
    values = await sheets_client.get_values_for_ranges(
        ranges=ranges,
        render_option=ValueRenderOption.unformatted,
    )
    day_expenses = [
        _day_expenses_from_rows(
            sheets_client=sheets_client,
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
            "month": validated_args.month,
            "sheet": sheet_name,
            "days": [expenses.model_dump() for expenses in day_expenses],
        },
    )


async def get_month_expenses(args: Mapping[str, object]) -> ToolCallResult:
    sheets_client = GoogleSheetsClient()
    validated_args = MonthExpensesArgs.model_validate(args)
    months = sorted(set(validated_args.months))
    ranges = [_month_range_name(month=month) for month in months]
    values = await sheets_client.get_values_for_ranges(
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
    sheet: str,
    value_rows: list[list[object]],
) -> MonthExpenses:
    total_row = _first_value_row(value_rows)
    return MonthExpenses(
        sheet=sheet,
        category_totals=_category_totals_from_row(total_row),
        total=_row_total(total_row),
    )


def _category_totals_from_row(row: list[object]) -> dict[str, int | float]:
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


GET_DAY_EXPENSES_PROMPT = """
## "get_day_expenses" tool

- Tool for reading per-category total expenses for one or more days in the same month.
- Args:
  - "days": Array of days to read, from 1 to 31. Defaults to an array with only the current day if not provided.
  - "month": Integer of the month to read, from 1 to 12. Defaults to the current month if not provided.
- Example:
{
  "days": [5, 7],
  "month": 7
}
- No args example:
{}"""


GET_MONTH_EXPENSES_PROMPT = """
## "get_month_expenses" tool

- Tool for reading per-category totals and aggregated total amounts for one or more months.
- Args:
  - "months": Array of months to read, from 1 to 12. Defaults to an array with only the current month if not provided.
- Example:
{
  "months": [6, 7]
}
- No args example:
{}"""


GET_DAY_EXPENSES_TOOL = HarleTool(
    name="get_day_expenses",
    func=get_day_expenses,
    prompt=GET_DAY_EXPENSES_PROMPT,
    can_run_concurrently=True,
)


GET_MONTH_EXPENSES_TOOL = HarleTool(
    name="get_month_expenses",
    func=get_month_expenses,
    prompt=GET_MONTH_EXPENSES_PROMPT,
    can_run_concurrently=True,
)
