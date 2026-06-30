from __future__ import annotations

from typing import Protocol


class ConversationStore(Protocol):
    def load_conversations(self) -> str:
        """Return conversation context ready to inject into the system prompt."""

    def save_conversation(self, *, prompt: str, response_text: str, model: str) -> None:
        """Persist the final user prompt and assistant response."""

