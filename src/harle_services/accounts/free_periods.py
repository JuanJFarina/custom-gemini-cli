from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from harle_domain.accounts import (
    SubscriptionPeriod,
    SubscriptionStatus,
    User,
    WebAccountRepository,
)
from harle_utils import Clock, as_utc, utc_now


@dataclass(frozen=True, slots=True)
class FreeSubscriptionService:
    repository: WebAccountRepository
    clock: Clock = utc_now

    async def ensure_current(self, user: User) -> bool:
        current_time = as_utc(self.clock())
        valid_until = user.subscription_valid_until
        if (
            user.plan_code != "free"
            or user.subscription_status is not SubscriptionStatus.ACTIVE
            or (valid_until is not None and valid_until <= current_time)
        ):
            return False
        period = user.require_subscription_period()
        if period.ends_at > current_time:
            return False
        renewed = advance_monthly_period(period, current_time)
        await self.repository.replace_free_period(
            user_id=user.id,
            expected_period=period,
            new_period=renewed,
            synchronized_at=current_time,
        )
        return True

    async def ensure_user(self, user_id: UUID) -> bool:
        current_time = as_utc(self.clock())
        account = await self.repository.get_free_period(
            user_id=user_id,
            current_time=current_time,
        )
        if account is None or account.period.ends_at > current_time:
            return False
        renewed = advance_monthly_period(account.period, current_time)
        await self.repository.replace_free_period(
            user_id=user_id,
            expected_period=account.period,
            new_period=renewed,
            synchronized_at=current_time,
        )
        return True

    async def renew_due(self, *, limit: int = 500) -> int:
        current_time = as_utc(self.clock())
        due_periods = await self.repository.list_due_free_periods(
            current_time=current_time,
            limit=limit,
        )
        renewed_count = 0
        for due in due_periods:
            renewed = advance_monthly_period(due.period, current_time)
            changed = await self.repository.replace_free_period(
                user_id=due.user_id,
                expected_period=due.period,
                new_period=renewed,
                synchronized_at=current_time,
            )
            renewed_count += int(changed)
        return renewed_count


def advance_monthly_period(
    period: SubscriptionPeriod,
    current_time: datetime,
) -> SubscriptionPeriod:
    if period.ends_at > current_time:
        return period
    anchor_day = max(period.starts_at.day, period.ends_at.day)
    starts_at = period.ends_at
    ends_at = _next_month(starts_at, anchor_day)
    while ends_at <= current_time:
        starts_at = ends_at
        ends_at = _next_month(starts_at, anchor_day)
    return SubscriptionPeriod(starts_at=starts_at, ends_at=ends_at)


def first_monthly_period(starts_at: datetime) -> SubscriptionPeriod:
    return SubscriptionPeriod(
        starts_at=starts_at,
        ends_at=_next_month(starts_at, starts_at.day),
    )


def _next_month(value: datetime, anchor_day: int) -> datetime:
    next_month = value.month % 12 + 1
    next_year = value.year + int(value.month == 12)
    next_day = min(anchor_day, monthrange(next_year, next_month)[1])
    return value.replace(year=next_year, month=next_month, day=next_day)
