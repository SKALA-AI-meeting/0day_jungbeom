"""rag-mcp 단위 테스트 공용 픽스처.

- api 내부 앱은 httpx MockTransport로 흉내 낸다(실제 api를 띄우지 않는다).
- 임베딩은 FakeEmbedder(텍스트 해시로 만든 1024차원 결정적 단위 벡터). 같은 텍스트면 코사인 1.
- DB는 `make infra-up`으로 띄운 postgres에 실행마다 임시 DB(rag_test_<랜덤>)를 만들고
  infra/db/schema.sql을 적용한 뒤 끝나면 지운다. 다른 worktree와 겹치지 않는다.
"""

import hashlib
import uuid

import asyncpg
import httpx
import numpy as np
import pytest
from fastmcp import Client
from rag_mcp import client, tools  # noqa: F401  (도구 등록)
from rag_mcp.config import REPO_ROOT, Settings, load_settings
from rag_mcp.embedder import DIM, set_embedder
from rag_mcp.server import mcp

SCHEMA = REPO_ROOT / "infra" / "db" / "schema.sql"
SCENARIOS = REPO_ROOT / "scenarios"


class FakeEmbedder:
    model = "fake-1024"
    dim = DIM

    def embed(self, texts: list[str]) -> np.ndarray:
        rows = []
        for text in texts:
            seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
            v = np.random.default_rng(seed).standard_normal(DIM)
            rows.append(v / np.linalg.norm(v))
        return np.array(rows, dtype=np.float32)


@pytest.fixture(autouse=True)
def fake_embedder():
    set_embedder(FakeEmbedder())
    yield
    set_embedder(None)


@pytest.fixture(scope="session")
async def database_url():
    base = load_settings().database_url
    name = f"rag_test_{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(base)
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()
    url = base.rsplit("/", 1)[0] + f"/{name}"
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(SCHEMA.read_text(encoding="utf-8"))
    finally:
        await conn.close()
    yield url
    admin = await asyncpg.connect(base)
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await admin.close()


@pytest.fixture
async def db(api, database_url):
    """도구가 임시 DB를 쓰게 설정하고 asyncpg 연결을 돌려준다. 끝나면 doc_chunks를 비운다."""
    api.configure(make_settings(database_url))
    conn = await asyncpg.connect(database_url)
    yield conn
    await conn.execute("TRUNCATE doc_chunks")
    await conn.close()


def make_settings(database_url: str = "postgresql://unused/none", scenarios_dir=SCENARIOS):
    return Settings(
        api_internal_url="http://api.test:8001",
        internal_token="test-token",
        database_url=database_url,
        scenarios_dir=scenarios_dir,
        embedding_model="fake-1024",
    )


@pytest.fixture
def api():
    """api 내부 앱 mock(DB 불필요). `api.handler`에 요청 → 응답 함수를, `api.requests`에 받은 요청을
    쌓는다. 설정을 바꿀 때는 `api.configure(settings)`로 mock 전송을 유지한다."""

    class Api:
        requests: list[httpx.Request]
        handler = None

        def configure(self, settings: Settings) -> None:
            client.configure(transport=self.transport, settings=settings)

    state = Api()
    state.requests = []

    def dispatch(request: httpx.Request) -> httpx.Response:
        state.requests.append(request)
        return state.handler(request)

    state.transport = httpx.MockTransport(dispatch)
    state.configure(make_settings())
    yield state
    client.configure()


@pytest.fixture
async def mcp_client():
    async with Client(mcp) as c:
        yield c


async def call(mcp_client, name, args):
    """도구를 호출하고 `{ok, ...}` 본문을 돌려준다."""
    result = await mcp_client.call_tool(name, args, raise_on_error=False)
    return result.structured_content
