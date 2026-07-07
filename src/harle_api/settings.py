from pathlib import Path

from harle_utils import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data" / "bot_conversations.sqlite3"
VERCEL_SQLITE_DIR = Path("/tmp")


class ApiSettings(Settings):
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_ALLOWED_USER_ID: int
    TELEGRAM_WEBHOOK_SECRET: str
    TELEGRAM_USER_NAME: str | None = "Juan José Farina"
    POSTGRES_DATABASE_URL: str | None = None
    POSTGRES_POOL_MIN_SIZE: int = 1
    POSTGRES_POOL_MAX_SIZE: int = 5
    SQLITE_PATH: str | None = None
    VERCEL: bool = False

    @property
    def RESOLVED_SQLITE_PATH(self) -> Path:  # pylint: disable=invalid-name
        if not self.VERCEL:
            return Path(self.SQLITE_PATH or str(DEFAULT_SQLITE_PATH)).expanduser()

        if not self.SQLITE_PATH:
            return VERCEL_SQLITE_DIR / DEFAULT_SQLITE_PATH.name

        path = Path(self.SQLITE_PATH).expanduser()
        if path.is_absolute():
            try:
                path.relative_to(VERCEL_SQLITE_DIR)
            except ValueError:
                pass
            else:
                return path

        return VERCEL_SQLITE_DIR / path.name


API_SETTINGS: ApiSettings | None = None


def get_settings() -> ApiSettings:
    global API_SETTINGS  # pylint: disable=global-statement
    if API_SETTINGS is None:
        API_SETTINGS = ApiSettings()
    return API_SETTINGS
