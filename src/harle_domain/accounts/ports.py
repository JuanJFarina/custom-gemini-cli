from typing import Protocol, runtime_checkable
from uuid import UUID

from harle_domain.accounts.models import ResolvedUser


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
