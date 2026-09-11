from functools import cache
from pathlib import Path

from harle_utils import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CONVERSATIONS_DIR = DATA_DIR / "conversations"


class AgentSettings(Settings):
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-2.5-flash"
    MAX_RETRIES: int = 3
    MAX_LOOPS: int = 5
    MAX_CONVERSATION_TOKENS: int = 1000


@cache
def get_agent_settings() -> AgentSettings:
    return AgentSettings()
