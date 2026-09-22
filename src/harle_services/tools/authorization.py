from dataclasses import dataclass
from uuid import UUID

from harle_domain.accounts import ResolvedUser
from harle_domain.tools import ToolFamily


@dataclass(frozen=True, slots=True)
class ToolAccessPolicy:
    legacy_google_sheets_user_id: UUID | None
    profiles_enabled: bool = False

    def authorized_families(
        self,
        resolved_user: ResolvedUser,
    ) -> frozenset[ToolFamily]:
        user = resolved_user.user
        profile_families = {ToolFamily.PROFILES} if self.profiles_enabled else set()
        if user.id == self.legacy_google_sheets_user_id:
            return frozenset(
                {
                    ToolFamily.INTERNAL_EVENTS,
                    ToolFamily.LEGACY_GOOGLE_SHEETS_EXPENSES,
                    ToolFamily.RECENT_MEDIA,
                    *profile_families,
                },
            )
        return frozenset(
            {
                ToolFamily.INTERNAL_EVENTS,
                ToolFamily.INTERNAL_EXPENSES,
                ToolFamily.RECENT_MEDIA,
                *profile_families,
            },
        )

    def authorized_families_for_user_id(
        self,
        user_id: UUID,
    ) -> frozenset[ToolFamily]:
        if user_id != self.legacy_google_sheets_user_id:
            return frozenset()
        return frozenset({ToolFamily.LEGACY_GOOGLE_SHEETS_EXPENSES})
