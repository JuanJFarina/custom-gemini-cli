from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from harle_agent.memory import CONVERSATIONS_DIR

from .protocol import MAX_CONVERSATION_TOKENS


class FileConversationStore:
    def __init__(self, conversations_dir: Path = CONVERSATIONS_DIR) -> None:
        self.conversations_dir = conversations_dir

    async def load(self, *, max_tokens: int = MAX_CONVERSATION_TOKENS) -> str:
        return await asyncio.to_thread(self._load_sync, max_tokens=max_tokens)

    def _load_sync(self, *, max_tokens: int = MAX_CONVERSATION_TOKENS) -> str:
        if not self.conversations_dir.is_dir():
            return "No previous conversations yet."

        conversation_paths = sorted(self.conversations_dir.glob("*.json"), reverse=True)
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
            if (next_context_length / 4) > max_tokens:
                break

            conversations.append(conversation)
            context_length = next_context_length

        if not conversations:
            return "No previous conversations fit within the context limit."

        return "\n".join(reversed(conversations))

    async def save(self, *, prompt: str, response_text: str, model: str) -> None:
        await asyncio.to_thread(
            self._save_sync,
            prompt=prompt,
            response_text=response_text,
            model=model,
        )

    def _save_sync(self, *, prompt: str, response_text: str, model: str) -> None:
        self.conversations_dir.mkdir(parents=True, exist_ok=True)
        path = self._new_conversation_path()
        path.write_text(
            _format_conversation(
                prompt=prompt,
                response_text=response_text,
                model=model,
            ),
            encoding="utf-8",
        )

    def _new_conversation_path(self) -> Path:
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        path = self.conversations_dir / f"{timestamp}.json"
        suffix = 2
        while path.exists():
            path = self.conversations_dir / f"{timestamp}-{suffix}.json"
            suffix += 1
        return path


def _format_conversation_for_context(path: Path) -> str:
    try:
        conversation = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""

    if not isinstance(conversation, dict):
        return ""

    conversation.pop("model", None)
    return json.dumps(conversation, ensure_ascii=False, indent=2)


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
