from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field


class HarleToolResult(BaseModel):
    called_tool_name: str
    result: Any


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
