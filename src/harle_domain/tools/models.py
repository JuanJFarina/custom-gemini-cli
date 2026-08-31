import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from harle_utils import ToolUnavailableError


class ToolFamily(str, Enum):
    INTERNAL_EXPENSES = "internal_expenses"
    INTERNAL_EVENTS = "internal_events"
    PROFILES = "profiles"
    LEGACY_GOOGLE_SHEETS_EXPENSES = "legacy_google_sheets_expenses"


class ToolEffect(str, Enum):
    READ = "read"
    MODIFY = "modify"


class ToolCall(BaseModel):
    tool_name: str = Field(min_length=1)
    tool_args: Mapping[str, object]
    direct_request_quote: str | None = None

    model_config = ConfigDict(extra="forbid")


class ToolCallAction(BaseModel):
    action: Literal["call_tool"]
    calls: list[ToolCall] = Field(min_length=1, max_length=5)


class ToolCallResult(BaseModel):
    called_tool_name: str
    result: object


class InternalToolCallInteraction(BaseModel):
    tool_calls: list[ToolCall]
    tool_results: list[ToolCallResult]

    @property
    def tool_call_response(self) -> ToolCallAction:
        return ToolCallAction(action="call_tool", calls=self.tool_calls)


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    family: ToolFamily
    description: str
    argument_model: type[BaseModel]
    effect: ToolEffect
    can_run_concurrently: bool

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Tool name cannot be empty.")
        if not self.description.strip():
            raise ValueError("Tool description cannot be empty.")
        if self.effect is ToolEffect.MODIFY and self.can_run_concurrently:
            raise ValueError("Modifying tools cannot run concurrently.")

    @property
    def prompt(self) -> str:
        schema = json.dumps(
            self.argument_model.model_json_schema(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return (
            f'## "{self.name}" tool\n\n'
            f"- Effect: {self.effect.value}\n"
            f"- {self.description}\n"
            f"- Arguments JSON Schema: {schema}"
        )


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    user_id: UUID
    authorized_families: frozenset[ToolFamily]

    def require_family(self, family: ToolFamily) -> None:
        if family not in self.authorized_families:
            raise ToolUnavailableError("This tool is unavailable.")


ToolHandler = Callable[[BaseModel], Awaitable[ToolCallResult]]


@dataclass(frozen=True, slots=True)
class HarleTool:
    definition: ToolDefinition
    handler: ToolHandler

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def prompt(self) -> str:
        return self.definition.prompt

    @property
    def can_run_concurrently(self) -> bool:
        return self.definition.can_run_concurrently


@dataclass(frozen=True, slots=True)
class HarleToolStore:
    tools: Sequence[HarleTool] = ()
    family_instructions: Sequence[str] = ()

    def get(self, tool_name: str) -> HarleTool:
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        raise ToolUnavailableError("This tool is unavailable.")

    @property
    def prompt(self) -> str:
        sections = [*self.family_instructions, *(tool.prompt for tool in self.tools)]
        return "\n\n".join(sections)
