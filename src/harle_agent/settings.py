import base64
import json
from collections.abc import Mapping
from functools import cache
from pathlib import Path

from harle_utils import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
PERSONAL_HISTORY_PATH = DATA_DIR / "juan_personal_history.md"
CONVERSATIONS_DIR = DATA_DIR / "conversations"


class AgentSettings(Settings):
    EXPENSES_SPREADSHEET_ID: str
    EXPENSES_NEXT_YEAR_SPREADSHEET_ID: str
    GOOGLE_SERVICE_ACCOUNT_JSON_BASE64: str
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-2.5-flash"
    MAX_RETRIES: int = 3
    MAX_LOOPS: int = 5
    MAX_CONVERSATION_TOKENS: int = 1000

    @property
    # pylint: disable-next=invalid-name
    def GOOGLE_SERVICE_ACCOUNT(self) -> Mapping[str, object]:
        decoded = base64.b64decode(self.GOOGLE_SERVICE_ACCOUNT_JSON_BASE64).decode(
            "utf-8",
        )
        decoded_json = json.loads(decoded)
        if not isinstance(decoded_json, Mapping):
            raise ValueError(
                "GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 must decode to an object.",
            )
        return decoded_json


@cache
def get_agent_settings() -> AgentSettings:
    return AgentSettings()
