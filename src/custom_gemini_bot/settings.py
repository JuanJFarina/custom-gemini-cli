from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from custom_gemini_cli.config import DEFAULT_MODEL, load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data" / "bot_conversations.sqlite3"


@dataclass(frozen=True)
class BotSettings:
    gemini_api_key: str | None
    gemini_model: str
    telegram_bot_token: str | None
    telegram_allowed_user_id: int | None
    telegram_webhook_secret: str | None
    sqlite_path: Path

    def require_gemini_api_key(self) -> str:
        if not self.gemini_api_key:
            raise RuntimeError("Missing GEMINI_API_KEY.")
        return self.gemini_api_key

    def require_telegram_bot_token(self) -> str:
        if not self.telegram_bot_token:
            raise RuntimeError("Missing TELEGRAM_BOT_TOKEN.")
        return self.telegram_bot_token

    def require_telegram_allowed_user_id(self) -> int:
        if self.telegram_allowed_user_id is None:
            raise RuntimeError("Missing or invalid TELEGRAM_ALLOWED_USER_ID.")
        return self.telegram_allowed_user_id

    def require_telegram_webhook_secret(self) -> str:
        if not self.telegram_webhook_secret:
            raise RuntimeError("Missing TELEGRAM_WEBHOOK_SECRET.")
        return self.telegram_webhook_secret


def get_settings() -> BotSettings:
    load_dotenv()
    sqlite_path = Path(os.environ.get("SQLITE_PATH", str(DEFAULT_SQLITE_PATH))).expanduser()

    return BotSettings(
        gemini_api_key=os.environ.get("GEMINI_API_KEY"),
        gemini_model=os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL,
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN"),
        telegram_allowed_user_id=_parse_int(os.environ.get("TELEGRAM_ALLOWED_USER_ID")),
        telegram_webhook_secret=os.environ.get("TELEGRAM_WEBHOOK_SECRET"),
        sqlite_path=sqlite_path,
    )


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except ValueError:
        return None

