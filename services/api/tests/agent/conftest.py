"""에이전트 연결 테스트 픽스처.

- business-mcp·rag-mcp를 각 서비스 가상환경의 하위 프로세스로 띄운다
  (Streamable HTTP, 실제 서버 코드).
  rag는 결정적 임베딩, DB는 이 실행의 임시 DB(doc_chunks 포함)를 쓴다.
- api 공개·내부 앱을 이 테스트 루프 안의 uvicorn으로 띄운다. MCP 서버는 내부 앱을, 테스트는
  공개 앱의 WebSocket을 부른다. 앱은 테스트마다 새 AppContext로 바꿔 끼운다.
- runner는 SessionAgentRunner + FakeLLM(테스트가 script를 채운다). 체크포인터는 임시 DB.
- live가 아닌 실행에서는 LangSmith 트레이싱을 끈다(테스트 데이터를 보내지 않게).
"""

import asyncio
import os
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
import uvicorn
from app.agent.llm import BaseLLM, FakeLLM
from app.agent.mcp_client import BUSINESS, RAG, McpClient
from app.agent.session.runner import SessionAgentRunner
from app.agent.session.store import DbAgentStore
from app.config import REPO_ROOT, get_settings
from app.db import make_session_factory
from app.hub import Hub
from app.main import create_internal_app, create_public_app
from app.services.context import AppContext
from app.services.locks import SessionLocks

from tests.conftest import FakePublisher

SERVICES = REPO_ROOT / "services"
LAUNCHER = Path(__file__).with_name("mcp_server.py")
STARTUP_SECONDS = 180  # 새 worktree에서는 uv가 서비스 가상환경을 처음 만든다


@pytest.fixture(scope="session", autouse=True)
def tracing_off(request):
    if "live" not in (request.config.option.markexpr or "").replace("not live", ""):
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        os.environ["LANGSMITH_TRACING"] = "false"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Swappable:
    """테스트마다 대상 ASGI 앱을 바꿔 끼우는 래퍼(uvicorn 서버는 세션 동안 하나)."""

    def __init__(self) -> None:
        self.app = None

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        await self.app(scope, receive, send)


@dataclass
class Servers:
    public: Swappable
    internal: Swappable
    public_port: int
    mcp_urls: dict[str, str]


async def _wait_health(url: str, process: subprocess.Popen) -> None:
    async with httpx.AsyncClient() as client:
        for _ in range(STARTUP_SECONDS * 4):
            if process.poll() is not None:
                raise RuntimeError(f"{url} exited with {process.returncode}")
            try:
                if (await client.get(url)).status_code == 200:
                    return
            except httpx.TransportError:
                pass
            await asyncio.sleep(0.25)
    raise TimeoutError(url)


@pytest.fixture(scope="session")
async def servers(database_url):
    public, internal = Swappable(), Swappable()
    public_port, internal_port = free_port(), free_port()
    uvicorn_servers = [
        uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        for app, port in ((public, public_port), (internal, internal_port))
    ]
    tasks = [asyncio.create_task(s.serve()) for s in uvicorn_servers]

    env = {
        **os.environ,
        "API_INTERNAL_URL": f"http://127.0.0.1:{internal_port}",
        "INTERNAL_TOKEN": get_settings().internal_token,
        "DATABASE_URL": database_url,
        "SCENARIOS_DIR": str(REPO_ROOT / "scenarios"),
        "EMBEDDING_MODEL": "test-bigram",
    }
    env.pop("VIRTUAL_ENV", None)  # api 가상환경이 아니라 각 서비스의 것을 쓰게
    processes, urls = [], {}
    for name, folder in ((BUSINESS, "business-mcp"), (RAG, "rag-mcp")):
        port = free_port()
        cwd = SERVICES / folder
        process = subprocess.Popen(
            ["uv", "run", "--quiet", "python", str(LAUNCHER), name, str(port)],
            cwd=cwd,
            env={**env, "PYTHONPATH": str(cwd)},
            stdout=sys.stderr,
            stderr=sys.stderr,
        )
        processes.append(process)
        urls[name] = f"http://127.0.0.1:{port}/mcp"
    try:
        for url, process in zip(urls.values(), processes, strict=True):
            await _wait_health(url.removesuffix("/mcp") + "/health", process)
        yield Servers(public, internal, public_port, urls)
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            process.wait(timeout=10)
        for server in uvicorn_servers:
            server.should_exit = True
        await asyncio.gather(*tasks, return_exceptions=True)


@dataclass
class Stack:
    ctx: AppContext
    runner: SessionAgentRunner
    llm: FakeLLM
    hub: Hub
    servers: Servers

    def use_llm(self, llm: BaseLLM) -> None:
        self.runner.llm = llm


@pytest.fixture
async def stack(servers, db, engine, database_url):
    """이 테스트의 AppContext(SessionAgentRunner)를 서버에 끼우고 rag 색인을 만든다."""
    factory = make_session_factory(engine)
    hub = Hub()
    llm = FakeLLM()
    runner = SessionAgentRunner(
        llm=llm,
        mcp_urls=servers.mcp_urls,
        store=DbAgentStore(factory),
        database_url=database_url,
        broadcast=hub.broadcast,
    )
    ctx = AppContext(
        settings=get_settings(),
        engine=engine,
        session_factory=factory,
        hub=hub,
        locks=SessionLocks(),
        publisher=FakePublisher(),
        runner=runner,
    )
    servers.public.app = create_public_app(ctx)
    servers.internal.app = create_internal_app(ctx)
    async with McpClient({RAG: servers.mcp_urls[RAG]}, "-") as rag:
        indexed = await rag.scope(frozenset({"reindex_documents"})).call("reindex_documents")
    assert indexed["ok"], indexed
    # 체크포인터 테이블·인덱스(CREATE INDEX CONCURRENTLY)를 열린 트랜잭션이 없을 때 미리 만든다
    await runner.graph()
    yield Stack(ctx, runner, llm, hub, servers)
    await runner.aclose()
