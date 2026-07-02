from pathlib import Path

from harle_utils import Settings


class ApiSettings(Settings):
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_ALLOWED_USER_ID: int
    TELEGRAM_WEBHOOK_SECRET: str
    SQLITE_PATH: str
    VERCEL: bool = True

    @property
    def RESOLVED_SQLITE_PATH(self) -> Path:  # pylint: disable=invalid-name
        return Path(self.SQLITE_PATH)


API_SETTINGS: ApiSettings | None = None


def get_settings() -> ApiSettings:
    global API_SETTINGS  # pylint: disable=global-statement
    if API_SETTINGS is None:
        API_SETTINGS = ApiSettings()
    return API_SETTINGS
