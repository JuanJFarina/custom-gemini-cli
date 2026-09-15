import argparse
import asyncio
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import asyncpg

PLAN_CODES = ("free", "basic", "max")
SUBSCRIPTION_STATUSES = (
    "active",
    "inactive",
    "past_due",
    "cancelled",
    "revoked",
)
LOCALE_PATTERN = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*$")
TIMEZONE_PATTERN = re.compile(r"^[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*$")
MAX_TELEGRAM_ID = 9_223_372_036_854_775_807
MAX_PERSONAL_HISTORY_BYTES = 1_000_000


@dataclass(frozen=True)
class AccountProvision:
    database_url: str
    telegram_id: int
    display_name: str
    plan_code: str
    subscription_status: str
    subscription_valid_until: datetime | None


@dataclass(frozen=True)
class UserProfileProvision:
    preferred_name: str
    locale: str
    timezone_name: str
    latitude: Decimal | None
    longitude: Decimal | None
    personal_history: str | None


@dataclass(frozen=True)
class AssistantProfileProvision:
    assistant_display_name: str
    assistant_profile_text: str


@dataclass(frozen=True)
class ProvisionRequest:
    account: AccountProvision
    user_profile: UserProfileProvision
    assistant_profile: AssistantProfileProvision


def _required_text(value: str, field: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must not be blank")
    if len(normalized) > max_length:
        raise ValueError(f"{field} must not exceed {max_length} characters")
    return normalized


def _database_url(value: str) -> str:
    normalized = _required_text(value, "database URL", 4_096)
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("database URL must use the postgres or postgresql scheme")
    if not parsed.path or parsed.path == "/":
        raise ValueError("database URL must include a database name")
    return normalized


def _telegram_id(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Telegram ID must be an integer") from exc
    if parsed <= 0 or parsed > MAX_TELEGRAM_ID:
        raise argparse.ArgumentTypeError("Telegram ID must be a positive BIGINT")
    return parsed


def _subscription_timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "subscription validity must be an ISO 8601 timestamp",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError(
            "subscription validity must include a UTC offset",
        )
    return parsed.astimezone(timezone.utc)


def _coordinate(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("coordinate must be numeric") from exc
    if not parsed.is_finite():
        raise argparse.ArgumentTypeError("coordinate must be finite")
    return parsed


def _locale(value: str) -> str:
    normalized = value.strip()
    if not LOCALE_PATTERN.fullmatch(normalized):
        raise argparse.ArgumentTypeError(
            "locale must resemble en, en-US, or pt_BR",
        )
    return normalized.replace("_", "-")


def _timezone_name(value: str) -> str:
    normalized = value.strip()
    if not TIMEZONE_PATTERN.fullmatch(normalized):
        raise argparse.ArgumentTypeError("timezone must be an IANA timezone")
    try:
        ZoneInfo(normalized)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise argparse.ArgumentTypeError("timezone must be an IANA timezone") from exc
    return normalized


def _personal_history(path: Path | None) -> str | None:
    if path is None:
        return None
    if not path.is_file():
        raise ValueError(f"personal history file does not exist: {path}")
    size = path.stat().st_size
    if size > MAX_PERSONAL_HISTORY_BYTES:
        raise ValueError(
            f"personal history file must not exceed {MAX_PERSONAL_HISTORY_BYTES} bytes",
        )
    return path.read_bytes().decode("utf-8").strip()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="provision_user")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("POSTGRES_DATABASE_URL"),
    )
    parser.add_argument("--telegram-id", required=True, type=_telegram_id)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--plan-code", required=True, choices=PLAN_CODES)
    parser.add_argument(
        "--subscription-status",
        required=True,
        choices=SUBSCRIPTION_STATUSES,
    )
    parser.add_argument(
        "--subscription-valid-until",
        type=_subscription_timestamp,
    )
    parser.add_argument("--preferred-name", required=True)
    parser.add_argument("--locale", required=True, type=_locale)
    parser.add_argument("--timezone", required=True, type=_timezone_name)
    parser.add_argument("--latitude", type=_coordinate)
    parser.add_argument("--longitude", type=_coordinate)
    parser.add_argument("--personal-history-file", type=Path)
    parser.add_argument("--assistant-display-name", required=True)
    parser.add_argument("--assistant-profile-text", required=True)
    return parser


def parse_arguments() -> ProvisionRequest:
    parser = _parser()
    arguments = parser.parse_args()
    if arguments.database_url is None:
        parser.error(
            "--database-url or the POSTGRES_DATABASE_URL environment variable is required",
        )

    latitude = cast(Decimal | None, arguments.latitude)
    longitude = cast(Decimal | None, arguments.longitude)
    if (latitude is None) != (longitude is None):
        parser.error("latitude and longitude must be provided together")
    if latitude is not None and not Decimal("-90") <= latitude <= Decimal("90"):
        parser.error("latitude must be between -90 and 90")
    if longitude is not None and not Decimal("-180") <= longitude <= Decimal("180"):
        parser.error("longitude must be between -180 and 180")

    subscription_status = cast(str, arguments.subscription_status)
    subscription_valid_until = cast(
        datetime | None,
        arguments.subscription_valid_until,
    )
    if (
        subscription_status == "active"
        and subscription_valid_until is not None
        and subscription_valid_until <= datetime.now(timezone.utc)
    ):
        parser.error("an active subscription cannot already be expired")

    try:
        request = ProvisionRequest(
            account=AccountProvision(
                database_url=_database_url(cast(str, arguments.database_url)),
                telegram_id=cast(int, arguments.telegram_id),
                display_name=_required_text(
                    cast(str, arguments.display_name),
                    "display name",
                    200,
                ),
                plan_code=cast(str, arguments.plan_code),
                subscription_status=subscription_status,
                subscription_valid_until=subscription_valid_until,
            ),
            user_profile=UserProfileProvision(
                preferred_name=_required_text(
                    cast(str, arguments.preferred_name),
                    "preferred name",
                    200,
                ),
                locale=cast(str, arguments.locale),
                timezone_name=cast(str, arguments.timezone),
                latitude=latitude,
                longitude=longitude,
                personal_history=_personal_history(
                    cast(Path | None, arguments.personal_history_file),
                ),
            ),
            assistant_profile=AssistantProfileProvision(
                assistant_display_name=_required_text(
                    cast(str, arguments.assistant_display_name),
                    "assistant display name",
                    200,
                ),
                assistant_profile_text=_required_text(
                    cast(str, arguments.assistant_profile_text),
                    "assistant profile text",
                    20_000,
                ),
            ),
        )
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
        raise RuntimeError("argument parsing did not exit") from exc
    return request


def _optional_uuid(value: object, source: str) -> UUID | None:
    if value is None:
        return None
    if not isinstance(value, UUID):
        raise RuntimeError(f"{source} returned an invalid user UUID")
    return value


async def _resolve_user_id(
    connection: asyncpg.Connection,
    request: ProvisionRequest,
) -> UUID | None:
    identity_user_id = _optional_uuid(
        await connection.fetchval(
            """
            SELECT user_id
            FROM public.external_identities
            WHERE provider = 'telegram'
                AND external_user_id = $1
            FOR UPDATE
            """,
            str(request.account.telegram_id),
        ),
        "external identity lookup",
    )
    legacy_user_id = _optional_uuid(
        await connection.fetchval(
            """
            SELECT id
            FROM public.users
            WHERE telegram_id = $1
            FOR UPDATE
            """,
            request.account.telegram_id,
        ),
        "legacy Telegram lookup",
    )
    if (
        identity_user_id is not None
        and legacy_user_id is not None
        and identity_user_id != legacy_user_id
    ):
        raise ValueError(
            "external identity and legacy telegram_id belong to different users",
        )
    return identity_user_id or legacy_user_id


async def _validate_plan(
    connection: asyncpg.Connection,
    plan_code: str,
) -> None:
    plan_is_active = await connection.fetchval(
        """
        SELECT active
        FROM public.plans
        WHERE code = $1
        FOR SHARE
        """,
        plan_code,
    )
    if plan_is_active is not True:
        raise ValueError(f"plan is missing or inactive: {plan_code}")


async def _create_user(
    connection: asyncpg.Connection,
    request: ProvisionRequest,
) -> UUID:
    user_id = _optional_uuid(
        await connection.fetchval(
            """
            INSERT INTO public.users (
                name,
                telegram_id,
                display_name,
                plan_code,
                subscription_status,
                subscription_valid_until,
                subscription_synced_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            RETURNING id
            """,
            request.account.display_name,
            request.account.telegram_id,
            request.account.display_name,
            request.account.plan_code,
            request.account.subscription_status,
            request.account.subscription_valid_until,
        ),
        "user insertion",
    )
    if user_id is None:
        raise RuntimeError("user insertion returned no UUID")
    return user_id


async def _update_user(
    connection: asyncpg.Connection,
    user_id: UUID,
    request: ProvisionRequest,
) -> None:
    stored_telegram_id = await connection.fetchval(
        """
        SELECT telegram_id
        FROM public.users
        WHERE id = $1
        FOR UPDATE
        """,
        user_id,
    )
    if (
        stored_telegram_id is not None
        and stored_telegram_id != request.account.telegram_id
    ):
        raise ValueError("matched user already has a different legacy telegram_id")

    result = await connection.execute(
        """
        UPDATE public.users
        SET name = $2,
            telegram_id = $3,
            display_name = $2,
            plan_code = $4,
            subscription_status = $5,
            subscription_valid_until = $6,
            subscription_synced_at = NOW(),
            updated_at = NOW()
        WHERE id = $1
        """,
        user_id,
        request.account.display_name,
        request.account.telegram_id,
        request.account.plan_code,
        request.account.subscription_status,
        request.account.subscription_valid_until,
    )
    if result != "UPDATE 1":
        raise RuntimeError("matched user no longer exists")


async def _upsert_identity(
    connection: asyncpg.Connection,
    user_id: UUID,
    request: ProvisionRequest,
) -> None:
    await connection.execute(
        """
        INSERT INTO public.external_identities (
            user_id,
            provider,
            external_user_id,
            display_name
        )
        VALUES ($1, 'telegram', $2, $3)
        ON CONFLICT (provider, external_user_id) DO UPDATE
        SET user_id = EXCLUDED.user_id,
            display_name = EXCLUDED.display_name,
            updated_at = NOW()
        """,
        user_id,
        str(request.account.telegram_id),
        request.account.display_name,
    )


async def _upsert_user_profile(
    connection: asyncpg.Connection,
    user_id: UUID,
    request: ProvisionRequest,
) -> None:
    await connection.execute(
        """
        INSERT INTO public.user_profiles (
            user_id,
            preferred_name,
            locale,
            timezone,
            latitude,
            longitude,
            personal_history
        )
        VALUES ($1, $2, $3, $4, $5, $6, COALESCE($7, ''))
        ON CONFLICT (user_id) DO UPDATE
        SET preferred_name = EXCLUDED.preferred_name,
            locale = EXCLUDED.locale,
            timezone = EXCLUDED.timezone,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            personal_history = COALESCE(
                $7,
                public.user_profiles.personal_history
            ),
            updated_at = NOW()
        """,
        user_id,
        request.user_profile.preferred_name,
        request.user_profile.locale,
        request.user_profile.timezone_name,
        request.user_profile.latitude,
        request.user_profile.longitude,
        request.user_profile.personal_history,
    )


async def _upsert_assistant_profile(
    connection: asyncpg.Connection,
    user_id: UUID,
    request: ProvisionRequest,
) -> None:
    await connection.execute(
        """
        INSERT INTO public.assistant_profiles (
            user_id,
            display_name,
            profile_text
        )
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            profile_text = EXCLUDED.profile_text,
            updated_at = NOW()
        """,
        user_id,
        request.assistant_profile.assistant_display_name,
        request.assistant_profile.assistant_profile_text,
    )


async def provision_user(request: ProvisionRequest) -> UUID:
    connection = await asyncpg.connect(dsn=request.account.database_url)
    try:
        async with connection.transaction(isolation="serializable"):
            await connection.execute(
                """
                SELECT pg_advisory_xact_lock(
                    hashtextextended('telegram:' || $1, 0)
                )
                """,
                str(request.account.telegram_id),
            )
            await _validate_plan(connection, request.account.plan_code)
            user_id = await _resolve_user_id(connection, request)
            if user_id is None:
                user_id = await _create_user(connection, request)
            else:
                await _update_user(connection, user_id, request)
            await _upsert_identity(connection, user_id, request)
            await _upsert_user_profile(connection, user_id, request)
            await _upsert_assistant_profile(connection, user_id, request)
            return user_id
    finally:
        await connection.close()


def main() -> int:
    request = parse_arguments()
    try:
        user_id = asyncio.run(provision_user(request))
    except (
        OSError,
        RuntimeError,
        ValueError,
        asyncpg.InterfaceError,
        asyncpg.PostgresError,
    ) as exc:
        print(f"Provisioning failed: {exc}", file=sys.stderr)
        return 1
    print(f"Provisioned user {user_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
