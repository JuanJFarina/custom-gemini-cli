from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from custom_gemini_cli.prompts.system import SYSTEM_PROMPT
from custom_gemini_cli.runtime_context import (
    get_current_time_and_date,
    get_current_weather,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
PERSONAL_HISTORY_PATH = DATA_DIR / "juan_personal_history.md"
CONVERSATIONS_DIR = DATA_DIR / "conversations"
CONVERSATION_CONTEXT_CHAR_LIMIT = 4000


def build_system_instruction() -> str:
    return SYSTEM_PROMPT.format(
        current_time_and_date=get_current_time_and_date(),
        current_weather=get_current_weather(),
        juan_personal_history_summary=_load_personal_history(),
        latest_conversations=_load_latest_conversations(),
    )


def save_conversation(prompt: str, response_text: str, model: str) -> Path:
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)

    path = _new_conversation_path()
    path.write_text(
        _format_conversation(prompt=prompt, response_text=response_text, model=model),
        encoding="utf-8",
    )
    return path


def _load_personal_history() -> str:
    if not PERSONAL_HISTORY_PATH.is_file():
        return "No personal history has been recorded yet."

    content = PERSONAL_HISTORY_PATH.read_text(encoding="utf-8").strip()
    return content or "No personal history has been recorded yet."


def _load_latest_conversations() -> str:
    if not CONVERSATIONS_DIR.is_dir():
        return "No previous conversations yet."

    conversation_paths = sorted(CONVERSATIONS_DIR.glob("*.json"), reverse=True)
    if not conversation_paths:
        return "No previous conversations yet."

    conversations: list[str] = []
    context_length = 0
    for path in conversation_paths:
        conversation = _format_conversation_for_context(path)
        if not conversation:
            continue

        separator_length = 1 if conversations else 0
        next_context_length = context_length + separator_length + len(conversation)
        if next_context_length > CONVERSATION_CONTEXT_CHAR_LIMIT:
            break

        conversations.append(conversation)
        context_length = next_context_length

    if not conversations:
        return "No previous conversations fit within the context limit."

    return "\n".join(reversed(conversations))


def _format_conversation_for_context(path: Path) -> str:
    try:
        conversation = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""

    if not isinstance(conversation, dict):
        return ""

    conversation.pop("model", None)
    return json.dumps(conversation, ensure_ascii=False, indent=2)


def _new_conversation_path() -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    path = CONVERSATIONS_DIR / f"{timestamp}.json"
    suffix = 2
    while path.exists():
        path = CONVERSATIONS_DIR / f"{timestamp}-{suffix}.json"
        suffix += 1
    return path


def _format_conversation(prompt: str, response_text: str, model: str) -> str:
    created_at = datetime.now().isoformat(timespec="seconds")
    return json.dumps(
        {
            "conversation_date": created_at,
            "model": model,
            "juan_jose_farina_prompt": prompt,
            "response": response_text,
        },
        ensure_ascii=False,
        indent=2,
    )
