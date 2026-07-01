from __future__ import annotations

import os
from pathlib import Path

DEFAULT_MODEL = "gemini-2.5-flash"


def load_dotenv() -> None:
    project_dotenv = Path(__file__).resolve().parents[2] / ".env"
    candidates = [Path.cwd() / ".env", project_dotenv]

    for path in dict.fromkeys(candidates):
        if not path.is_file():
            continue

        for line in path.read_text(encoding="utf-8").splitlines():
            key, value = _parse_env_line(line)
            if key and key not in os.environ:
                os.environ[key] = value


def _parse_env_line(line: str) -> tuple[str | None, str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None, ""

    if stripped.startswith("export "):
        stripped = stripped.removeprefix("export ").strip()

    key, separator, value = stripped.partition("=")
    if not separator:
        return None, ""

    key = key.strip()
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]

    return key, value
