from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import asyncpg

from harle_domain.expenses import (
    ExpenseCategory,
    ExpenseDetails,
    ExpenseEntryType,
    ExpenseInstallment,
    ExpenseStatus,
    ExpenseTimestamps,
    ExpenseTransaction,
)

EXPENSE_COLUMNS = """
    id,
    user_id,
    entry_type,
    amount,
    currency,
    category,
    transaction_date,
    description,
    status,
    installment_group_id,
    installment_number,
    installment_count,
    created_at,
    updated_at,
    cancelled_at
"""


@dataclass(frozen=True, slots=True)
class PostgresExpenseRepository:
    pool: asyncpg.Pool

    async def create(
        self,
        *,
        user_id: UUID,
        transactions: Sequence[ExpenseTransaction],
    ) -> Sequence[ExpenseTransaction]:
        _require_transactions(user_id, transactions)
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                rows = [
                    await _insert_transaction(connection, transaction)
                    for transaction in transactions
                ]
        return [_transaction_from_row(row) for row in rows]

    async def get_related(
        self,
        *,
        user_id: UUID,
        transaction_id: UUID,
    ) -> Sequence[ExpenseTransaction]:
        async with self.pool.acquire() as connection:
            rows = await _fetch_related(
                connection,
                user_id=user_id,
                transaction_id=transaction_id,
                lock=False,
            )
        return [_transaction_from_row(row) for row in rows]

    async def list_for_date(
        self,
        *,
        user_id: UUID,
        transaction_date: date,
    ) -> Sequence[ExpenseTransaction]:
        return await self.list_for_range(
            user_id=user_id,
            start_date=transaction_date,
            end_date=transaction_date,
        )

    async def list_for_range(
        self,
        *,
        user_id: UUID,
        start_date: date,
        end_date: date,
    ) -> Sequence[ExpenseTransaction]:
        if end_date < start_date:
            raise ValueError("Expense date range cannot end before it starts.")
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT {EXPENSE_COLUMNS}
                FROM expense_transactions
                WHERE user_id = $1
                    AND status = 'active'
                    AND transaction_date >= $2
                    AND transaction_date <= $3
                ORDER BY transaction_date, created_at, id
                """,
                user_id,
                start_date,
                end_date,
            )
        return [_transaction_from_row(row) for row in rows]

    async def update_related(
        self,
        *,
        user_id: UUID,
        transaction_id: UUID,
        transactions: Sequence[ExpenseTransaction],
    ) -> Sequence[ExpenseTransaction]:
        _require_transactions(user_id, transactions)
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                current_rows = await _fetch_related(
                    connection,
                    user_id=user_id,
                    transaction_id=transaction_id,
                    lock=True,
                )
                if not current_rows:
                    return []
                current = [_transaction_from_row(row) for row in current_rows]
                _require_same_related_transactions(current, transactions)
                rows = [
                    await _update_transaction(connection, transaction)
                    for transaction in transactions
                ]
        return [_transaction_from_row(row) for row in rows]

    async def delete_related(
        self,
        *,
        user_id: UUID,
        transaction_id: UUID,
    ) -> Sequence[ExpenseTransaction]:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                rows = await _fetch_related(
                    connection,
                    user_id=user_id,
                    transaction_id=transaction_id,
                    lock=True,
                )
                if not rows:
                    return []
                transaction_ids = [_uuid(row, "id") for row in rows]
                await connection.execute(
                    """
                    DELETE FROM expense_transactions
                    WHERE user_id = $1
                        AND id = ANY($2::uuid[])
                    """,
                    user_id,
                    transaction_ids,
                )
        return [_transaction_from_row(row) for row in rows]


async def _insert_transaction(
    connection: asyncpg.Connection,
    transaction: ExpenseTransaction,
) -> asyncpg.Record:
    row = await connection.fetchrow(
        f"""
        INSERT INTO expense_transactions (
            id,
            user_id,
            entry_type,
            amount,
            currency,
            category,
            transaction_date,
            description,
            status,
            installment_group_id,
            installment_number,
            installment_count,
            created_at,
            updated_at,
            cancelled_at
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8,
            $9, $10, $11, $12, $13, $14, $15
        )
        RETURNING {EXPENSE_COLUMNS}
        """,
        transaction.id,
        transaction.user_id,
        transaction.entry_type.value,
        transaction.amount,
        transaction.currency,
        transaction.category.value,
        transaction.transaction_date,
        transaction.description,
        transaction.status.value,
        transaction.installment_group_id,
        transaction.installment_number,
        transaction.installment_count,
        transaction.created_at,
        transaction.updated_at,
        transaction.cancelled_at,
    )
    if row is None:
        raise RuntimeError("Could not create expense transaction.")
    return row


async def _update_transaction(
    connection: asyncpg.Connection,
    transaction: ExpenseTransaction,
) -> asyncpg.Record:
    row = await connection.fetchrow(
        f"""
        UPDATE expense_transactions
        SET entry_type = $3,
            amount = $4,
            currency = $5,
            category = $6,
            transaction_date = $7,
            description = $8,
            status = $9,
            updated_at = $10,
            cancelled_at = $11
        WHERE id = $1
            AND user_id = $2
        RETURNING {EXPENSE_COLUMNS}
        """,
        transaction.id,
        transaction.user_id,
        transaction.entry_type.value,
        transaction.amount,
        transaction.currency,
        transaction.category.value,
        transaction.transaction_date,
        transaction.description,
        transaction.status.value,
        transaction.updated_at,
        transaction.cancelled_at,
    )
    if row is None:
        raise RuntimeError("Expense transaction disappeared during correction.")
    return row


async def _fetch_related(
    connection: asyncpg.Connection,
    *,
    user_id: UUID,
    transaction_id: UUID,
    lock: bool,
) -> list[asyncpg.Record]:
    lock_clause = "FOR UPDATE" if lock else ""
    target = await connection.fetchrow(
        f"""
        SELECT installment_group_id
        FROM expense_transactions
        WHERE id = $1
            AND user_id = $2
            AND status = 'active'
        {lock_clause}
        """,
        transaction_id,
        user_id,
    )
    if target is None:
        return []
    group_id = _optional_uuid(target, "installment_group_id")
    if group_id is None:
        row = await connection.fetchrow(
            f"""
            SELECT {EXPENSE_COLUMNS}
            FROM expense_transactions
            WHERE id = $1
                AND user_id = $2
                AND status = 'active'
            {lock_clause}
            """,
            transaction_id,
            user_id,
        )
        return [row] if row is not None else []
    return list(
        await connection.fetch(
            f"""
            SELECT {EXPENSE_COLUMNS}
            FROM expense_transactions
            WHERE user_id = $1
                AND installment_group_id = $2
                AND status = 'active'
            ORDER BY installment_number
            {lock_clause}
            """,
            user_id,
            group_id,
        ),
    )


def _require_transactions(
    user_id: UUID,
    transactions: Sequence[ExpenseTransaction],
) -> None:
    if not transactions:
        raise ValueError("At least one expense transaction is required.")
    if any(transaction.user_id != user_id for transaction in transactions):
        raise ValueError("Expense transaction owner does not match user identifier.")


def _require_same_related_transactions(
    current: Sequence[ExpenseTransaction],
    replacements: Sequence[ExpenseTransaction],
) -> None:
    current_by_id = {transaction.id: transaction for transaction in current}
    replacement_by_id = {transaction.id: transaction for transaction in replacements}
    if current_by_id.keys() != replacement_by_id.keys():
        raise ValueError("Expense correction must preserve transaction identifiers.")
    for transaction_id, replacement in replacement_by_id.items():
        existing = current_by_id[transaction_id]
        if (
            replacement.installment_group_id != existing.installment_group_id
            or replacement.installment_number != existing.installment_number
            or replacement.installment_count != existing.installment_count
        ):
            raise ValueError("Expense correction cannot change installment identity.")


def _transaction_from_row(row: asyncpg.Record) -> ExpenseTransaction:
    return ExpenseTransaction(
        id=_uuid(row, "id"),
        user_id=_uuid(row, "user_id"),
        details=ExpenseDetails(
            entry_type=ExpenseEntryType(_text(row, "entry_type")),
            amount=_decimal(row, "amount"),
            currency=_text(row, "currency"),
            category=ExpenseCategory(_text(row, "category")),
            transaction_date=_date(row, "transaction_date"),
            description=_text(row, "description"),
            status=ExpenseStatus(_text(row, "status")),
        ),
        installment=_installment_from_row(row),
        timestamps=ExpenseTimestamps(
            created_at=_datetime(row, "created_at"),
            updated_at=_datetime(row, "updated_at"),
            cancelled_at=_optional_datetime(row, "cancelled_at"),
        ),
    )


def _installment_from_row(row: asyncpg.Record) -> ExpenseInstallment | None:
    group_id = _optional_uuid(row, "installment_group_id")
    number = _optional_integer(row, "installment_number")
    count = _optional_integer(row, "installment_count")
    if group_id is None and number is None and count is None:
        return None
    if group_id is None or number is None or count is None:
        raise TypeError("Expected complete installment fields.")
    return ExpenseInstallment(group_id=group_id, number=number, count=count)


def _text(row: asyncpg.Record, key: str) -> str:
    value: object = row[key]
    if not isinstance(value, str):
        raise TypeError(f"Expected {key} to be text.")
    return value


def _uuid(row: asyncpg.Record, key: str) -> UUID:
    value: object = row[key]
    if not isinstance(value, UUID):
        raise TypeError(f"Expected {key} to be a UUID.")
    return value


def _optional_uuid(row: asyncpg.Record, key: str) -> UUID | None:
    value: object = row[key]
    if value is None:
        return None
    if not isinstance(value, UUID):
        raise TypeError(f"Expected {key} to be a UUID or null.")
    return value


def _decimal(row: asyncpg.Record, key: str) -> Decimal:
    value: object = row[key]
    if not isinstance(value, Decimal):
        raise TypeError(f"Expected {key} to be numeric.")
    return value


def _date(row: asyncpg.Record, key: str) -> date:
    value: object = row[key]
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"Expected {key} to be a date.")
    return value


def _datetime(row: asyncpg.Record, key: str) -> datetime:
    value: object = row[key]
    if not isinstance(value, datetime):
        raise TypeError(f"Expected {key} to be a datetime.")
    return value


def _optional_datetime(row: asyncpg.Record, key: str) -> datetime | None:
    value: object = row[key]
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"Expected {key} to be a datetime or null.")
    return value


def _optional_integer(row: asyncpg.Record, key: str) -> int | None:
    value: object = row[key]
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"Expected {key} to be an integer or null.")
    return value
