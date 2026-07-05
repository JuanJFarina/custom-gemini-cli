from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import Field

from harle_agent.environment_knowledge import ROSARIO_TIMEZONE
from harle_agent.models import HarleTool, HarleToolResult

from .utils import (
    MONTH_SHEET_MAPPING,
    GoogleSheetsClient,
    TransactionArgs,
)


class AddInInstallmentsTransactionArgs(TransactionArgs):
    installments: int = Field(gt=1, le=12)

    @classmethod
    def from_args(cls, args: dict[str, Any]) -> "AddInInstallmentsTransactionArgs":
        now = datetime.now(ROSARIO_TIMEZONE)
        return cls(
            amount=args["amount"],
            installments=int(args["installments"]),
            category=args["category"],
            month=args.get("month") or now.month,
            day=args.get("day") or now.day,
        )


async def add_in_installments_transaction(args: dict[str, Any]) -> HarleToolResult:
    sheets_client = GoogleSheetsClient()
    validated_args = AddInInstallmentsTransactionArgs.from_args(args)
    installment_amount = (
        validated_args.amount / Decimal(validated_args.installments)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    updated_cells: list[dict[str, Any]] = []

    for month_offset in range(validated_args.installments):
        installment_number = month_offset + 1
        remaining_installments = validated_args.installments - month_offset
        target_month = ((validated_args.month - 1 + month_offset) % 12) + 1
        target_day = validated_args.day if month_offset == 0 else 1
        month_string = MONTH_SHEET_MAPPING[target_month]
        cell = f"{validated_args.category}{target_day + 1}"
        amount_formula = (
            f"({installment_amount} * "
            f"{remaining_installments} / {remaining_installments})"
        )

        old_formula = await sheets_client.get_formula(
            sheet_name=month_string,
            cell=cell,
        )
        new_formula = sheets_client.build_updated_formula(
            old_formula=old_formula,
            amount=amount_formula,
            refund=False,
        )
        await sheets_client.update_formula(
            sheet_name=month_string,
            cell=cell,
            formula=new_formula,
        )

        updated_cells.append(
            {
                "sheet_modified": month_string,
                "cell": cell,
                "installment_number": installment_number,
                "remaining_installments": remaining_installments,
                "old_formula": old_formula,
                "new_formula": new_formula,
            },
        )

    return HarleToolResult(
        called_tool_name="add_in_installments_transaction",
        result={
            "ok": True,
            "category": args["category"],
            "amount": str(validated_args.amount),
            "installments": validated_args.installments,
            "installment_amount": str(installment_amount),
            "updated_cells": updated_cells,
        },
    )


ADD_IN_INSTALLMENTS_TRANSACTION_PROMPT = """
## "add_in_installments_transaction" tool

- Tool for adding a fixed installments transaction to the expenses spreadsheet.
- This tool will update each month where an installment is to be paid.
- Args:
  - "amount": Positive integer that represents the total amount of the transaction in Argentine pesos.
  - "installments": Integer number of monthly installments, from 2 to 12.
  - "category": String of one of the valid categories.
  - "month": Integer of the first month of the transaction, from 1 to 12. Will default to current month if not provided.
  - "day": Integer of the day of the transaction, from 1 to 31. Will default to current day if not provided.
- Valid category strings:
  - "B": For all fees related to rent and building (spreadsheet column name: "alquileres").
  - "C": For all fees related to essential services like electricity, gas, water, healthcare, etc. (spreadsheet column name: "servicios_esenciales").
  - "D": For all fees related to non-essential services like streaming, gym, subscriptions, etc. (spreadsheet column name: "servicios_no_esenciales").
  - "E": For all fees related to consumable items inside the house like groceries, food, cleaning, etc. (spreadsheet column name: "hogar").
  - "F": For all fees related to transportation like taxi, Uber, buses, fuel, parking, etc. (spreadsheet column name: "transporte").
  - "G": For all fees related to out-of-the-house consumables and entertainment like restaurants, bars, cinema, outings, etc. (spreadsheet column name: "salidas").
  - "H": For all fees related to long-term buys like clothes, electronics, games, books, shopping, etc. (spreadsheet column name: "shopping").
  - "I": For anything that doesn't fit into the other categories. (spreadsheet column name: "otros").
- Example for all args for buying a 100000 videogame in 3 installments on July 5th:
{
  "amount": 100000,
  "installments": 3,
  "category": "H",
  "month": 7,
  "day": 5
}
"""


ADD_IN_INSTALLMENTS_TRANSACTION_TOOL = HarleTool(
    name="add_in_installments_transaction",
    func=add_in_installments_transaction,
    prompt=ADD_IN_INSTALLMENTS_TRANSACTION_PROMPT,
)
