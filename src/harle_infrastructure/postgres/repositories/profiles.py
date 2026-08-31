from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

import asyncpg

from harle_domain.profiles.models import AssistantProfile, UserProfile


@dataclass(frozen=True, slots=True)
class PostgresUserProfileRepository:
    pool: asyncpg.Pool

    async def get(self, *, user_id: UUID) -> UserProfile | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    user_id,
                    preferred_name,
                    locale,
                    timezone,
                    latitude,
                    longitude,
                    personal_history,
                    created_at,
                    updated_at
                FROM user_profiles
                WHERE user_id = $1
                """,
                user_id,
            )

        if row is None:
            return None
        return _user_profile(row)

    async def save(
        self,
        *,
        user_id: UUID,
        profile: UserProfile,
    ) -> UserProfile:
        if profile.user_id != user_id:
            raise ValueError("User profile owner does not match user identifier.")

        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO user_profiles (
                    user_id,
                    preferred_name,
                    locale,
                    timezone,
                    latitude,
                    longitude,
                    personal_history,
                    created_at,
                    updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (user_id) DO UPDATE
                SET preferred_name = EXCLUDED.preferred_name,
                    locale = EXCLUDED.locale,
                    timezone = EXCLUDED.timezone,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    personal_history = EXCLUDED.personal_history,
                    updated_at = EXCLUDED.updated_at
                RETURNING
                    user_id,
                    preferred_name,
                    locale,
                    timezone,
                    latitude,
                    longitude,
                    personal_history,
                    created_at,
                    updated_at
                """,
                user_id,
                profile.preferred_name,
                profile.locale,
                profile.timezone,
                profile.latitude,
                profile.longitude,
                profile.personal_history,
                profile.created_at,
                profile.updated_at,
            )

        if row is None:
            raise RuntimeError("Could not save user profile.")
        return _user_profile(row)


@dataclass(frozen=True, slots=True)
class PostgresAssistantProfileRepository:
    pool: asyncpg.Pool

    async def get(self, *, user_id: UUID) -> AssistantProfile | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    user_id,
                    display_name,
                    profile_text,
                    created_at,
                    updated_at
                FROM assistant_profiles
                WHERE user_id = $1
                """,
                user_id,
            )

        if row is None:
            return None
        return _assistant_profile(row)

    async def save(
        self,
        *,
        user_id: UUID,
        profile: AssistantProfile,
    ) -> AssistantProfile:
        if profile.user_id != user_id:
            raise ValueError(
                "Assistant profile owner does not match user identifier.",
            )

        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO assistant_profiles (
                    user_id,
                    display_name,
                    profile_text,
                    created_at,
                    updated_at
                )
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id) DO UPDATE
                SET display_name = EXCLUDED.display_name,
                    profile_text = EXCLUDED.profile_text,
                    updated_at = EXCLUDED.updated_at
                RETURNING
                    user_id,
                    display_name,
                    profile_text,
                    created_at,
                    updated_at
                """,
                user_id,
                profile.display_name,
                profile.profile_text,
                profile.created_at,
                profile.updated_at,
            )

        if row is None:
            raise RuntimeError("Could not save assistant profile.")
        return _assistant_profile(row)


def _user_profile(row: asyncpg.Record) -> UserProfile:
    return UserProfile(
        user_id=_uuid(row, "user_id"),
        preferred_name=_text(row, "preferred_name"),
        locale=_text(row, "locale"),
        timezone=_text(row, "timezone"),
        latitude=_optional_decimal(row, "latitude"),
        longitude=_optional_decimal(row, "longitude"),
        personal_history=_text(row, "personal_history"),
        created_at=_datetime(row, "created_at"),
        updated_at=_datetime(row, "updated_at"),
    )


def _assistant_profile(row: asyncpg.Record) -> AssistantProfile:
    return AssistantProfile(
        user_id=_uuid(row, "user_id"),
        display_name=_text(row, "display_name"),
        profile_text=_text(row, "profile_text"),
        created_at=_datetime(row, "created_at"),
        updated_at=_datetime(row, "updated_at"),
    )


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


def _datetime(row: asyncpg.Record, key: str) -> datetime:
    value: object = row[key]
    if not isinstance(value, datetime):
        raise TypeError(f"Expected {key} to be a datetime.")
    return value


def _optional_decimal(
    row: asyncpg.Record,
    key: str,
) -> Decimal | None:
    value: object = row[key]
    if value is None:
        return None
    if not isinstance(value, Decimal):
        raise TypeError(f"Expected {key} to be numeric or null.")
    return value
