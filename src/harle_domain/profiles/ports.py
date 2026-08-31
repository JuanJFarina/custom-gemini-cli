from typing import Protocol, runtime_checkable
from uuid import UUID

from harle_domain.profiles.models import AssistantProfile, UserProfile


@runtime_checkable
class UserProfileRepository(Protocol):
    async def get(self, *, user_id: UUID) -> UserProfile | None: ...

    async def save(
        self,
        *,
        user_id: UUID,
        profile: UserProfile,
    ) -> UserProfile: ...


@runtime_checkable
class AssistantProfileRepository(Protocol):
    async def get(self, *, user_id: UUID) -> AssistantProfile | None: ...

    async def save(
        self,
        *,
        user_id: UUID,
        profile: AssistantProfile,
    ) -> AssistantProfile: ...
