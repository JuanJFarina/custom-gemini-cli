import asyncpg

from harle_utils import InvalidDatabaseSchemaError

REQUIRED_COLUMNS = frozenset(
    {
        "assistant_profiles.created_at",
        "assistant_profiles.display_name",
        "assistant_profiles.profile_text",
        "assistant_profiles.updated_at",
        "assistant_profiles.user_id",
        "conversations.completed_at",
        "conversations.created_at",
        "conversations.failure_code",
        "conversations.id",
        "conversations.kind",
        "conversations.model",
        "conversations.prompt",
        "conversations.response",
        "conversations.status",
        "conversations.telegram_chat_id",
        "conversations.telegram_update_id",
        "conversations.tool_interaction_index",
        "conversations.tool_call_response",
        "conversations.tool_result",
        "conversations.user_id",
        "expense_transactions.amount",
        "expense_transactions.cancelled_at",
        "expense_transactions.category",
        "expense_transactions.created_at",
        "expense_transactions.currency",
        "expense_transactions.description",
        "expense_transactions.entry_type",
        "expense_transactions.id",
        "expense_transactions.installment_count",
        "expense_transactions.installment_group_id",
        "expense_transactions.installment_number",
        "expense_transactions.status",
        "expense_transactions.transaction_date",
        "expense_transactions.updated_at",
        "expense_transactions.user_id",
        "external_identities.created_at",
        "external_identities.display_name",
        "external_identities.external_user_id",
        "external_identities.id",
        "external_identities.provider",
        "external_identities.updated_at",
        "external_identities.user_id",
        "internal_events.all_day",
        "internal_events.cancelled_at",
        "internal_events.created_at",
        "internal_events.deleted_at",
        "internal_events.description",
        "internal_events.ends_at",
        "internal_events.id",
        "internal_events.starts_at",
        "internal_events.status",
        "internal_events.timezone",
        "internal_events.title",
        "internal_events.updated_at",
        "internal_events.user_id",
        "plans.active",
        "plans.code",
        "plans.created_at",
        "plans.monthly_request_limit",
        "plans.updated_at",
        "telegram_update_claims.claimed_at",
        "telegram_update_claims.telegram_chat_id",
        "telegram_update_claims.telegram_user_id",
        "telegram_update_claims.update_id",
        "user_profiles.created_at",
        "user_profiles.latitude",
        "user_profiles.locale",
        "user_profiles.longitude",
        "user_profiles.personal_history",
        "user_profiles.preferred_name",
        "user_profiles.timezone",
        "user_profiles.updated_at",
        "user_profiles.user_id",
        "users.created_at",
        "users.display_name",
        "users.id",
        "users.plan_code",
        "users.subscription_status",
        "users.subscription_synced_at",
        "users.subscription_valid_until",
        "users.updated_at",
    },
)


async def validate_postgres_schema(pool: asyncpg.Pool) -> None:
    table_names = sorted(
        {column.split(".", maxsplit=1)[0] for column in REQUIRED_COLUMNS},
    )
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
                AND table_name = ANY($1::text[])
            """,
            table_names,
        )

    available_columns = {
        f"{_text(row, 'table_name')}.{_text(row, 'column_name')}" for row in rows
    }
    missing_columns = sorted(REQUIRED_COLUMNS - available_columns)
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise InvalidDatabaseSchemaError(
            f"PostgreSQL schema is missing required columns: {missing}",
        )


def _text(row: asyncpg.Record, key: str) -> str:
    value: object = row[key]
    if not isinstance(value, str):
        raise TypeError(f"Expected {key} to be text.")
    return value
