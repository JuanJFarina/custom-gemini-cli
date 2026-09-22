from collections.abc import Mapping
from typing import TypeVar

from pydantic import BaseModel, ConfigDict

from harle_domain.profiles import AssistantProfile, InteractionFrequency
from harle_domain.tools import (
    ToolCallResult,
    ToolDefinition,
    ToolEffect,
    ToolExecutionContext,
    ToolFamily,
    ToolHandler,
)
from harle_services.profiles import AssistantProfileService

from .registry import ToolFamilyRegistration

ModelT = TypeVar("ModelT", bound=BaseModel)


class GetInteractionFrequencyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SetInteractionFrequencyArgs(BaseModel):
    interaction_frequency: InteractionFrequency

    model_config = ConfigDict(extra="forbid")


FAMILY = ToolFamily.PROFILES

SHARED_INSTRUCTIONS = """For interaction frequency:
- high uses a 12-hour probability scale.
- medium uses a 24-hour probability scale.
- low uses a 48-hour probability scale.
- The scale is when cumulative interaction probability reaches about 63%, not a fixed message interval."""

DEFINITIONS = (
    ToolDefinition(
        name="get_interaction_frequency",
        family=FAMILY,
        description="Get the user's proactive interaction frequency.",
        argument_model=GetInteractionFrequencyArgs,
        effect=ToolEffect.READ,
        can_run_concurrently=True,
    ),
    ToolDefinition(
        name="set_interaction_frequency",
        family=FAMILY,
        description=(
            "Set proactive interaction frequency to high, medium, or low when "
            "the user directly requests it."
        ),
        argument_model=SetInteractionFrequencyArgs,
        effect=ToolEffect.MODIFY,
        can_run_concurrently=False,
    ),
)


def create_internal_profiles_registration(
    service: AssistantProfileService,
) -> ToolFamilyRegistration:
    def build_handlers(
        context: ToolExecutionContext,
    ) -> Mapping[str, ToolHandler]:
        async def get_frequency(args: BaseModel) -> ToolCallResult:
            context.require_family(FAMILY)
            _require_model(args, GetInteractionFrequencyArgs)
            profile = await service.get(user_id=context.user_id)
            return ToolCallResult(
                called_tool_name="get_interaction_frequency",
                result=_frequency_payload(profile),
            )

        async def set_frequency(args: BaseModel) -> ToolCallResult:
            context.require_family(FAMILY)
            validated = _require_model(args, SetInteractionFrequencyArgs)
            profile = await service.update_interaction_frequency(
                user_id=context.user_id,
                frequency=validated.interaction_frequency,
            )
            return ToolCallResult(
                called_tool_name="set_interaction_frequency",
                result=_frequency_payload(profile),
            )

        return {
            "get_interaction_frequency": get_frequency,
            "set_interaction_frequency": set_frequency,
        }

    registration = ToolFamilyRegistration(
        family=FAMILY,
        instructions=SHARED_INSTRUCTIONS,
        definitions=DEFINITIONS,
        handler_factory=build_handlers,
    )
    return registration


def _frequency_payload(profile: AssistantProfile) -> Mapping[str, str | int]:
    frequency = profile.interaction_frequency
    return {
        "interaction_frequency": frequency.value,
        "scale_hours": int(frequency.scale.total_seconds() // 3600),
    }


def _require_model(value: BaseModel, model: type[ModelT]) -> ModelT:
    if not isinstance(value, model):
        raise TypeError(f"Expected {model.__name__}.")
    return value
