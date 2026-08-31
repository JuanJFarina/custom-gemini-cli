from dataclasses import dataclass
from typing import TypeAlias

from harle_domain.accounts import ResolvedUser

from .identity import IdentityService
from .quota import QuotaExceeded, QuotaReservation, UsageQuotaService
from .rate_limit import RateLimitService, TemporaryBan
from .subscriptions import SubscriptionService


@dataclass(frozen=True, slots=True)
class PreflightAccepted:
    resolved_user: ResolvedUser
    quota_reservation: QuotaReservation


PreflightResult: TypeAlias = PreflightAccepted | TemporaryBan | QuotaExceeded


@dataclass(frozen=True, slots=True)
class PreflightService:
    identity: IdentityService
    rate_limit: RateLimitService
    subscriptions: SubscriptionService
    quota: UsageQuotaService

    async def check(self, telegram_user_id: int) -> PreflightResult:
        resolved_user = await self.identity.resolve_telegram_user(telegram_user_id)
        rate_limit = self.rate_limit.check(telegram_user_id)
        if isinstance(rate_limit, TemporaryBan):
            return rate_limit

        self.subscriptions.require_active(resolved_user)
        quota = await self.quota.reserve(
            user_id=resolved_user.user.id,
            monthly_request_limit=resolved_user.plan.monthly_request_limit,
        )
        if isinstance(quota, QuotaExceeded):
            return quota
        return PreflightAccepted(
            resolved_user=resolved_user,
            quota_reservation=quota,
        )
