from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter

from harle_agent.settings import get_agent_settings
from harle_agent.stores.protocol import ConversationStore

from .harle_tool import HarleToolStore


class HarleConfig(BaseModel):
    model: str = get_agent_settings().GEMINI_MODEL
    api_key: str = get_agent_settings().GEMINI_API_KEY


class HarleResponse(BaseModel):
    action: Literal["respond"]
    response: str


class HarleToolCall(BaseModel):
    action: Literal["call_tool"]
    tool_name: Literal["add_non_credit_transaction"]
    tool_args: dict[str, Any]


HarleThought = HarleResponse | HarleToolCall

HarleThoughtAdapter = TypeAdapter(HarleThought, config={"discriminator": "action"})  # type: ignore[call-overload]


class HarleStores(BaseModel):
    conversation_store: ConversationStore
    tool_store: HarleToolStore

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
