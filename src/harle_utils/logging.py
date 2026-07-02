import logging as stdlib_logging
import os
import sys
from enum import Enum

from dotenv import load_dotenv

LOGGER_NAME = "harle"
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


DEFAULT_LOG_LEVEL = LogLevel.WARNING


def get_log_level() -> LogLevel:
    load_dotenv()
    return parse_log_level(os.getenv("HARLE_LOG_LEVEL"))


def parse_log_level(value: str | None) -> LogLevel:
    if not value:
        return DEFAULT_LOG_LEVEL

    try:
        return LogLevel(value.strip().upper())
    except ValueError:
        return DEFAULT_LOG_LEVEL


def configure_logging(level: LogLevel | str | None = None) -> None:
    log_level = _resolve_log_level(level)
    stdlib_logging.basicConfig(
        level=log_level.value,
        format=LOG_FORMAT,
        stream=sys.stderr,
    )
    stdlib_logging.getLogger(LOGGER_NAME).setLevel(log_level.value)


def get_logger(name: str | None = None) -> stdlib_logging.Logger:
    return stdlib_logging.getLogger(name or LOGGER_NAME)


def _resolve_log_level(level: LogLevel | str | None) -> LogLevel:
    if isinstance(level, LogLevel):
        return level
    if isinstance(level, str):
        return parse_log_level(level)
    return get_log_level()
