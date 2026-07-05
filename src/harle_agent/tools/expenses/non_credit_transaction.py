from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from harle_agent.models import HarleTool, HarleToolResult
from harle_agent.runtime_context import ROSARIO_TIMEZONE

from .cons import (
    ADD_NON_CREDIT_TRANSACTION_PROMPT,
    MONTH_SHEET_MAPPING,
    SIMPLE_FORMULA_PATTERN,
)
from .google_sheets import GoogleSheetsClient


class AddNonCreditTransactionArgs(BaseModel):
    amount: int = Field(gt=0)
    category: str = Field(
        description="The category of the transaction.",
        pattern=r"^(B|C|D|E|F|G|H|I)$",
    )
    month: int = Field(
        description="The month of the transaction, from 1 to 12.",
        ge=1,
        le=12,
    )
    day: int = Field(
        description="The day of the transaction, from 1 to 31.",
        ge=1,
        le=31,
    )
    is_refund: bool = False

    @classmethod
    def from_args(cls, args: dict[str, Any]) -> "AddNonCreditTransactionArgs":
        return cls(
            amount=int(args["amount"]),
            category=args["category"],
            month=args.get("month") or datetime.now(ROSARIO_TIMEZONE).month,
            day=args.get("day") or datetime.now(ROSARIO_TIMEZONE).day,
            is_refund=args.get("is_refund", False),
        )


async def add_non_credit_transaction(args: dict[str, Any]) -> HarleToolResult:
    sheets_client = GoogleSheetsClient()
    validated_args = AddNonCreditTransactionArgs.from_args(args)
    cell = f"{validated_args.category}{validated_args.day + 1}"
    month_string = MONTH_SHEET_MAPPING[validated_args.month]

    old_formula = await sheets_client.get_formula(
        sheet_name=month_string,
        cell=cell,
    )
    new_formula = build_updated_formula(
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
        called_tool_name="add_non_credit_transaction",
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


def build_updated_formula(*, old_formula: str, amount: int, refund: bool) -> str:
    formula = old_formula.strip()
    if formula == "":
        formula = "=0"

    if not SIMPLE_FORMULA_PATTERN.fullmatch(formula):
        raise ValueError(f"Cell formula is not a simple expense formula: {formula}")

    if formula == "=0":
        return f"=-{amount}" if refund else f"={amount}"

    operator = "-" if refund else "+"
    return f"{formula}{operator}{amount}"


ADD_NON_CREDIT_TRANSACTION_TOOL = HarleTool(
    name="add_non_credit_transaction",
    func=add_non_credit_transaction,
    prompt=ADD_NON_CREDIT_TRANSACTION_PROMPT,
)
