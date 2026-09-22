from dataclasses import dataclass
from uuid import UUID

from harle_domain.profiles import (
    AssistantProfile,
    AssistantProfileRepository,
    InteractionFrequency,
)
from harle_utils import MissingProfileError


@dataclass(frozen=True, slots=True)
class AssistantProfileService:
    repository: AssistantProfileRepository

    async def get(self, *, user_id: UUID) -> AssistantProfile:
        profile = await self.repository.get(user_id=user_id)
        if profile is None:
            raise MissingProfileError
        return profile

    async def update_interaction_frequency(
        self,
        *,
        user_id: UUID,
        frequency: InteractionFrequency,
    ) -> AssistantProfile:
        profile = await self.repository.update_interaction_frequency(
            user_id=user_id,
            frequency=frequency,
        )
        if profile is None:
            raise MissingProfileError
        return profile
