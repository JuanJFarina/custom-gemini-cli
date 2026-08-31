from dataclasses import dataclass

from harle_domain.accounts.models import ResolvedUser, SubscriptionStatus
from harle_utils import Clock, InactiveSubscriptionError, utc_now


@dataclass(frozen=True, slots=True)
class SubscriptionService:
    clock: Clock = utc_now

    def require_active(self, resolved_user: ResolvedUser) -> ResolvedUser:
        user = resolved_user.user
        valid_until = user.subscription_valid_until
        is_expired = valid_until is not None and valid_until <= self.clock()
        if (
            not resolved_user.plan.active
            or user.subscription_status is not SubscriptionStatus.ACTIVE
            or is_expired
        ):
            raise InactiveSubscriptionError
        return resolved_user
