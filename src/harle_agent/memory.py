from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
PERSONAL_HISTORY_PATH = DATA_DIR / "juan_personal_history.md"
CONVERSATIONS_DIR = DATA_DIR / "conversations"
CONVERSATION_CONTEXT_CHAR_LIMIT = 4000
