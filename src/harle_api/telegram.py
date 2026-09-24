import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from harle_domain.messaging import TelegramMediaReference

from .media import MAX_MEDIA_REQUEST_SIZE, RejectedMedia, extract_media

TELEGRAM_LINK_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


@dataclass(frozen=True)
class IncomingTelegramMessage:
    update_id: int
    chat_id: int
    user_id: int
    user_name: str
    text: str
    media: TelegramMediaReference | None = None


@dataclass(frozen=True)
class UnsupportedTelegramMedia:
    update_id: int
    chat_id: int
    user_id: int
    user_name: str
    reason: str


@dataclass(frozen=True)
class _TelegramEnvelope:
    update_id: int
    chat_id: int
    user_id: int
    user_name: str
    message: Mapping[str, object]


def extract_telegram_message(
    update: Mapping[str, object],
    maximum_request_size: int = MAX_MEDIA_REQUEST_SIZE,
) -> IncomingTelegramMessage | UnsupportedTelegramMedia | None:
    envelope = _telegram_envelope(update)
    if envelope is None:
        return None
    return _message_content(envelope, maximum_request_size)


def extract_telegram_link_token(text: str) -> str | None:
    command, separator, token = text.strip().partition(" ")
    if command.split("@", maxsplit=1)[0] != "/start" or not separator:
        return None
    normalized = token.strip()
    if not TELEGRAM_LINK_TOKEN_PATTERN.fullmatch(normalized):
        return None
    return normalized


def _telegram_envelope(
    update: Mapping[str, object],
) -> _TelegramEnvelope | None:
    update_id = _parse_update_id(update.get("update_id"))
    if update_id is None:
        return None
    message = update.get("message")
    if not isinstance(message, Mapping):
        return None
    chat = message.get("chat")
    from_user = message.get("from")
    if not all((isinstance(chat, Mapping), isinstance(from_user, Mapping))):
        return None
    chat = cast(Mapping[str, object], chat)
    from_user = cast(Mapping[str, object], from_user)
    chat_id = _parse_int(chat.get("id"))
    user_id = _parse_int(from_user.get("id"))
    if chat_id in (None, 0) or user_id is None or user_id <= 0:
        return None
    return _TelegramEnvelope(
        update_id=update_id,
        chat_id=cast(int, chat_id),
        user_id=cast(int, user_id),
        user_name=_display_name(from_user, fallback=f"Telegram user {user_id}"),
        message=message,
    )


def _message_content(
    envelope: _TelegramEnvelope,
    maximum_request_size: int,
) -> IncomingTelegramMessage | UnsupportedTelegramMedia | None:
    text = _parse_str(envelope.message.get("text"))
    if text:
        return IncomingTelegramMessage(
            update_id=envelope.update_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
            user_name=envelope.user_name,
            text=text,
        )

    media = extract_media(
        envelope.update_id,
        envelope.message,
        maximum_request_size,
    )
    if isinstance(media, RejectedMedia):
        return UnsupportedTelegramMedia(
            update_id=envelope.update_id,
            chat_id=envelope.chat_id,
            user_id=envelope.user_id,
            user_name=envelope.user_name,
            reason=media.reason,
        )
    if media is None:
        return None

    caption = _parse_str(envelope.message.get("caption"))
    prompt = "\n".join(filter(None, (media.prompt_marker, caption)))
    return IncomingTelegramMessage(
        update_id=envelope.update_id,
        chat_id=envelope.chat_id,
        user_id=envelope.user_id,
        user_name=envelope.user_name,
        text=prompt,
        media=media,
    )


def _parse_update_id(value: object) -> int | None:
    parsed = _parse_int(value)
    if parsed is None:
        return None
    return parsed if parsed >= 0 else None


def _parse_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _display_name(user: Mapping[str, object], *, fallback: str) -> str:
    first_name = _parse_str(user.get("first_name"))
    last_name = _parse_str(user.get("last_name"))
    username = _parse_str(user.get("username"))

    full_name = " ".join(filter(None, (first_name, last_name)))
    if full_name:
        return full_name
    if username:
        return f"@{username}"
    return fallback


def _parse_str(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""
