from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

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
    tool_name: Literal[
        "add_one_time_transaction",
        "add_in_installments_transaction",
        "get_day_expenses",
        "get_month_expenses",
        "remove_or_update_transaction",
    ]
    tool_args: dict[str, Any]


HarleThought = Annotated[
    HarleResponse | HarleToolCall,
    Field(discriminator="action"),
]

HarleThoughtAdapter: TypeAdapter[HarleThought] = TypeAdapter(HarleThought)


class HarleStores(BaseModel):
    conversation_store: ConversationStore
    tool_store: HarleToolStore

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
