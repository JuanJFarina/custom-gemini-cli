from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from custom_gemini_cli import __version__


DEFAULT_MODEL = "gemini-2.5-flash"


def main() -> int:
    _load_dotenv()
    args = _parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(
            "Missing GEMINI_API_KEY. Set it in your environment or a .env file.",
            file=sys.stderr,
        )
        return 2

    prompt = " ".join(args.prompt).strip()
    if not prompt:
        print("Prompt cannot be empty.", file=sys.stderr)
        return 2

    model = args.model or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
    client = genai.Client(api_key=api_key)

    try:
        response = _generate_content(client, model, prompt)
    except Exception as exc:
        if model != DEFAULT_MODEL and _is_unavailable_model_error(exc):
            print(
                f"Configured model '{model}' is unavailable; retrying with {DEFAULT_MODEL}.",
                file=sys.stderr,
            )
            try:
                response = _generate_content(client, DEFAULT_MODEL, prompt)
            except Exception as retry_exc:
                print(f"Gemini request failed: {retry_exc}", file=sys.stderr)
                return 1
        else:
            print(f"Gemini request failed: {exc}", file=sys.stderr)
            return 1
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    text = (response.text or "").strip()
    if text:
        print(text)

    if args.show_sources:
        _print_sources(response)

    return 0


def _generate_content(client: genai.Client, model: str, prompt: str) -> Any:
    return client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[
                types.Tool(
                    google_search=types.GoogleSearch(),
                )
            ]
        ),
    )


def _is_unavailable_model_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "not_found" in message and "model" in message and "unavailable" in message


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="gemini",
        description="Ask Gemini with Google Search grounding enabled.",
    )
    parser.add_argument(
        "prompt",
        nargs="+",
        help="Prompt to send to Gemini. Quote it to pass it as one argument.",
    )
    parser.add_argument(
        "--model",
        help=f"Gemini model to use. Defaults to GEMINI_MODEL or {DEFAULT_MODEL}.",
    )
    parser.add_argument(
        "--show-sources",
        action="store_true",
        help="Print source URLs from grounding metadata when available.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args()


def _load_dotenv() -> None:
    project_dotenv = Path(__file__).resolve().parents[2] / ".env"
    candidates = [Path.cwd() / ".env", project_dotenv]

    for path in dict.fromkeys(candidates):
        if not path.is_file():
            continue

        for line in path.read_text(encoding="utf-8").splitlines():
            key, value = _parse_env_line(line)
            if key and key not in os.environ:
                os.environ[key] = value


def _parse_env_line(line: str) -> tuple[str | None, str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None, ""

    if stripped.startswith("export "):
        stripped = stripped.removeprefix("export ").strip()

    key, separator, value = stripped.partition("=")
    if not separator:
        return None, ""

    key = key.strip()
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]

    return key, value


def _print_sources(response: Any) -> None:
    sources = list(_extract_sources(response))
    if not sources:
        return

    print("\nSources:")
    for index, source in enumerate(sources, start=1):
        title = source["title"]
        uri = source["uri"]
        print(f"{index}. {title} - {uri}")


def _extract_sources(response: Any) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[str] = set()

    for candidate in _get(response, "candidates") or []:
        metadata = _get(candidate, "grounding_metadata") or _get(
            candidate, "groundingMetadata"
        )
        for chunk in _get(metadata, "grounding_chunks") or _get(
            metadata, "groundingChunks"
        ) or []:
            web = _get(chunk, "web")
            uri = _get(web, "uri")
            if not uri or uri in seen:
                continue

            seen.add(uri)
            sources.append(
                {
                    "title": _get(web, "title") or uri,
                    "uri": uri,
                }
            )

    return sources


def _get(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


if __name__ == "__main__":
    raise SystemExit(main())
