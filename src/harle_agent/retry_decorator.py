from collections.abc import Awaitable, Callable
from functools import wraps
from time import time
from typing import Any

from harle_utils import log

from .models.harle_models import HarleToolResult
from .reasoning import (
    HarleThought,
)
from .settings import get_agent_settings
from .tools import show_tool_results

Settings = get_agent_settings()


def retry(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        attempts = 0
        time_taken = time()
        while attempts < Settings.MAX_RETRIES:
            try:
                result = await func(*args, **kwargs)
                time_taken = time() - time_taken
                log.info(
                    f"{func.__name__} SUCCEDED in {time_taken} seconds with {attempts} attempts",
                )
                return result
            except Exception as e:  # pylint: disable=broad-exception-caught
                attempts += 1
                log.error(f"Attempt {attempts} for {func.__name__} failed: {e}")
        time_taken = time() - time_taken
        log.warning(
            f"{func.__name__} FAILED in {time_taken} seconds with {attempts} attempts",
        )
        if func.__name__ == "_call_gemini":
            tool_results = kwargs.get("tool_results")
            if tool_results:
                return HarleThought(
                    action="respond",
                    response=(
                        "I can't respond right now, but these are the results of "
                        f"the tool calls: {show_tool_results(tool_results)}"
                    ),
                )
            return HarleThought(
                action="respond",
                response="I can't respond right now, sorry !",
            )
        if func.__name__ == "_call_tool":
            return HarleToolResult(
                tool_name="Tool name not available when creating this error message.",
                result={
                    "error": (
                        f"Tool can't be called, even after {Settings.MAX_RETRIES} "
                        "attempts. Don't retry.",
                    ),
                },
            )
        raise RuntimeError(
            f"Unknown error: {func.__name__} failed after {Settings.MAX_RETRIES} attempts.",
        )

    return wrapper
