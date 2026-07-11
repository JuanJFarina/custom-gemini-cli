from typing import Protocol, runtime_checkable

from .harle_tool import HarleToolInteraction


@runtime_checkable
class ConversationStore(Protocol):
    async def load(self) -> str: ...

    async def save(self, *, prompt: str, response_text: str, model: str) -> None: ...

    async def save_tool_call(
        self,
        *,
        interaction: HarleToolInteraction,
        model: str,
    ) -> None: ...
