"""api 단위 테스트 공용 픽스처.

DB는 `make infra-up`으로 띄운 postgres를 쓴다. 실행마다 임시 DB(dayzero_test_<랜덤>)를 만들어
infra/db/schema.sql을 적용하고 끝나면 지운다. 여러 worktree가 같은 postgres를 써도 겹치지 않는다.
LLM·MCP·RabbitMQ는 쓰지 않는다(FakeAgentRunner, FakePublisher).
"""

import uuid
from typing import Any

import asyncpg
import pytest
from app.agent.runner import FakeAgentRunner
from app.config import REPO_ROOT, get_settings
from app.db import make_engine, make_session_factory
from app.hub import Hub
from app.models import Company, Position
from app.queue import PublishNotConfirmed
from app.services.locks import SessionLocks
from app.services.messages import save_internal_message
from app.services.scenario import build_scenario
from app.services.session import SessionService
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

SCHEMA = REPO_ROOT / "infra" / "db" / "schema.sql"
SCENARIOS = REPO_ROOT / "scenarios"


def _asyncpg_dsn(url) -> str:
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


@pytest.fixture(scope="session")
async def database_url():
    base = make_url(get_settings().database_url)
    name = f"dayzero_test_{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(_asyncpg_dsn(base))
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
    factory = make_session_factory(engine)
    async with factory() as session:
        yield session
    async with engine.begin() as conn:
        tables = (
            await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        ).scalars()
        await conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))


class FakeSocket:
    """hub에 붙이는 가짜 WebSocket. 받은 프레임을 순서대로 모은다."""

    def __init__(self) -> None:
        self.frames: list[dict[str, Any]] = []
        self.closed: int | None = None

    async def send_json(self, data: Any) -> None:
        self.frames.append(data)

    async def close(self, code: int = 1000) -> None:
        self.closed = code

    def types(self) -> list[str]:
        return [f["type"] for f in self.frames]


class FakePublisher:
    """fail=True면 브로커 미확인(PublishNotConfirmed)처럼 예외를 낸다."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []
        self.fail = False

    async def publish(self, routing_key: str, body: dict[str, Any]) -> None:
        if self.fail:
            raise PublishNotConfirmed(routing_key)
        self.published.append((routing_key, body))


@pytest.fixture
def hub() -> Hub:
    return Hub()


@pytest.fixture
def publisher() -> FakePublisher:
    return FakePublisher()


@pytest.fixture
def locks() -> SessionLocks:
    return SessionLocks()


@pytest.fixture
def runner(engine, hub) -> FakeAgentRunner:
    factory = make_session_factory(engine)

    async def post_message(**kwargs):
        async with factory() as session:
            message, _ = await save_internal_message(session, hub, **kwargs)
            return message

    return FakeAgentRunner(post_message, hub.broadcast)


@pytest.fixture
def service(db, hub, runner, publisher, locks) -> SessionService:
    return SessionService(db, hub=hub, runner=runner, publisher=publisher, locks=locks)


ALL_FIVE = ["responsibility", "planning", "adaptability", "collaboration", "honesty"]


@pytest.fixture
def make_position(db: AsyncSession):
    async def factory(elements: list[str] = ALL_FIVE, session_minutes: int = 120) -> Position:
        scenario, version = build_scenario(SCENARIOS, elements, session_minutes)
        company = Company(name="테스트 회사")
        db.add(company)
        await db.flush()
        position = Position(
            company_id=company.id,
            name="프로덕트 기획",
            mission_id=scenario["mission_id"],
            elements=elements,
            session_minutes=session_minutes,
            catalog_version=version,
            scenario=scenario,
        )
        db.add(position)
        await db.commit()
        return position

    return factory


@pytest.fixture
def started_session(service, make_position):
    """초대 → 동의 → 시작까지 진행한 세션(in_progress)."""

    async def factory(elements: list[str] = ALL_FIVE, session_minutes: int = 120):
        position = await make_position(elements, session_minutes)
        session, _, _ = await service.create_for_invite(position.id, "지원자A", "a@example.com")
        await service.consent(session.id)
        return await service.start(session.id)

    return factory


async def to_completed(service: SessionService, session_id) -> None:
    """제출(reporting) → 보고 없이 종료(completed). 보고 대기 상한을 기다리지 않고 complete를 바로
    부른다.
    """
    await service.submit(session_id)
    await service.complete(session_id, "submitted")
