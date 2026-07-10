from datetime import datetime, timedelta, timezone
from typing import Any

from harle_agent.models import HarleTool, HarleToolResult

from .utils import (
    CATEGORY_COLUMNS,
    MONTH_SHEET_MAPPING,
    DayExpensesArgs,
    GoogleSheetsClient,
    MonthExpensesArgs,
)

FIRST_DAY_ROW = 2
LAST_DAY_ROW = 32
EXPENSES_TIMEZONE = timezone(timedelta(hours=-3), name="ART")


async def get_day_expenses(args: dict[str, Any] | None = None) -> HarleToolResult:
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
        range_name=f"{CATEGORY_COLUMNS[0]}{row_number}:{CATEGORY_COLUMNS[-1]}{row_number}",
    )
    row = formulas[0] if formulas else []
    expenses = _expense_entries_from_row(
        sheets_client=sheets_client,
        row=row,
        day=validated_args.day,
    )

    return HarleToolResult(
        called_tool_name="get_day_expenses",
        result={
            "ok": True,
            "month": validated_args.month,
            "sheet": sheet_name,
            "day": validated_args.day,
            "expenses": expenses,
            "total": _sum_expenses(expenses),
        },
    )


async def get_month_expenses(args: dict[str, Any] | None = None) -> HarleToolResult:  # pylint: disable=too-many-locals
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

    category_totals = {category: 0 for category in CATEGORY_COLUMNS}
    days: list[dict[str, Any]] = []

    for row_index, row in enumerate(formulas):
        day = row_index + 1
        expenses = _expense_entries_from_row(
            sheets_client=sheets_client,
            row=row,
            day=day,
        )
        if not expenses:
            continue

        day_total = _sum_expenses(expenses)
        for expense in expenses:
            category = str(expense["category"])
            category_totals[category] += expense["amount"]

        days.append(
            {
                "day": day,
                "expenses": expenses,
                "total": day_total,
            },
        )

    non_empty_category_totals = {
        category: total for category, total in category_totals.items() if total
    }

    return HarleToolResult(
        called_tool_name="get_month_expenses",
        result={
            "ok": True,
            "month": validated_args.month,
            "sheet": sheet_name,
            "category_totals": non_empty_category_totals,
            "days": days,
            "total": sum(non_empty_category_totals.values()),
        },
    )


def _expense_entries_from_row(
    *,
    sheets_client: GoogleSheetsClient,
    row: list[str],
    day: int,
) -> list[dict[str, Any]]:
    expenses: list[dict[str, Any]] = []
    for column_index, category in enumerate(CATEGORY_COLUMNS):
        formula = row[column_index] if column_index < len(row) else ""
        amount = sheets_client.formula_total(formula)
        if not amount:
            continue

        expenses.append(
            {
                "category": category,
                "day": day,
                "amount": amount,
                "formula": formula,
            },
        )
    return expenses


def _sum_expenses(expenses: list[dict[str, Any]]) -> int | float:
    return sum(expense["amount"] for expense in expenses)


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
