from __future__ import annotations

from argparse import ArgumentParser, Namespace
from sys import stderr

from harle_agent import __version__
from harle_agent.agent import Harle
from harle_agent.config import DEFAULT_MODEL
from harle_agent.stores.file_store import FileConversationStore
from harle_agent.tools.expenses import build_expense_tool_from_env
from harle_cli.config import get_api_key, get_model, load_dotenv
from harle_cli.grounding import print_sources


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
    harle = Harle(
        model=model,
        api_key=api_key,
        conversation_store=FileConversationStore(),
        expense_tool=build_expense_tool_from_env(),
    )

    try:
        response_text = harle.respond(prompt)
    except Exception as exc:
        print(f"Gemini request failed: {exc}", file=stderr)
        return 1

    if harle.effective_model != model and harle.effective_model == DEFAULT_MODEL:
        print(
            f"Configured model '{model}' is unavailable; retried with {DEFAULT_MODEL}.",
            file=stderr,
        )

    if response_text:
        print(f"\nGemini: {response_text}\n")

    if args.show_sources and harle.last_response is not None:
        print_sources(harle.last_response)

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
