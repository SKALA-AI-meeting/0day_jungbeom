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

    session(기본): LangGraph 세션 그래프(gpt-4o-mini, business-mcp·rag-mcp 경유, PostgresSaver).
    fake: FakeAgentRunner(내부 저장을 직접 호출, LLM 없이 개발·테스트용).
    assistant는 ASSISTANT_RUNNER로 고른다. fake(기본): 고정 문장. graph: 어시스턴트 그래프
    (rag-mcp 경유, 같은 PostgresSaver 저장소의 assistant thread).
    """
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    hub = Hub()
    kind = os.environ.get("AGENT_RUNNER", "session")
    if kind == "session":
        runner = _session_runner(settings, factory, hub)
    elif kind == "fake":
        runner = _fake_runner(factory, hub)
    else:
        raise ValueError(f"AGENT_RUNNER must be session or fake: {kind}")
    assistant_kind = os.environ.get("ASSISTANT_RUNNER", "fake")
    if assistant_kind == "graph":
        assistant = _assistant_runner(settings, factory, hub)
    elif assistant_kind == "fake":
        assistant = FakeAssistantRunner()
    else:
        raise ValueError(f"ASSISTANT_RUNNER must be graph or fake: {assistant_kind}")

    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=factory,
        hub=hub,
        locks=SessionLocks(),
        publisher=RabbitPublisher(settings.rabbitmq_url),
        runner=runner,
        assistant=assistant,
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
    from app.agent.llm import make_llm
    from app.agent.mcp_client import BUSINESS, RAG
    from app.agent.session.runner import SessionAgentRunner
    from app.agent.session.store import DbAgentStore

    # 역할별 모델·키는 llm/roles.py 규칙 하나로(MODEL_<역할>, 비면 OPENAI_MODEL)
    roles = {role: make_llm(role) for role in ("colleague", "manager", "observe")}
    return SessionAgentRunner(
        llm=roles["colleague"],
        roles=roles,
        mcp_urls={BUSINESS: settings.business_mcp_url, RAG: settings.rag_mcp_url},
        store=DbAgentStore(factory),
        database_url=settings.database_url,
        broadcast=hub.broadcast,
    )


def _assistant_runner(
    settings: Settings, factory: async_sessionmaker[AsyncSession], hub: Hub
) -> AssistantRunner:
    from app.agent.assistant import AssistantGraphRunner, db_scenario, mcp_rag
    from app.agent.llm import OpenAILLM

    return AssistantGraphRunner(
        llm=OpenAILLM(settings.openai_api_key, settings.openai_model),
        rag=mcp_rag(settings.rag_mcp_url),
        scenario=db_scenario(factory),
        database_url=settings.database_url,
        broadcast=hub.broadcast,
    )


def get_context(conn: HTTPConnection) -> AppContext:
    """FastAPI 의존성. HTTP 요청과 WebSocket 모두에서 쓴다."""
    return conn.app.state.ctx
