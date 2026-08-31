from dataclasses import dataclass

from harle_domain.accounts import AccountRepository, ResolvedUser
from harle_utils import UnknownIdentityError


@dataclass(frozen=True, slots=True)
class IdentityService:
    accounts: AccountRepository

    async def resolve_telegram_user(self, telegram_user_id: int) -> ResolvedUser:
        resolved_user = await self.accounts.resolve_telegram_identity(
            telegram_user_id=telegram_user_id,
        )
        if resolved_user is None:
            raise UnknownIdentityError
        return resolved_user
