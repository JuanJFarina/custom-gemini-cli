from __future__ import annotations

import os
from sys import stderr

from harle_agent.config import DEFAULT_MODEL


def get_api_key() -> str | None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return api_key

    print(
        "Missing GEMINI_API_KEY. Set it in your environment or a .env file.",
        file=stderr,
    )
    return None


def get_model(cli_model: str | None) -> str:
    return cli_model or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
