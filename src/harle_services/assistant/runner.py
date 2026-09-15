from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from harle_agent.agent import Harle
from harle_agent.models import (
    HarlePersonalContext,
    HarleRunResult,
    HarleStores,
    default_harle_config,
)
from harle_domain.tools import HarleToolStore
from harle_services.runtime import UserRuntime


@dataclass(frozen=True, slots=True)
class GeneratedResponse:
    harle: Harle
    result: HarleRunResult


async def generate_response(
    *,
    prompt: str,
    user_runtime: UserRuntime,
    tool_store: HarleToolStore,
    on_tool_started: Callable[[], Awaitable[None]] | None = None,
) -> GeneratedResponse:
    user_profile = user_runtime.user_profile
    assistant_profile = user_runtime.assistant_profile
    harle = Harle(
        config=default_harle_config(),
        stores=HarleStores(
            conversation_store=user_runtime.conversation_store,
            tool_store=tool_store,
        ),
        personal_context=HarlePersonalContext(
            user_name=user_runtime.resolved_user.user.display_name,
            preferred_name=user_profile.preferred_name,
            locale=user_profile.locale,
            timezone=user_profile.timezone,
            assistant_profile=(
                f"{assistant_profile.display_name}: {assistant_profile.profile_text}"
            ),
            personal_history=(
                user_profile.personal_history
                or "No personal history has been supplied."
            ),
            latitude=(
                float(user_profile.latitude)
                if user_profile.latitude is not None
                else None
            ),
            longitude=(
                float(user_profile.longitude)
                if user_profile.longitude is not None
                else None
            ),
        ),
        on_tool_started=on_tool_started,
    )
    return GeneratedResponse(harle=harle, result=await harle.call(prompt))
