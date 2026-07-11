from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, Field


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


class HarleToolResult(BaseModel):
    called_tool_name: str
    result: Any


class HarleToolInteraction(BaseModel):
    tool_call: HarleToolCall
    tool_result: HarleToolResult


class HarleTool(BaseModel):
    name: str
    func: Callable[..., Awaitable[HarleToolResult]]
    prompt: str


class HarleToolStore(BaseModel):
    tools: list[HarleTool] = Field(default_factory=list)

    def get(self, tool_name: str) -> HarleTool:
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        raise ValueError(f"Tool {tool_name} not found")
