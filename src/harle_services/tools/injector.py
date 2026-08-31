from dataclasses import dataclass
from uuid import UUID

from harle_domain.accounts import ResolvedUser
from harle_domain.tools import HarleToolStore

from .authorization import ToolAccessPolicy
from .registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class ToolsInjector:
    registry: ToolRegistry
    access_policy: ToolAccessPolicy

    def inject(self, resolved_user: ResolvedUser) -> HarleToolStore:
        families = self.access_policy.authorized_families(resolved_user)
        return self.registry.build_store(
            user_id=resolved_user.user.id,
            authorized_families=families,
        )

    def inject_for_explicit_user_id(self, user_id: UUID) -> HarleToolStore:
        families = self.access_policy.authorized_families_for_user_id(user_id)
        return self.registry.build_store(
            user_id=user_id,
            authorized_families=families,
        )
