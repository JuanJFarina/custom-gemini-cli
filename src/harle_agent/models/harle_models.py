from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Awaitable, Callable
from harle_agent.stores.protocol import ConversationStore


class HarleConfig(BaseModel):
    model: str
    api_key: str


class HarleToolResult(BaseModel):
    tool_name: str
    result: Any


class HarleTool(BaseModel):
    tool_name: str
    tool_func: Callable[..., Awaitable[Any]]


class HarleToolStore(BaseModel):
    tools: list[HarleTool] = Field(default_factory=list)

    def get(self, tool_name: str) -> HarleTool:
        for tool in self.tools:
            if tool.tool_name == tool_name:
                return tool
        raise ValueError(f"Tool {tool_name} not found")


class HarleStores(BaseModel):
    conversation_store: ConversationStore
    tool_store: HarleToolStore

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
