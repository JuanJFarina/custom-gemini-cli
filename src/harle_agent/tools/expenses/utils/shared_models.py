from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from harle_agent.environment_knowledge import ROSARIO_TIMEZONE

DayNumber = Annotated[int, Field(ge=1, le=31)]
MonthNumber = Annotated[int, Field(ge=1, le=12)]


class TransactionArgs(BaseModel):
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


class Transaction(TransactionArgs):
    is_refund: bool = False


class DayExpensesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: list[DayNumber] = Field(
        default_factory=lambda: [datetime.now(ROSARIO_TIMEZONE).day],
        description="Day or days of the expenses query, from 1 to 31.",
        min_length=1,
        max_length=31,
    )
    month: MonthNumber = Field(
        default_factory=lambda: datetime.now(ROSARIO_TIMEZONE).month,
        description="The month of the expenses query, from 1 to 12.",
    )


class MonthExpensesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    months: list[MonthNumber] = Field(
        default_factory=lambda: [datetime.now(ROSARIO_TIMEZONE).month],
        description="Month or months of the expenses query, from 1 to 12.",
        min_length=1,
        max_length=12,
    )


class RemoveOrUpdateTransactionArgs(BaseModel):
    old_transaction: Transaction
    new_transaction: Transaction | None = None
