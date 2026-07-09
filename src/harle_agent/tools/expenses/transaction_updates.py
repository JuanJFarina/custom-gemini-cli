from typing import Any

from harle_agent.models import HarleTool, HarleToolResult

from .utils import (
    MONTH_SHEET_MAPPING,
    GoogleSheetsClient,
    RemoveOrUpdateTransactionArgs,
    Transaction,
)


async def remove_or_update_transaction(args: dict[str, Any]) -> HarleToolResult:  # pylint: disable=too-many-locals
    sheets_client = GoogleSheetsClient()
    validated_args = RemoveOrUpdateTransactionArgs(**args)
    previous_transaction = validated_args.previous_transaction
    new_transaction = validated_args.new_transaction

    previous_sheet = MONTH_SHEET_MAPPING[previous_transaction.month]
    previous_cell = _transaction_cell(previous_transaction)
    old_previous_formula = await sheets_client.get_formula(
        sheet_name=previous_sheet,
        cell=previous_cell,
    )
    removal_result = sheets_client.build_formula_without_amount(
        old_formula=old_previous_formula,
        amount=previous_transaction.amount,
    )
    if not removal_result.removed:
        return HarleToolResult(
            called_tool_name="remove_or_update_transaction",
            result={
                "ok": False,
                "reason": "No matching transaction amount was found.",
                "previous_transaction": previous_transaction.model_dump(),
                "previous_cell": previous_cell,
                "previous_formula": old_previous_formula,
            },
        )

    if new_transaction is None:
        await sheets_client.update_formula(
            sheet_name=previous_sheet,
            cell=previous_cell,
            formula=removal_result.formula,
        )
        return _result(
            previous_transaction=previous_transaction,
            new_transaction=None,
            duplicate_matches=removal_result.duplicate_matches,
            updates=[
                {
                    "sheet_modified": previous_sheet,
                    "cell": previous_cell,
                    "old_formula": old_previous_formula,
                    "new_formula": removal_result.formula,
                },
            ],
        )

    new_sheet = MONTH_SHEET_MAPPING[new_transaction.month]
    new_cell = _transaction_cell(new_transaction)
    same_cell = previous_sheet == new_sheet and previous_cell == new_cell

    if same_cell:
        final_formula = sheets_client.build_updated_formula(
            old_formula=removal_result.formula,
            amount=new_transaction.amount,
            refund=False,
        )
        await sheets_client.update_formula(
            sheet_name=previous_sheet,
            cell=previous_cell,
            formula=final_formula,
        )
        updates = [
            {
                "sheet_modified": previous_sheet,
                "cell": previous_cell,
                "old_formula": old_previous_formula,
                "new_formula": final_formula,
            },
        ]
    else:
        await sheets_client.update_formula(
            sheet_name=previous_sheet,
            cell=previous_cell,
            formula=removal_result.formula,
        )
        old_new_formula = await sheets_client.get_formula(
            sheet_name=new_sheet,
            cell=new_cell,
        )
        final_new_formula = sheets_client.build_updated_formula(
            old_formula=old_new_formula,
            amount=new_transaction.amount,
            refund=False,
        )
        await sheets_client.update_formula(
            sheet_name=new_sheet,
            cell=new_cell,
            formula=final_new_formula,
        )
        updates = [
            {
                "sheet_modified": previous_sheet,
                "cell": previous_cell,
                "old_formula": old_previous_formula,
                "new_formula": removal_result.formula,
            },
            {
                "sheet_modified": new_sheet,
                "cell": new_cell,
                "old_formula": old_new_formula,
                "new_formula": final_new_formula,
            },
        ]

    return _result(
        previous_transaction=previous_transaction,
        new_transaction=new_transaction,
        duplicate_matches=removal_result.duplicate_matches,
        updates=updates,
    )


def _transaction_cell(transaction: Transaction) -> str:
    return f"{transaction.category}{transaction.day + 1}"


def _result(
    *,
    previous_transaction: Transaction,
    new_transaction: Transaction | None,
    duplicate_matches: int,
    updates: list[dict[str, Any]],
) -> HarleToolResult:
    return HarleToolResult(
        called_tool_name="remove_or_update_transaction",
        result={
            "ok": True,
            "previous_transaction": previous_transaction.model_dump(),
            "new_transaction": (
                new_transaction.model_dump() if new_transaction is not None else None
            ),
            "duplicate_matches": duplicate_matches,
            "note": (
                "Only the first matching transaction amount was removed."
                if duplicate_matches > 1
                else None
            ),
            "updates": updates,
        },
    )


REMOVE_OR_UPDATE_TRANSACTION_PROMPT = """
## "remove_or_update_transaction" tool

- Tool for removing or updating one existing transaction in the expenses spreadsheet.
- This tool removes one matching positive amount from the previous transaction's day/category cell.
- If "new_transaction" is provided, the tool adds that new transaction after removing the previous one.
- If multiple equal amounts exist in the same cell, the tool removes the first matching amount.
- Args:
  - "previous_transaction": Object with "amount", "category", "month", and "day".
  - "new_transaction": Object with "amount", "category", "month", and "day", or null to only remove the transaction.
- Example for changing a transaction from July 5th category "E" to July 6th category "G":
{
  "previous_transaction": {
    "amount": 10000,
    "category": "E",
    "month": 7,
    "day": 5
  },
  "new_transaction": {
    "amount": 10000,
    "category": "G",
    "month": 7,
    "day": 6
  }
}"""


REMOVE_OR_UPDATE_TRANSACTION_TOOL = HarleTool(
    name="remove_or_update_transaction",
    func=remove_or_update_transaction,
    prompt=REMOVE_OR_UPDATE_TRANSACTION_PROMPT,
)
