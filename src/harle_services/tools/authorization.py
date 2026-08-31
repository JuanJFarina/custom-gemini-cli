from dataclasses import dataclass
from uuid import UUID

from harle_domain.accounts import ResolvedUser, SubscriptionStatus
from harle_domain.tools import ToolFamily


@dataclass(frozen=True, slots=True)
class ToolAccessPolicy:
    legacy_google_sheets_user_id: UUID | None

    def authorized_families(
        self,
        resolved_user: ResolvedUser,
    ) -> frozenset[ToolFamily]:
        user = resolved_user.user
        if (
            not resolved_user.plan.active
            or user.subscription_status is not SubscriptionStatus.ACTIVE
        ):
            return frozenset()
        return self.authorized_families_for_user_id(user.id)

    def authorized_families_for_user_id(
        self,
        user_id: UUID,
    ) -> frozenset[ToolFamily]:
        if (
            self.legacy_google_sheets_user_id is None
            or user_id != self.legacy_google_sheets_user_id
        ):
            return frozenset()
        return frozenset({ToolFamily.LEGACY_GOOGLE_SHEETS_EXPENSES})
