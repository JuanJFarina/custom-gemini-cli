from typing import Protocol, runtime_checkable

from harle_domain.tools.models import InternalToolCallInteraction


@runtime_checkable
class ConversationStore(Protocol):
    async def load(self) -> str: ...

    async def save(self, *, prompt: str, response_text: str, model: str) -> None: ...

    async def save_tool_call(
        self,
        *,
        interaction: InternalToolCallInteraction,
        interaction_index: int,
        model: str,
    ) -> None: ...
