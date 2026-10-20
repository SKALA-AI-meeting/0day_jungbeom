"""러너 단위 테스트(mock) 픽스처: api 테스트 스택 위에서 러너를 그대로 돌린다.

- api 공개·내부 앱(uvicorn, 이 루프), business-mcp·rag-mcp 하위 프로세스, 격리 DB, FakeLLM은
  services/api/tests의 픽스처를 그대로 가져온다(최상위 이름 `tests`는 그 패키지다).
- 시계: DB 시각 열을 당겨 세션 분을 앞으로 보내는 script_driver.Driver를 Clock으로 감싼다.
- 리포트 워커: FakePublisher 대신 발행을 받아 워커의 build_draft와 InternalApi(내부 앱에 ASGI로)로
  draft·final을 저장하는 프로세스 안 워커(SimWorker). 리포트 문장은 워커 코드가 만든다.
"""

import asyncio
import sys
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from app.config import get_settings
from app.queue import APPROVE, GENERATE
from tests.agent.conftest import servers, stack, tracing_off  # noqa: F401
from tests.agent.script_driver import Driver

from e2e.client import Target
from tests.conftest import database_url, db, engine  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "report-worker"))
from report_worker.api import InternalApi  # noqa: E402
from report_worker.report import build_draft  # noqa: E402


class DriverClock:
    """세션 분을 DB 시각 이동으로 앞당기는 Clock(run.Clock)."""

    card_wait_seconds = 20

    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    async def now(self) -> float:
        return await self.driver.now()

    async def advance_to(self, minute: float) -> None:
        await self.driver.advance_to(minute)

    async def settle(self) -> None:
        await self.driver.settle()

    async def idle(self) -> None:
        await self.driver.advance_to(await self.driver.now() + 0.25)


class FakeReportLLM:
    model = "gpt-4o-mini"


class SimWorker:
    """report.generate → draft, report.approve → 같은 draft로 final(실제 워커의 소비 규칙 축약)."""

    def __init__(self, internal_app) -> None:
        transport = httpx.ASGITransport(app=internal_app)
        self.api = InternalApi(
            "http://internal", get_settings().internal_token, transport=transport
        )
        self.drafts: dict[str, dict] = {}
        self.published: list[tuple[str, dict]] = []
        self.tasks: set[asyncio.Task] = set()
        self.fail = False

    async def publish(self, routing_key: str, body: dict) -> None:
        self.published.append((routing_key, body))
        task = asyncio.create_task(self.consume(routing_key, body["session_id"]))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def consume(self, routing_key: str, session_id: str) -> None:
        if routing_key == GENERATE:
            content, usage = await build_draft(await self.api.collect(session_id), FakeReportLLM())
            self.drafts[session_id] = content
            await self.api.save_draft(session_id, content, usage)
        elif routing_key == APPROVE:
            await self.api.save_final(session_id, self.drafts[session_id])

    async def close(self) -> None:
        await self.api.close()


@pytest.fixture
async def e2e_stack(stack, database_url):  # noqa: F811
    """(target, clock_factory, worker). 러너는 실 스택과 같은 공개 포트·WS, 내부 앱은 ASGI로."""
    worker = SimWorker(stack.servers.internal)
    stack.ctx.publisher = worker
    stack.ctx.settings = replace(stack.ctx.settings, enable_test_api=True)
    target = Target(
        public_url=f"http://127.0.0.1:{stack.servers.public_port}",
        internal_url="http://internal",
        internal_token=get_settings().internal_token,
        database_url=database_url,
    )

    async def clock_factory(session_id: str, invite_token: str, started_at: datetime):
        session = uuid.UUID(session_id)
        driver = Driver(stack, session, invite_token, 6)
        await driver.settle()  # 킥오프(0분)
        return DriverClock(driver)

    transports = {"internal": httpx.ASGITransport(app=stack.servers.internal)}
    yield target, clock_factory, transports, worker
    await worker.close()
