from collections.abc import Sequence
from datetime import date
from typing import Protocol, runtime_checkable
from uuid import UUID

from .models import ExpenseTransaction


@runtime_checkable
class ExpenseRepository(Protocol):
    async def create(
        self,
        *,
        user_id: UUID,
        transactions: Sequence[ExpenseTransaction],
    ) -> Sequence[ExpenseTransaction]: ...

    async def get_related(
        self,
        *,
        user_id: UUID,
        transaction_id: UUID,
    ) -> Sequence[ExpenseTransaction]: ...

    async def list_for_date(
        self,
        *,
        user_id: UUID,
        transaction_date: date,
    ) -> Sequence[ExpenseTransaction]: ...

    async def list_for_range(
        self,
        *,
        user_id: UUID,
        start_date: date,
        end_date: date,
    ) -> Sequence[ExpenseTransaction]: ...

    async def update_related(
        self,
        *,
        user_id: UUID,
        transaction_id: UUID,
        transactions: Sequence[ExpenseTransaction],
    ) -> Sequence[ExpenseTransaction]: ...

    async def delete_related(
        self,
        *,
        user_id: UUID,
        transaction_id: UUID,
    ) -> Sequence[ExpenseTransaction]: ...
