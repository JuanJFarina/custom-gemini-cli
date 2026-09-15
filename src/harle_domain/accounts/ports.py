from typing import Protocol, runtime_checkable

from harle_domain.accounts.models import ResolvedUser


@runtime_checkable
class AccountRepository(Protocol):
    async def resolve_telegram_identity(
        self,
        *,
        telegram_user_id: int,
    ) -> ResolvedUser | None: ...
