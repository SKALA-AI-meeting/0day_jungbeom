"""공개·내부 앱이 한 프로세스에서 함께 쓰는 객체(hub, Lock, runner, 큐, DB).

run.py가 한 번 만든다.
"""

import os
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.requests import HTTPConnection

from app.agent.runner import AgentRunner, AssistantRunner, FakeAgentRunner, FakeAssistantRunner
from app.config import Settings, get_settings
from app.db import make_engine, make_session_factory
from app.hub import Hub
from app.queue import Publisher, RabbitPublisher
from app.services.locks import SessionLocks
from app.services.reuse import record_reuse
from app.services.session import SessionService


@dataclass
class AppContext:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    hub: Hub
    locks: SessionLocks
    publisher: Publisher
    runner: AgentRunner
    # 어시스턴트 훅. 기본은 고정 문장, agent-assistant 트랙이 그래프 구현으로 바꾼다
    assistant: AssistantRunner = field(default_factory=FakeAssistantRunner)

    def session_service(self, db: AsyncSession) -> SessionService:
        return SessionService(
            db,
            hub=self.hub,
            runner=self.runner,
            publisher=self.publisher,
            locks=self.locks,
            reuse_estimator=record_reuse,
        )


def build_context(settings: Settings | None = None) -> AppContext:
    """runner는 환경변수 AGENT_RUNNER로 고른다.

    fake(기본): FakeAgentRunner(내부 저장을 직접 호출). session: LangGraph 세션 그래프(gpt-4o-mini,
    business-mcp·rag-mcp 경유, PostgresSaver).
    """
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    hub = Hub()
    kind = os.environ.get("AGENT_RUNNER", "fake")
    if kind == "session":
        runner = _session_runner(settings, factory, hub)
    elif kind == "fake":
        runner = _fake_runner(factory, hub)
    else:
        raise ValueError(f"AGENT_RUNNER must be session or fake: {kind}")

    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=factory,
        hub=hub,
        locks=SessionLocks(),
        publisher=RabbitPublisher(settings.rabbitmq_url),
        runner=runner,
    )


def _fake_runner(factory: async_sessionmaker[AsyncSession], hub: Hub) -> AgentRunner:
    from app.services.messages import save_internal_message

    async def post_message(**kwargs):
        async with factory() as db:
            message, _ = await save_internal_message(db, hub, **kwargs)
            return message

    return FakeAgentRunner(post_message, hub.broadcast)


def _session_runner(
    settings: Settings, factory: async_sessionmaker[AsyncSession], hub: Hub
) -> AgentRunner:
    from app.agent.llm import OpenAILLM
    from app.agent.mcp_client import BUSINESS, RAG
    from app.agent.session.runner import SessionAgentRunner
    from app.agent.session.store import DbAgentStore

    return SessionAgentRunner(
        llm=OpenAILLM(settings.openai_api_key, settings.openai_model),
        mcp_urls={BUSINESS: settings.business_mcp_url, RAG: settings.rag_mcp_url},
        store=DbAgentStore(factory),
        database_url=settings.database_url,
        broadcast=hub.broadcast,
    )


def get_context(conn: HTTPConnection) -> AppContext:
    """FastAPI 의존성. HTTP 요청과 WebSocket 모두에서 쓴다."""
    return conn.app.state.ctx
