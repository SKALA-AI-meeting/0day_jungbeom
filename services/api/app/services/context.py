"""공개·내부 앱이 한 프로세스에서 함께 쓰는 객체(hub, Lock, runner, 큐, DB).

run.py가 한 번 만든다.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.requests import HTTPConnection

from app.agent.runner import AgentRunner, FakeAgentRunner
from app.config import Settings, get_settings
from app.db import make_engine, make_session_factory
from app.hub import Hub
from app.queue import Publisher, RabbitPublisher
from app.services.locks import SessionLocks
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

    def session_service(self, db: AsyncSession) -> SessionService:
        return SessionService(
            db, hub=self.hub, runner=self.runner, publisher=self.publisher, locks=self.locks
        )


def build_context(settings: Settings | None = None) -> AppContext:
    """기본 runner는 FakeAgentRunner(내부 저장을 직접 호출).

    에이전트 트랙이 실제 runner로 바꾼다.
    """
    from app.services.messages import save_internal_message

    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    hub = Hub()

    async def post_message(**kwargs):
        async with factory() as db:
            message, _ = await save_internal_message(db, hub, **kwargs)
            return message

    return AppContext(
        settings=settings,
        engine=engine,
        session_factory=factory,
        hub=hub,
        locks=SessionLocks(),
        publisher=RabbitPublisher(settings.rabbitmq_url),
        runner=FakeAgentRunner(post_message, hub.broadcast),
    )


def get_context(conn: HTTPConnection) -> AppContext:
    """FastAPI 의존성. HTTP 요청과 WebSocket 모두에서 쓴다."""
    return conn.app.state.ctx
