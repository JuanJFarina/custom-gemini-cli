from functools import cache

from harle_utils import Settings


class ApiSettings(Settings):
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_WEBHOOK_SECRET: str
    POSTGRES_DATABASE_URL: str
    POSTGRES_POOL_MIN_SIZE: int = 1
    POSTGRES_POOL_MAX_SIZE: int = 5
    EVENT_SCHEDULER_INTERVAL_SECONDS: float = 300
    MAX_MEDIA_REQUEST_SIZE: int = 12 * 1024 * 1024


@cache
def get_settings() -> ApiSettings:
    return ApiSettings()
