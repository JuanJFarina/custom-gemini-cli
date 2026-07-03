from typing import Protocol, runtime_checkable

from harle_agent.settings import get_agent_settings

TOKENS_CAP = get_agent_settings().MAX_CONVERSATION_TOKENS


@runtime_checkable
class ConversationStore(Protocol):
    async def load(self, *, max_tokens: int = TOKENS_CAP) -> str:
        """Return conversation context ready to inject into the system prompt.
        The context is limited to max_tokens tokens."""

    async def save(self, *, prompt: str, response_text: str, model: str) -> None:
        """Persist the final user prompt and assistant response."""
