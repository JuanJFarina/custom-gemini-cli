import asyncio
from argparse import ArgumentParser, Namespace
from sys import stderr

from harle_agent import __version__
from harle_agent.agent import Harle
from harle_agent.models import HarleStores, HarleToolStore
from harle_agent.stores import FileConversationStore


async def call_harle(harle: Harle, prompt: str) -> None:
    response_text, saving_task = await harle.call(prompt)
    if response_text:
        print(f"\nGemini: {response_text}\n")
    await saving_task


def main() -> int:
    args = _parse_args()

    prompt = " ".join(args.prompt).strip()
    if not prompt:
        print("Prompt cannot be empty.", file=stderr)
        return 2

    harle_stores = HarleStores(
        conversation_store=FileConversationStore(),
        tool_store=HarleToolStore(),
    )
    harle = Harle(
        stores=harle_stores,
    )

    try:
        asyncio.run(call_harle(harle, prompt))
    except Exception as exc:  # pylint: disable=broad-exception-caught
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
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
