import logging
import os
import sys
from enum import Enum

from dotenv import load_dotenv
from pydantic import TypeAdapter, ValidationError

LOGGER_NAME = "harle"
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


class LogLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    DEBUG = "DEBUG"


LogLevelAdapter = TypeAdapter(LogLevel)


def configure_logging(level: LogLevel) -> logging.Logger:
    logging.basicConfig(
        level=level.value,
        format=LOG_FORMAT,
        stream=sys.stderr,
    )
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level.value)
    return logger


load_dotenv()
LOG_LEVEL = os.getenv("HARLE_LOG_LEVEL")

try:
    log_level = LogLevelAdapter.validate_python(LOG_LEVEL or LogLevel.WARNING)
    log = configure_logging(log_level)
    log.info(f"Environment log level set to: {log_level.value}")

except ValidationError:
    log = configure_logging(LogLevel.WARNING)
    log.warning(
        f"Invalid environment log level: '{LOG_LEVEL}', using default: {LogLevel.WARNING}",
    )
