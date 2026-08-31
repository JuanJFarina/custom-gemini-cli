from asyncio import gather
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from harle_domain.conversations.ports import ConversationStore
from harle_domain.profiles import (
    AssistantProfileRepository,
    UserProfileRepository,
)
from harle_services.access import IdentityService, SubscriptionService
from harle_services.tools import ToolsInjector
from harle_utils import MissingProfileError

from .models import UserRuntime

ConversationStoreBuilder = Callable[[UUID, int], ConversationStore]


@dataclass(frozen=True, slots=True)
class UserRuntimeFactory:
    identity: IdentityService
    subscriptions: SubscriptionService
    user_profiles: UserProfileRepository
    assistant_profiles: AssistantProfileRepository
    conversation_store_builder: ConversationStoreBuilder
    tools: ToolsInjector

    async def create(
        self,
        *,
        telegram_user_id: int,
        telegram_chat_id: int,
    ) -> UserRuntime:
        resolved_user = await self.identity.resolve_telegram_user(telegram_user_id)
        self.subscriptions.require_active(resolved_user)
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
            tool_store=self.tools.inject(
                resolved_user,
                timezone=user_profile.timezone,
            ),
        )
