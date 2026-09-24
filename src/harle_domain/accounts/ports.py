from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from harle_domain.accounts.models import ResolvedUser, SubscriptionPeriod
from harle_domain.accounts.web import (
    AccountOverview,
    BrowserSession,
    FreeAccountPeriod,
    GoogleIdentity,
    GoogleRegistration,
    TelegramLinkCommandRecord,
    TelegramLinkResult,
    TelegramLinkStatus,
)


@runtime_checkable
class AccountRepository(Protocol):
    async def resolve_telegram_identity(
        self,
        *,
        telegram_user_id: int,
    ) -> ResolvedUser | None: ...

    async def resolve_user_telegram_identity(
        self,
        *,
        user_id: UUID,
    ) -> ResolvedUser | None: ...


@runtime_checkable
class WebAccountRepository(Protocol):
    async def find_or_create_google_user(
        self,
        *,
        registration: GoogleRegistration,
    ) -> UUID: ...

    async def get_overview(self, *, user_id: UUID) -> AccountOverview | None: ...

    async def get_free_period(
        self,
        *,
        user_id: UUID,
        current_time: datetime,
    ) -> FreeAccountPeriod | None: ...

    async def list_due_free_periods(
        self,
        *,
        current_time: datetime,
        limit: int,
    ) -> Sequence[FreeAccountPeriod]: ...

    async def replace_free_period(
        self,
        *,
        user_id: UUID,
        expected_period: SubscriptionPeriod,
        new_period: SubscriptionPeriod,
        synchronized_at: datetime,
    ) -> bool: ...


@runtime_checkable
class BrowserSessionRepository(Protocol):
    async def create(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
        created_at: datetime,
    ) -> BrowserSession: ...

    async def resolve(
        self,
        *,
        token_hash: str,
        current_time: datetime,
    ) -> BrowserSession | None: ...

    async def revoke(
        self,
        *,
        token_hash: str,
        revoked_at: datetime,
    ) -> bool: ...


@runtime_checkable
class TelegramLinkRepository(Protocol):
    async def issue(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
        created_at: datetime,
    ) -> None: ...

    async def get_status(
        self,
        *,
        user_id: UUID,
        current_time: datetime,
    ) -> TelegramLinkStatus: ...

    async def process_command(
        self,
        *,
        command: TelegramLinkCommandRecord,
    ) -> TelegramLinkResult: ...


@runtime_checkable
class GoogleIdentityProvider(Protocol):
    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
    ) -> str: ...

    async def exchange(
        self,
        *,
        code: str,
        code_verifier: str,
        expected_nonce: str,
    ) -> GoogleIdentity: ...
