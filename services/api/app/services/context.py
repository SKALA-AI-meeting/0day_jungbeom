"""공개·내부 앱이 한 프로세스에서 함께 쓰는 객체(hub, 메일박스, runner, 큐, DB, 시계).

run.py가 build_context()로 한 번 만들고 두 앱의 app.state.ctx에 넣는다. 테스트는 같은 생성자에
가짜 시계·가짜 runner·메모리 publisher를 넣는다.
"""

import asyncio
import importlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.requests import HTTPConnection

from app import queue
from app.agent import intent as intent_module
from app.agent.runner import (
    AgentRunner,
    AssistantRunner,
    FakeAgentRunner,
    FakeAssistantRunner,
)
from app.config import Settings, get_settings
from app.db import make_engine, make_session_factory
from app.hub import Hub
from app.mailbox import Mailboxes
from app.models import Session
from app.services.clock import Clock, MonotonicClock, SystemClock
from app.services.common import Effects

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    clock: Clock
    publisher: queue.Publisher
    runner: AgentRunner | None = None
    assistant: AssistantRunner = field(default_factory=FakeAssistantRunner)
    classify: Callable[..., Awaitable[tuple[dict, bool]]] | None = None
    hub: Hub = None  # type: ignore[assignment]
    mailboxes: Mailboxes = None  # type: ignore[assignment]
    generations: dict[uuid.UUID, int] = field(default_factory=dict)
    spawned: set[asyncio.Task] = field(default_factory=set)
    record_frames: bool = False
    engine: AsyncEngine | None = None

    def __post_init__(self) -> None:
        if self.hub is None:
            self.hub = Hub(self.clock.now, record=self.record_frames)
        if self.mailboxes is None:
            self.mailboxes = Mailboxes(self)
        if self.classify is None:

            async def classify(message: str, **kwargs: Any):
                return await intent_module.classify(None, message, **kwargs)

            self.classify = classify
        if self.runner is None:
            self.runner = FakeAgentRunner(self.post_message, self.mailboxes.ports)

    def spawn(self, coro: Awaitable[Any]) -> None:
        task = asyncio.ensure_future(coro)
        self.spawned.add(task)
        task.add_done_callback(self.spawned.discard)

    async def drain_spawned(self) -> None:
        while self.spawned:
            await asyncio.gather(*list(self.spawned), return_exceptions=True)

    async def apply(self, session_id: uuid.UUID, fx: Effects) -> None:
        """커밋 뒤 효과: generation 캐시 → 큐 발행 → WS 프레임(순서대로) → 자극 enqueue."""
        if fx.generation is not None:
            self.generations[session_id] = fx.generation
        for routing_key in fx.publish:
            async with self.session_factory() as db:
                session = await db.get(Session, session_id)
                await queue.publish_report(
                    db, self.publisher, session, routing_key, self.clock.now()
                )
        await self.hub.send_many(session_id, fx.events)
        for stimulus, run_id in fx.stimuli:
            self.mailboxes.put(session_id, stimulus, run_id)

    async def post_message(self, *, session_id: uuid.UUID, **body: Any) -> dict[str, Any]:
        """내부 POST /messages와 같은 저장(개발용 FakeAgentRunner의 post_message)."""
        from app.services import debate
        from app.services.common import load_session, serialize_message

        fx = Effects()
        async with self.session_factory() as db:
            session = await load_session(db, session_id, lock=True)
            message = await debate.post_internal_message(db, session, body, self.clock, fx)
            await db.commit()
            payload = serialize_message(session, message)
        await self.apply(session_id, fx)
        return payload


def get_context(conn: HTTPConnection) -> AppContext:
    """FastAPI 의존성. HTTP 요청과 WebSocket 모두에서 쓴다."""
    return conn.app.state.ctx


def _load_factory(path: str) -> Callable[[AppContext], Any]:
    module, _, name = path.partition(":")
    return getattr(importlib.import_module(module), name)


def build_context(settings: Settings | None = None) -> AppContext:
    """AGENT_RUNNER=session(기본)이면 agent 트랙의 토론 그래프·어시스턴트·의도 분류 LLM을 붙인다.

    fake는 FakeAgentRunner(단위 테스트 주입용), `모듈:함수`는 그 함수(ctx)가 AgentRunner를 만든다.
    LLM_FAKE=1이어도 runner는 그대로이고 LLM 래퍼(make_llm)가 고정 응답을 돌려준다.
    """
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    ctx = AppContext(
        settings=settings,
        session_factory=factory,
        clock=MonotonicClock(SystemClock()),
        publisher=queue.RabbitPublisher(settings.rabbitmq_url),
        engine=engine,
    )
    if settings.agent_runner == "session":
        # agent 트랙 소유 모듈(app/agent/factory.py)이라 실제 실행 때만 가져온다
        from app.agent.factory import build_assistant_runner, build_debate_runner, db_scenario
        from app.agent.llm import make_llm

        scenario = db_scenario(factory)
        ctx.runner = build_debate_runner(settings, scenario, ctx.mailboxes.ports)
        ctx.assistant = build_assistant_runner(settings, scenario)
        intent_llm = make_llm("intent")

        async def classify(message: str, **kwargs: Any):
            return await intent_module.classify(intent_llm, message, **kwargs)

        ctx.classify = classify
    elif settings.agent_runner not in ("", "fake"):
        ctx.runner = _load_factory(settings.agent_runner)(ctx)
    return ctx
