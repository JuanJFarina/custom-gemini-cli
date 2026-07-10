from collections.abc import Mapping

from pydantic import BaseModel

from harle_agent.models import HarleTool, HarleToolResult

from .utils import (
    MONTH_SHEET_MAPPING,
    GoogleSheetsClient,
    RemoveOrUpdateTransactionArgs,
    Transaction,
)


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


async def remove_or_update_transaction(args: Mapping[str, object]) -> HarleToolResult:
    sheets_client = GoogleSheetsClient()
    validated_args = RemoveOrUpdateTransactionArgs(**args)
    removal = await _transaction_removal(
        sheets_client=sheets_client,
        old_transaction=validated_args.old_transaction,
    )

    if not removal.removed:
        return _not_found_result(removal)

    updates = await _transaction_updates(
        sheets_client=sheets_client,
        removal=removal,
        new_transaction=validated_args.new_transaction,
    )
    return _result(
        old_transaction=validated_args.old_transaction,
        new_transaction=validated_args.new_transaction,
        duplicate_matches=removal.duplicate_matches,
        updates=updates,
    )


async def _transaction_removal(
    *,
    sheets_client: GoogleSheetsClient,
    old_transaction: Transaction,
) -> TransactionRemoval:
    location = _transaction_location(old_transaction)
    old_formula = await sheets_client.get_formula(
        sheet_name=location.sheet_name,
        cell=location.cell,
    )
    removal_result = sheets_client.build_formula_without_amount(
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
    sheets_client: GoogleSheetsClient,
    removal: TransactionRemoval,
    new_transaction: Transaction | None,
) -> list[FormulaUpdate]:
    if new_transaction is None:
        return [
            await _update_formula(
                sheets_client=sheets_client,
                location=removal.location,
                old_formula=removal.old_formula,
                new_formula=removal.formula_after_removal,
            ),
        ]

    new_location = _transaction_location(new_transaction)
    if removal.location == new_location:
        return [
            await _same_cell_update(
                sheets_client=sheets_client,
                removal=removal,
                new_transaction=new_transaction,
            ),
        ]

    return await _moved_transaction_updates(
        sheets_client=sheets_client,
        removal=removal,
        new_transaction=new_transaction,
        new_location=new_location,
    )


async def _same_cell_update(
    *,
    sheets_client: GoogleSheetsClient,
    removal: TransactionRemoval,
    new_transaction: Transaction,
) -> FormulaUpdate:
    final_formula = sheets_client.build_updated_formula(
        old_formula=removal.formula_after_removal,
        amount=new_transaction.amount,
        refund=new_transaction.is_refund,
    )
    return await _update_formula(
        sheets_client=sheets_client,
        location=removal.location,
        old_formula=removal.old_formula,
        new_formula=final_formula,
    )


async def _moved_transaction_updates(
    *,
    sheets_client: GoogleSheetsClient,
    removal: TransactionRemoval,
    new_transaction: Transaction,
    new_location: TransactionLocation,
) -> list[FormulaUpdate]:
    removal_update = await _update_formula(
        sheets_client=sheets_client,
        location=removal.location,
        old_formula=removal.old_formula,
        new_formula=removal.formula_after_removal,
    )
    old_new_formula = await sheets_client.get_formula(
        sheet_name=new_location.sheet_name,
        cell=new_location.cell,
    )
    final_new_formula = sheets_client.build_updated_formula(
        old_formula=old_new_formula,
        amount=new_transaction.amount,
        refund=new_transaction.is_refund,
    )
    new_update = await _update_formula(
        sheets_client=sheets_client,
        location=new_location,
        old_formula=old_new_formula,
        new_formula=final_new_formula,
    )
    return [removal_update, new_update]


async def _update_formula(
    *,
    sheets_client: GoogleSheetsClient,
    location: TransactionLocation,
    old_formula: str,
    new_formula: str,
) -> FormulaUpdate:
    await sheets_client.update_formula(
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


def _transaction_location(transaction: Transaction) -> TransactionLocation:
    return TransactionLocation(
        sheet_name=MONTH_SHEET_MAPPING[transaction.month],
        cell=f"{transaction.category}{transaction.day + 1}",
    )


def _signed_amount(transaction: Transaction) -> int:
    return -transaction.amount if transaction.is_refund else transaction.amount


def _not_found_result(removal: TransactionRemoval) -> HarleToolResult:
    return HarleToolResult(
        called_tool_name="remove_or_update_transaction",
        result={
            "ok": False,
            "reason": "No matching transaction amount was found.",
            "old_transaction": removal.old_transaction.model_dump(),
            "previous_cell": removal.location.cell,
            "previous_formula": removal.old_formula,
        },
    )


def _result(
    *,
    old_transaction: Transaction,
    new_transaction: Transaction | None,
    duplicate_matches: int,
    updates: list[FormulaUpdate],
) -> HarleToolResult:
    return HarleToolResult(
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


REMOVE_OR_UPDATE_TRANSACTION_PROMPT = """
## "remove_or_update_transaction" tool

- Tool for removing or updating one existing transaction (positive or refund) in the expenses spreadsheet.
- Args:
  - "old_transaction": Object following the "Transaction" model:
    - "amount": The amount of the transaction.
    - "category": The category of the transaction.
    - "month": The month of the transaction (1-12).
    - "day": The day of the transaction (1-31).
    - "is_refund": Optional. Use "is_refund": true when the existing transaction is a refund/negative adjustment.
  - "new_transaction": Optional object following the "Transaction" model or null to only remove the transaction.
- Example for changing a regular transaction into a refund:
{
  "old_transaction": {
    "amount": 10000,
    "category": "E",
    "month": 7,
    "day": 5,
    "is_refund": false
  },
  "new_transaction": {
    "amount": 10000,
    "category": "E",
    "month": 7,
    "day": 5,
    "is_refund": true
  }
}"""


REMOVE_OR_UPDATE_TRANSACTION_TOOL = HarleTool(
    name="remove_or_update_transaction",
    func=remove_or_update_transaction,
    prompt=REMOVE_OR_UPDATE_TRANSACTION_PROMPT,
)
