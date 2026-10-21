"""환경 설정. compose는 env_file로 주입하고, 로컬은 infra/.env.local → infra/.env 순으로 읽는다."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 로컬은 <repo>/services/debate-mcp/debate_mcp/config.py. 컨테이너에는 저장소 루트가 없다.
_parents = Path(__file__).resolve().parents
REPO_ROOT = _parents[3] if len(_parents) > 3 else _parents[-1]

TIMEOUT_SECONDS = 10.0


def _load_env_files() -> None:
    # 이미 있는 환경변수(compose env_file)는 덮어쓰지 않는다.
    # .env.local이 먼저라 같은 키는 로컬 값이 이긴다.
    for name in (".env.local", ".env"):
        path = REPO_ROOT / "infra" / name
        if path.is_file():
            load_dotenv(path, override=False)


@dataclass(frozen=True)
class Settings:
    api_internal_url: str
    internal_token: str


def load_settings() -> Settings:
    _load_env_files()
    return Settings(
        api_internal_url=os.environ.get("API_INTERNAL_URL", "http://api:8001").rstrip("/"),
        internal_token=os.environ.get("INTERNAL_TOKEN", "change-me-internal"),
    )
