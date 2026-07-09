from pydantic import BaseModel, Field


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
    pass


class DayExpensesArgs(BaseModel):
    day: int = Field(
        description="The day of the expenses query, from 1 to 31.",
        ge=1,
        le=31,
    )
    month: int = Field(
        description="The month of the expenses query, from 1 to 12.",
        ge=1,
        le=12,
    )


class MonthExpensesArgs(BaseModel):
    month: int = Field(
        description="The month of the expenses query, from 1 to 12.",
        ge=1,
        le=12,
    )


class RemoveOrUpdateTransactionArgs(BaseModel):
    previous_transaction: Transaction
    new_transaction: Transaction | None = None
