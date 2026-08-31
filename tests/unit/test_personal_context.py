import asyncio

import pytest
from pydantic import ValidationError

from harle_agent.environment_knowledge import (
    WEATHER_UNAVAILABLE,
    get_current_time_and_date,
    get_current_weather,
)
from harle_agent.models import HarlePersonalContext
from harle_agent.prompts import SYSTEM_PROMPT


def test_personal_context_requires_valid_timezone_and_location_pair() -> None:
    common = {
        "user_name": "Beta User",
        "preferred_name": "Beta",
        "locale": "en-US",
        "assistant_profile": "A concise AI assistant.",
        "personal_history": "No history.",
    }

    with pytest.raises(ValidationError):
        HarlePersonalContext(**common, timezone="Invalid/Timezone")
    with pytest.raises(ValidationError):
        HarlePersonalContext(**common, timezone="UTC", latitude=10)


def test_environment_context_uses_supplied_profile_values() -> None:
    assert "UTC" in get_current_time_and_date("UTC")
    assert (
        asyncio.run(
            get_current_weather(
                latitude=None,
                longitude=None,
                timezone_name="UTC",
            ),
        )
        == WEATHER_UNAVAILABLE
    )


def test_system_prompt_is_generic_and_transparent() -> None:
    assert "Juan" not in SYSTEM_PROMPT
    assert "real human being" not in SYSTEM_PROMPT
    assert "transparent that you are AI" in SYSTEM_PROMPT
