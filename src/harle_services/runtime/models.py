from dataclasses import dataclass

from harle_domain.accounts import ResolvedUser
from harle_domain.conversations.ports import ConversationStore
from harle_domain.profiles import AssistantProfile, UserProfile
from harle_domain.tools import HarleToolStore


@dataclass(frozen=True, slots=True)
class UserRuntime:
    resolved_user: ResolvedUser
    user_profile: UserProfile
    assistant_profile: AssistantProfile
    telegram_chat_id: int
    telegram_update_id: int
    conversation_store: ConversationStore
    tool_store: HarleToolStore
