from __future__ import annotations

from argparse import ArgumentParser, Namespace
from sys import stderr
import asyncio

from harle_agent import __version__
from harle_agent.agent import Harle
from harle_agent.models.harle_models import HarleConfig, HarleStores, HarleToolStore
from harle_agent.config import DEFAULT_MODEL
from harle_agent.stores.file_store import FileConversationStore
from harle_cli.config import get_api_key, get_model, load_dotenv


async def call_harle(harle: Harle, prompt: str) -> None:
    response_text, saving_task = await harle.call(prompt)
    if response_text:
        print(f"\nGemini: {response_text}\n")
    await saving_task


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
    harle_config = HarleConfig(
        model=model,
        api_key=api_key,
    )
    harle_stores = HarleStores(
        conversation_store=FileConversationStore(),
        tool_store=HarleToolStore(),
    )
    harle = Harle(
        config=harle_config,
        stores=harle_stores,
    )

    try:
        asyncio.run(call_harle(harle, prompt))
    except Exception as exc:
        print(f"Gemini request failed: {exc}", file=stderr)
        return 1

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
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
