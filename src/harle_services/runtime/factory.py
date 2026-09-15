from asyncio import gather
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from harle_domain.accounts import ResolvedUser
from harle_domain.conversations.ports import ConversationStore
from harle_domain.profiles import (
    AssistantProfileRepository,
    UserProfileRepository,
)
from harle_utils import MissingProfileError

from .models import UserRuntime

ConversationStoreBuilder = Callable[[UUID, int], ConversationStore]


@dataclass(frozen=True, slots=True)
class UserRuntimeFactory:
    user_profiles: UserProfileRepository
    assistant_profiles: AssistantProfileRepository
    conversation_store_builder: ConversationStoreBuilder

    async def create_for_resolved_user(
        self,
        *,
        resolved_user: ResolvedUser,
        telegram_chat_id: int,
    ) -> UserRuntime:
        user_id = resolved_user.user.id
        user_profile, assistant_profile = await gather(
            self.user_profiles.get(user_id=user_id),
            self.assistant_profiles.get(user_id=user_id),
        )
        if user_profile is None or assistant_profile is None:
            raise MissingProfileError
        return UserRuntime(
            resolved_user=resolved_user,
            user_profile=user_profile,
            assistant_profile=assistant_profile,
            telegram_chat_id=telegram_chat_id,
            conversation_store=self.conversation_store_builder(
                user_id,
                telegram_chat_id,
            ),
        )
