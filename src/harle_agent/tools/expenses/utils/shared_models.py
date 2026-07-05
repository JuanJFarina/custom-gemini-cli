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
