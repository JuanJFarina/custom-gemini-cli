from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from harle_agent.runtime_context import ROSARIO_TIMEZONE
from harle_agent.tools.google_sheets import (
    GoogleSheetsClient,
    load_google_sheets_settings_from_env,
)
from harle_agent.models.harle_models import HarleTool


MONTH_SHEET_NAMES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]

CATEGORY_COLUMNS = {
    "alquileres": "B",
    "servicios_esenciales": "C",
    "servicios_no_esenciales": "D",
    "hogar": "E",
    "transporte": "F",
    "salidas": "G",
    "shopping": "H",
    "otros": "I",
}

SIMPLE_FORMULA_PATTERN = re.compile(r"^=-?\d+(?:[+-]\d+)*$")

CATEGORY_GUIDANCE = """
Infer categories from English or Spanish descriptions when needed:
- rent, alquiler -> alquileres
- electricity, gas, water, utilities, luz, gas, agua, expensas -> servicios_esenciales
- subscriptions, streaming, cloud services, suscripciones -> servicios_no_esenciales
- groceries, supermarket, food at home, cleaning, supermercado, comida, limpieza -> hogar
- taxi, Uber, bus, fuel, parking, transporte, nafta, colectivo -> transporte
- restaurants, bars, cinema, outings, restaurants, bares, cine, salidas -> salidas
- clothes, electronics, games, books, shopping, ropa, electronica, juegos, libros -> shopping
- unclear, miscellaneous, other, varios, otros -> otros
"""


@dataclass(frozen=True)
class UpdateExpenseArgs:
    amount: int
    category: str
    day: int | None = None
    month: str | None = None
    refund: bool = False


class ExpenseTool:
    def __init__(self, sheets_client: GoogleSheetsClient) -> None:
        self.sheets_client = sheets_client

    async def add_non_credit_expense(self, args: dict[str, Any]) -> dict[str, Any]:
        try:
            parsed_args = _parse_args(args)
            month = _resolve_month(parsed_args.month)
            day = _resolve_day(parsed_args.day, month)
            category = _resolve_category(parsed_args.category)
            cell = _cell_for(day=day, category=category)

            old_formula = await self.sheets_client.get_formula(
                sheet_name=month,
                cell=cell,
            )
            new_formula = build_updated_formula(
                old_formula=old_formula,
                amount=parsed_args.amount,
                refund=parsed_args.refund,
            )
            await self.sheets_client.update_formula(
                sheet_name=month,
                cell=cell,
                formula=new_formula,
            )
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
            }

        return {
            "ok": True,
            "sheet": month,
            "cell": cell,
            "category": category,
            "amount": str(parsed_args.amount),
            "refund": str(parsed_args.refund),
            "old_formula": old_formula,
            "new_formula": new_formula,
        }


def build_expense_tool_from_env() -> HarleTool | None:
    settings = load_google_sheets_settings_from_env()
    if settings is None:
        return None
    expense_tool = ExpenseTool(GoogleSheetsClient(settings))
    return HarleTool(
        tool_name="add_non_credit_expense",
        tool_func=expense_tool.add_non_credit_expense,
    )


def build_updated_formula(*, old_formula: str, amount: int, refund: bool) -> str:
    _validate_amount(amount)
    formula = old_formula.strip()
    if formula == "":
        formula = "=0"

    if not SIMPLE_FORMULA_PATTERN.fullmatch(formula):
        raise ValueError(f"Cell formula is not a simple expense formula: {formula}")

    if formula == "=0":
        return f"=-{amount}" if refund else f"={amount}"

    operator = "-" if refund else "+"
    return f"{formula}{operator}{amount}"


def _parse_args(args: dict[str, Any]) -> UpdateExpenseArgs:
    return UpdateExpenseArgs(
        amount=_parse_amount(args.get("amount")),
        category=str(args.get("category") or ""),
        day=_parse_optional_int(args.get("day")),
        month=_parse_optional_str(args.get("month")),
        refund=bool(args.get("refund", False)),
    )


def _parse_amount(value: Any) -> int:
    amount = _parse_optional_int(value)
    if amount is None:
        raise ValueError("amount is required.")
    _validate_amount(amount)
    return amount


def _validate_amount(amount: int) -> None:
    if amount <= 0:
        raise ValueError("amount must be a positive integer.")


def _parse_optional_int(value: Any) -> int | None:
    if value is None:
        return None

    if isinstance(value, bool):
        raise ValueError("Expected an integer, got a boolean.")

    if isinstance(value, int):
        return value

    if isinstance(value, float) and value.is_integer():
        return int(value)

    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())

    raise ValueError(f"Expected an integer, got {value!r}.")


def _parse_optional_str(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip().lower()
    return text or None


def _resolve_month(month: str | None) -> str:
    if month is None:
        return MONTH_SHEET_NAMES[datetime.now(ROSARIO_TIMEZONE).month - 1]

    if month not in MONTH_SHEET_NAMES:
        raise ValueError(f"Invalid month: {month}")

    return month


def _resolve_day(day: int | None, month: str) -> int:
    now = datetime.now(ROSARIO_TIMEZONE)
    resolved_day = day or now.day
    month_index = MONTH_SHEET_NAMES.index(month) + 1
    _, last_day = calendar.monthrange(now.year, month_index)
    if resolved_day < 1 or resolved_day > last_day:
        raise ValueError(f"Invalid day {resolved_day} for month {month}.")

    return resolved_day


def _resolve_category(category: str) -> str:
    if category not in CATEGORY_COLUMNS:
        raise ValueError(f"Invalid category: {category}")
    return category


def _cell_for(*, day: int, category: str) -> str:
    return f"{CATEGORY_COLUMNS[category]}{day + 1}"
