"""환경 설정. compose는 env_file로 주입하고, 로컬은 infra/.env.local → infra/.env 순으로 읽는다."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 로컬은 <repo>/services/rag-mcp/rag_mcp/config.py. 컨테이너에는 저장소 루트가 없다.
_parents = Path(__file__).resolve().parents
REPO_ROOT = _parents[3] if len(_parents) > 3 else _parents[-1]

TIMEOUT_SECONDS = 10.0
DEFAULT_SCENARIOS_DIR = "/scenarios"


def _load_env_files() -> None:
    # 이미 있는 환경변수(compose env_file)는 덮어쓰지 않는다.
    # .env.local이 먼저라 같은 키는 로컬 값이 이긴다.
    for name in (".env.local", ".env"):
        path = REPO_ROOT / "infra" / name
        if path.is_file():
            load_dotenv(path, override=False)


def _scenarios_dir(value: str) -> Path:
    """api config와 같은 규칙: 기본값(/scenarios)이 없을 때만 저장소 scenarios/로 대체.

    사용자가 다른 경로를 지정했는데 없으면 설정 오류로 본다.
    """
    path = Path(value)
    if path.is_dir():
        return path
    if value == DEFAULT_SCENARIOS_DIR:
        return REPO_ROOT / "scenarios"
    raise ValueError(f"SCENARIOS_DIR does not exist: {value}")


@dataclass(frozen=True)
class Settings:
    api_internal_url: str
    internal_token: str
    database_url: str
    scenarios_dir: Path
    embedding_model: str


def load_settings() -> Settings:
    _load_env_files()
    env = os.environ
    # api는 SQLAlchemy 형식(postgresql+asyncpg://)을 쓴다. asyncpg는 postgresql://만 받는다.
    database_url = env.get(
        "DATABASE_URL", "postgresql+asyncpg://dayzero:dayzero@localhost:5432/dayzero"
    ).replace("postgresql+asyncpg://", "postgresql://")
    return Settings(
        api_internal_url=env.get("API_INTERNAL_URL", "http://api:8001").rstrip("/"),
        internal_token=env.get("INTERNAL_TOKEN", "change-me-internal"),
        database_url=database_url,
        scenarios_dir=_scenarios_dir(env.get("SCENARIOS_DIR", DEFAULT_SCENARIOS_DIR)),
        embedding_model=env.get("EMBEDDING_MODEL", "BAAI/bge-m3"),
    )
