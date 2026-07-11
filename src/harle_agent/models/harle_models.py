from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from harle_agent.settings import get_agent_settings

from .conversation_store import ConversationStore
from .harle_tool import HarleToolCall, HarleToolInteraction, HarleToolStore


class HarleConfig(BaseModel):
    model: str = get_agent_settings().GEMINI_MODEL
    api_key: str = get_agent_settings().GEMINI_API_KEY


class HarleResponse(BaseModel):
    action: Literal["respond"]
    response: str


HarleThought = Annotated[
    HarleResponse | HarleToolCall,
    Field(discriminator="action"),
]

HarleThoughtAdapter: TypeAdapter[HarleThought] = TypeAdapter(HarleThought)


class HarleStores(BaseModel):
    conversation_store: ConversationStore
    tool_store: HarleToolStore

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


class HarleRunResult(BaseModel):
    response_text: str
    tool_interactions: list[HarleToolInteraction] = Field(default_factory=list)
