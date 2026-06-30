from __future__ import annotations

from typing import Any, Iterable

from google import genai
from google.genai import types


def create_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def generate_content(
    client: genai.Client,
    model: str,
    prompt: str,
    system_instruction: str,
) -> Any:
    return client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[
                types.Tool(
                    google_search=types.GoogleSearch(),
                )
            ]
        ),
    )


def generate_content_with_tools(
    client: genai.Client,
    model: str,
    contents: Any,
    system_instruction: str,
    tools: Iterable[Any],
) -> Any:
    return client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=list(tools),
        ),
    )


def generate_grounded_content(
    client: genai.Client,
    model: str,
    contents: Any,
    system_instruction: str,
) -> Any:
    return client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[
                types.Tool(
                    google_search=types.GoogleSearch(),
                )
            ],
        ),
    )


def extract_response_text(response: Any) -> str:
    candidates = _get(response, "candidates") or []
    if not candidates:
        return ""

    content = _get(candidates[0], "content")
    parts = _get(content, "parts") or []
    text_parts: list[str] = []

    for part in parts:
        if _get(part, "thought"):
            continue

        text = _get(part, "text")
        if isinstance(text, str) and text.strip():
            text_parts.append(text.strip())

    if not text_parts:
        return ""

    return text_parts[-1] if len(text_parts) > 1 else text_parts[0]


def extract_function_calls(response: Any) -> list[Any]:
    function_calls = _get(response, "function_calls") or _get(response, "functionCalls")
    if function_calls:
        return list(function_calls)

    candidates = _get(response, "candidates") or []
    if not candidates:
        return []

    content = _get(candidates[0], "content")
    parts = _get(content, "parts") or []
    calls: list[Any] = []
    for part in parts:
        function_call = _get(part, "function_call") or _get(part, "functionCall")
        if function_call:
            calls.append(function_call)

    return calls


def get_first_candidate_content(response: Any) -> Any:
    candidates = _get(response, "candidates") or []
    if not candidates:
        return None
    return _get(candidates[0], "content")


def is_unavailable_model_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "not_found" in message and "model" in message and "unavailable" in message


def _get(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)
