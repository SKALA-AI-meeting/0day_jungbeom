"""환경 설정. compose는 env_file로 주입하고, 로컬은 infra/.env.local → infra/.env 순으로 읽는다."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 로컬은 <repo>/services/report-worker/report_worker/config.py. 컨테이너에는 저장소 루트가 없다.
_parents = Path(__file__).resolve().parents
REPO_ROOT = _parents[3] if len(_parents) > 3 else _parents[-1]


def _load_env_files() -> None:
    # 이미 있는 환경변수(compose env_file)는 덮어쓰지 않는다. .env.local의 같은 키가 이긴다.
    for name in (".env.local", ".env"):
        path = REPO_ROOT / "infra" / name
        if path.is_file():
            load_dotenv(path, override=False)


@dataclass(frozen=True)
class Settings:
    api_internal_url: str
    internal_token: str
    database_url: str
    rabbitmq_url: str
    openai_model: str


def checkpoint_url(database_url: str) -> str:
    """api는 SQLAlchemy(asyncpg) 형식을 쓴다. PostgresSaver(psycopg)는 드라이버 표기 없이 받는다."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


MODEL = "gpt-4o-mini"  # 고정 제약(AGENTS.md). 대체 모델 없음


def load_settings() -> Settings:
    _load_env_files()
    model = os.environ.get("OPENAI_MODEL", MODEL)
    if model != MODEL:
        raise RuntimeError(f"OPENAI_MODEL must be {MODEL}, got {model!r}")
    return Settings(
        api_internal_url=os.environ.get("API_INTERNAL_URL", "http://api:8001").rstrip("/"),
        internal_token=os.environ.get("INTERNAL_TOKEN", "change-me-internal"),
        database_url=checkpoint_url(os.environ.get("DATABASE_URL", "")),
        rabbitmq_url=os.environ.get("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/"),
        openai_model=model,
    )
