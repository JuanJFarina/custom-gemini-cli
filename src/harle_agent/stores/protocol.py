from typing import Protocol, runtime_checkable

MAX_CONVERSATION_TOKENS = 4000


@runtime_checkable
class ConversationStore(Protocol):
    async def load(self, *, max_tokens: int = MAX_CONVERSATION_TOKENS) -> str:
        """Return conversation context ready to inject into the system prompt.
        The context is limited to max_tokens tokens."""

    async def save(self, *, prompt: str, response_text: str, model: str) -> None:
        """Persist the final user prompt and assistant response."""
