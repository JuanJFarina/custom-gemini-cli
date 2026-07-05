from datetime import datetime
from typing import Any

from harle_agent.environment_knowledge import ROSARIO_TIMEZONE
from harle_agent.models import HarleTool, HarleToolResult

from .utils import (
    MONTH_SHEET_MAPPING,
    GoogleSheetsClient,
    TransactionArgs,
)


class AddOneTimeTransactionArgs(TransactionArgs):
    is_refund: bool = False

    @classmethod
    def from_args(cls, args: dict[str, Any]) -> "AddOneTimeTransactionArgs":
        return cls(
            amount=args["amount"],
            category=args["category"],
            month=args.get("month") or datetime.now(ROSARIO_TIMEZONE).month,
            day=args.get("day") or datetime.now(ROSARIO_TIMEZONE).day,
            is_refund=args.get("is_refund", False),
        )


async def add_one_time_transaction(args: dict[str, Any]) -> HarleToolResult:
    sheets_client = GoogleSheetsClient()
    validated_args = AddOneTimeTransactionArgs.from_args(args)
    cell = f"{validated_args.category}{validated_args.day + 1}"
    month_string = MONTH_SHEET_MAPPING[validated_args.month]

    old_formula = await sheets_client.get_formula(
        sheet_name=month_string,
        cell=cell,
    )
    new_formula = sheets_client.build_updated_formula(
        old_formula=old_formula,
        amount=validated_args.amount,
        refund=validated_args.is_refund,
    )
    await sheets_client.update_formula(
        sheet_name=month_string,
        cell=cell,
        formula=new_formula,
    )

    return HarleToolResult(
        called_tool_name="add_one_time_transaction",
        result={
            "ok": True,
            "sheet_modified": month_string,
            "cell": cell,
            "category": args["category"],
            "amount": validated_args.amount,
            "was_refund": validated_args.is_refund,
            "old_formula": old_formula,
            "new_formula": new_formula,
        },
    )


ADD_ONE_TIME_TRANSACTION_PROMPT = """
## "add_one_time_transaction" tool

- Tool for adding a one-time pay/refund transaction to the expenses spreadsheet.
- Args:
  - "amount": Positive integer that represents the amount of the transaction in Argentine pesos.
  - "category": String of one of the valid categories.
  - "month": Integer of the month of the transaction, from 1 to 12. Will default to current month if not provided.
  - "day": Integer of the day of the transaction, from 1 to 31. Will default to current day if not provided.
  - "is_refund": Boolean of whether the transaction is a refund or negative adjustment. Will default to false (not a refund) if not provided.
- Valid category strings:
  - "B": For all fees related to rent and building (spreadsheet column name: "alquileres").
  - "C": For all fees related to essential services like electricity, gas, water, healthcare, etc. (spreadsheet column name: "servicios_esenciales").
  - "D": For all fees related to non-essential services like streaming, gym, subscriptions, etc. (spreadsheet column name: "servicios_no_esenciales").
  - "E": For all fees related to consumable items inside the house like groceries, food, cleaning, etc. (spreadsheet column name: "hogar").
  - "F": For all fees related to transportation like taxi, Uber, buses, fuel, parking, etc. (spreadsheet column name: "transporte").
  - "G": For all fees related to out-of-the-house consumables and entertainment like restaurants, bars, cinema, outings, etc. (spreadsheet column name: "salidas").
  - "H": For all fees related to long-term buys like clothes, electronics, games, books, shopping, etc. (spreadsheet column name: "shopping").
  - "I": For anything that doesn't fit into the other categories. (spreadsheet column name: "otros").
- Example for all args for paying rent on July 5th:
{
  "amount": 500000,
  "category": "B",
  "month": 7,
  "day": 5,
  "is_refund": false
}
"""


ADD_ONE_TIME_TRANSACTION_TOOL = HarleTool(
    name="add_one_time_transaction",
    func=add_one_time_transaction,
    prompt=ADD_ONE_TIME_TRANSACTION_PROMPT,
)
