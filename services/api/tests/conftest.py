"""api 단위 테스트 공용 픽스처(G-F 기반).

DB 테스트는 `make infra-up`으로 띄운 postgres(127.0.0.1:5432)를 쓴다. 실행마다 임시 DB
(dayzero_test_<랜덤>)를 만들어 infra/db/schema.sql을 적용하고 끝나면 지운다. 여러 worktree가 같은
postgres를 써도 겹치지 않는다. 접속 주소는 env `TEST_DATABASE_URL`(기본 localhost),
postgres가 없으면 DB 테스트만 건너뛴다.
LLM·MCP·RabbitMQ는 쓰지 않는다(FakeAgentRunner, FakeSessionPorts).
"""

import os
import uuid

import asyncpg
import pytest
from app.config import REPO_ROOT
from app.db import make_engine, make_session_factory
from sqlalchemy import text
from sqlalchemy.engine import make_url

SCHEMA = REPO_ROOT / "infra" / "db" / "schema.sql"
DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://dayzero:dayzero@localhost:5432/dayzero"


def _asyncpg_dsn(url) -> str:
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


@pytest.fixture(scope="session")
async def database_url():
    base = make_url(os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL))
    name = f"dayzero_test_{uuid.uuid4().hex[:8]}"
    try:
        admin = await asyncpg.connect(_asyncpg_dsn(base), timeout=3)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"postgres 없음(make infra-up): {type(exc).__name__}")
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()
    test_url = base.set(database=name)
    conn = await asyncpg.connect(_asyncpg_dsn(test_url))
    try:
        await conn.execute(SCHEMA.read_text(encoding="utf-8"))
    finally:
        await conn.close()
    yield test_url.render_as_string(hide_password=False)
    admin = await asyncpg.connect(_asyncpg_dsn(base))
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await admin.close()


@pytest.fixture(scope="session")
async def engine(database_url):
    engine = make_engine(database_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db(engine):
    """테스트마다 새 AsyncSession. 끝나면 모든 테이블을 비운다."""
    factory = make_session_factory(engine)
    async with factory() as session:
        yield session
    async with engine.begin() as conn:
        tables = (
            await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        ).scalars()
        await conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))
