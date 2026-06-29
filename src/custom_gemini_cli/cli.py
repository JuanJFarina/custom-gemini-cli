from __future__ import annotations

from argparse import ArgumentParser, Namespace
from sys import stderr

from custom_gemini_cli import __version__
from .config import DEFAULT_MODEL, get_api_key, get_model, load_dotenv
from .gemini import (
    create_client,
    extract_response_text,
    generate_content,
    is_unavailable_model_error,
)
from .grounding import print_sources
from .memory import build_system_instruction, save_conversation


def main() -> int:
    load_dotenv()
    args = _parse_args()

    api_key = get_api_key()
    if not api_key:
        return 2

    prompt = " ".join(args.prompt).strip()
    if not prompt:
        print("Prompt cannot be empty.", file=stderr)
        return 2

    model = get_model(args.model)
    effective_model = model
    system_instruction = build_system_instruction()
    client = create_client(api_key=api_key)

    try:
        response = generate_content(client, model, prompt, system_instruction)
    except Exception as exc:
        if model != DEFAULT_MODEL and is_unavailable_model_error(exc):
            print(
                f"Configured model '{model}' is unavailable; retrying with {DEFAULT_MODEL}.",
                file=stderr,
            )
            try:
                response = generate_content(
                    client,
                    DEFAULT_MODEL,
                    prompt,
                    system_instruction,
                )
                effective_model = DEFAULT_MODEL
            except Exception as retry_exc:
                print(f"Gemini request failed: {retry_exc}", file=stderr)
                return 1
        else:
            print(f"Gemini request failed: {exc}", file=stderr)
            return 1
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    response_text = extract_response_text(response)
    if response_text:
        print(f"\nGemini: {response_text}\n")

    if args.show_sources:
        print_sources(response)

    save_conversation(prompt=prompt, response_text=response_text, model=effective_model)

    return 0


def _parse_args() -> Namespace:
    parser = ArgumentParser(
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


if __name__ == "__main__":
    raise SystemExit(main())
