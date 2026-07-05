from datetime import datetime
from typing import Any

from pydantic import Field

from harle_agent.environment_knowledge import ROSARIO_TIMEZONE
from harle_agent.models import HarleTool, HarleToolResult

from .utils import (
    MONTH_SHEET_MAPPING,
    GoogleSheetsClient,
    TargetYear,
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
    installment_amount = validated_args.amount / validated_args.installments
    updated_cells: list[dict[str, Any]] = []

    for month_offset in range(validated_args.installments):
        remaining_installments = validated_args.installments - month_offset
        absolute_month_index = validated_args.month - 1 + month_offset
        target_month = (absolute_month_index % 12) + 1
        target_spreadsheet: TargetYear = (
            "next_year" if absolute_month_index >= 12 else "current_year"
        )
        target_day = validated_args.day if month_offset == 0 else 1
        cell = f"{validated_args.category}{target_day + 1}"
        amount_formula = (
            f"({installment_amount:.2f} * "
            f"{remaining_installments} / {remaining_installments})"
        )

        old_formula = await sheets_client.get_formula(
            sheet_name=MONTH_SHEET_MAPPING[target_month],
            cell=cell,
            target_spreadsheet=target_spreadsheet,
        )
        new_formula = sheets_client.build_updated_formula(
            old_formula=old_formula,
            amount=amount_formula,
            refund=False,
        )
        await sheets_client.update_formula(
            sheet_name=MONTH_SHEET_MAPPING[target_month],
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

    return HarleToolResult(
        called_tool_name="add_in_installments_transaction",
        result={
            "ok": True,
            "category": args["category"],
            "updated_cells": updated_cells,
        },
    )


ADD_IN_INSTALLMENTS_TRANSACTION_PROMPT = """
## "add_in_installments_transaction" tool

- Tool for adding a fixed installments transaction to the expenses spreadsheet.
- This tool will update each month where an installment is to be paid, using the specific day of the transaction for the first installment, and using the 1st day of the month for the rest of the installments.
- Args:
  - "amount": Positive integer that represents the total amount of the transaction in Argentine pesos.
  - "installments": Integer number of monthly installments, from 2 to 12.
  - "category": String of one of the valid categories.
  - "month": Integer of the first month of the transaction, from 1 to 12. Will default to current month if not provided.
  - "day": Integer of the day of the transaction, from 1 to 31. Will default to current day if not provided.
- Example for all args for buying a 100000 videogame in 3 installments on July 5th:
{
  "amount": 100000,
  "installments": 3,
  "category": "H",
  "month": 7,
  "day": 5
}"""


ADD_IN_INSTALLMENTS_TRANSACTION_TOOL = HarleTool(
    name="add_in_installments_transaction",
    func=add_in_installments_transaction,
    prompt=ADD_IN_INSTALLMENTS_TRANSACTION_PROMPT,
)
