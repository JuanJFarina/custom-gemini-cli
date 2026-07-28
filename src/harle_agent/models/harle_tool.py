from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    tool_name: Literal[
        "add_one_time_transaction",
        "add_in_installments_transaction",
        "get_day_expenses",
        "get_month_expenses",
        "remove_or_update_transaction",
    ]
    tool_args: dict[str, Any]


class ToolCallAction(BaseModel):
    action: Literal["call_tool"]
    calls: list[ToolCall] = Field(min_length=1, max_length=5)


class ToolCallResult(BaseModel):
    called_tool_name: str
    result: Any


class InternalToolCallInteraction(BaseModel):
    tool_calls: list[ToolCall]
    tool_results: list[ToolCallResult]

    @property
    def tool_call_response(self) -> ToolCallAction:
        return ToolCallAction(action="call_tool", calls=self.tool_calls)


class HarleTool(BaseModel):
    name: str
    func: Callable[..., Awaitable[ToolCallResult]]
    prompt: str
    can_run_concurrently: bool


class HarleToolStore(BaseModel):
    tools: list[HarleTool] = Field(default_factory=list)

    def get(self, tool_name: str) -> HarleTool:
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        raise ValueError(f"Tool {tool_name} not found")
