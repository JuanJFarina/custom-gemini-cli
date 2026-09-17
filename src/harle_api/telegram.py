from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class IncomingTelegramMessage:
    update_id: int
    chat_id: int
    user_id: int
    user_name: str
    text: str


def extract_text_message(
    update: Mapping[str, object],
) -> IncomingTelegramMessage | None:
    update_id = _parse_update_id(update.get("update_id"))
    if update_id is None:
        return None

    message = update.get("message")
    if not isinstance(message, Mapping):
        return None

    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        return None

    chat = message.get("chat")
    from_user = message.get("from")
    if not isinstance(chat, Mapping) or not isinstance(from_user, Mapping):
        return None

    chat_id = _parse_int(chat.get("id"))
    user_id = _parse_int(from_user.get("id"))
    if chat_id is None or chat_id == 0 or user_id is None or user_id <= 0:
        return None

    return IncomingTelegramMessage(
        update_id=update_id,
        chat_id=chat_id,
        user_id=user_id,
        user_name=_display_name(from_user, fallback=f"Telegram user {user_id}"),
        text=text.strip(),
    )


def _parse_update_id(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _parse_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _display_name(user: Mapping[str, object], *, fallback: str) -> str:
    first_name = _parse_str(user.get("first_name"))
    last_name = _parse_str(user.get("last_name"))
    username = _parse_str(user.get("username"))

    full_name = " ".join(part for part in [first_name, last_name] if part)
    if full_name:
        return full_name
    if username:
        return f"@{username}"
    return fallback


def _parse_str(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""
