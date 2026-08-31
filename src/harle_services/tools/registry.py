from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from harle_domain.tools import (
    HarleTool,
    HarleToolStore,
    ToolDefinition,
    ToolExecutionContext,
    ToolFamily,
    ToolHandler,
)
from harle_utils import ToolUnavailableError

ToolHandlerFactory = Callable[
    [ToolExecutionContext],
    Mapping[str, ToolHandler],
]


@dataclass(frozen=True, slots=True)
class ToolFamilyRegistration:
    family: ToolFamily
    instructions: str
    definitions: Sequence[ToolDefinition]
    handler_factory: ToolHandlerFactory

    def __post_init__(self) -> None:
        if not self.instructions.strip():
            raise ValueError("Tool family instructions cannot be empty.")
        names = [definition.name for definition in self.definitions]
        if len(names) != len(set(names)):
            raise ValueError("Tool names must be unique within a family.")
        if any(definition.family is not self.family for definition in self.definitions):
            raise ValueError("Tool definition belongs to a different family.")


@dataclass(frozen=True, slots=True)
class ToolRegistry:
    registrations: Sequence[ToolFamilyRegistration]

    def __post_init__(self) -> None:
        families = [registration.family for registration in self.registrations]
        if len(families) != len(set(families)):
            raise ValueError("Tool families must be registered only once.")

    @property
    def families(self) -> frozenset[ToolFamily]:
        return frozenset(registration.family for registration in self.registrations)

    def build_store(
        self,
        *,
        user_id: UUID,
        authorized_families: frozenset[ToolFamily],
    ) -> HarleToolStore:
        unavailable = authorized_families - self.families
        if unavailable:
            raise ToolUnavailableError("An authorized tool family is unavailable.")

        context = ToolExecutionContext(
            user_id=user_id,
            authorized_families=authorized_families,
        )
        tools: list[HarleTool] = []
        instructions: list[str] = []
        for registration in self.registrations:
            if registration.family not in authorized_families:
                continue
            handlers = registration.handler_factory(context)
            expected_names = {
                definition.name for definition in registration.definitions
            }
            if set(handlers) != expected_names:
                raise ValueError("Tool handlers do not match registered definitions.")
            tools.extend(
                HarleTool(
                    definition=definition,
                    handler=handlers[definition.name],
                )
                for definition in registration.definitions
            )
            instructions.append(registration.instructions)

        return HarleToolStore(
            tools=tuple(tools),
            family_instructions=tuple(instructions),
        )
