import base64
import json
from pathlib import Path

from harle_utils import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
PERSONAL_HISTORY_PATH = DATA_DIR / "juan_personal_history.md"
CONVERSATIONS_DIR = DATA_DIR / "conversations"


class AgentSettings(Settings):
    EXPENSES_SPREADSHEET_ID: str
    GOOGLE_SERVICE_ACCOUNT_JSON_BASE64: str
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-2.5-flash"
    MAX_RETRIES: int = 3
    MAX_LOOPS: int = 5
    MAX_CONVERSATION_TOKENS: int = 1000

    @property
    def GOOGLE_SERVICE_ACCOUNT(self) -> str:  # pylint: disable=invalid-name
        decoded = base64.b64decode(self.GOOGLE_SERVICE_ACCOUNT_JSON_BASE64).decode(
            "utf-8",
        )
        return json.loads(decoded)


AGENT_SETTINGS: AgentSettings | None = None


def get_agent_settings() -> AgentSettings:
    global AGENT_SETTINGS  # pylint: disable=global-statement
    if AGENT_SETTINGS is None:
        AGENT_SETTINGS = AgentSettings()
    return AGENT_SETTINGS
