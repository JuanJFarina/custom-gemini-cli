from collections.abc import Awaitable, Callable
from functools import wraps
from time import time
from typing import Any

from google.genai.errors import APIError, ClientError, ServerError
from pydantic import ValidationError

from harle_utils import log

from .models import HarleResponse, HarleToolResult
from .settings import get_agent_settings
from .tools import show_tool_results

SETTINGS = get_agent_settings()
ASSISTANT_FAILURES = (
    APIError,
    ClientError,
    ServerError,
    RuntimeError,
    ValueError,
    ValidationError,
)


def retry(
    func: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        attempts = 0
        start_time = time()
        while attempts < SETTINGS.MAX_RETRIES:
            attempts += 1
            try:
                result = await func(*args, **kwargs)
                log.info(
                    f"{func.__name__} SUCCEDED in {time() - start_time} seconds with {attempts} attempts",
                )
                return result
            except ASSISTANT_FAILURES as e:
                log.error(f"Attempt {attempts} for {func.__name__} failed: {e}")
        log.warning(
            f"{func.__name__} FAILED in {time() - start_time} seconds with {attempts} attempts",
        )
        if func.__name__ == "_call_gemini":
            tool_results = kwargs.get("tool_results")
            if tool_results:
                return HarleResponse(
                    action="respond",
                    response=(
                        "I can't respond right now, but these are the results of "
                        f"the tool calls: {show_tool_results(tool_results)}"
                    ),
                )
            return HarleResponse(
                action="respond",
                response="I can't respond right now, sorry !",
            )
        if func.__name__ == "_call_tool":
            return HarleToolResult(
                called_tool_name="Tool name not available when creating this error message.",
                result={
                    "error": (
                        f"Tool can't be called, even after {SETTINGS.MAX_RETRIES} "
                        "attempts. Don't retry.",
                    ),
                },
            )
        raise RuntimeError(
            f"Unknown error: {func.__name__} failed after {SETTINGS.MAX_RETRIES} attempts.",
        )

    return wrapper
