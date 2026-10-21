import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from assessment_mcp import client, server, tools  # noqa: F401  (도구 등록)
from assessment_mcp.config import Settings
from fastmcp import Client

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = REPO_ROOT / "tests" / "fixtures" / "contracts"
TOKEN = "test-assessment-token"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# 공용 계약 형태(tests/contract_shape.py). 도구 출력은 MCP_TOOLS 형태로 검사한다
shape = _load_module("contract_shape", REPO_ROOT / "tests" / "contract_shape.py")


def fixture(name: str):
    """tests/fixtures/contracts/<name>.json"""
    return json.loads((CONTRACTS / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def api():
    """api 내부 앱 mock. `api.handler`에 요청 → 응답 함수를, `api.requests`에 받은 요청을 쌓는다."""

    class Api:
        requests: list[httpx.Request]
        handler = None

    state = Api()
    state.requests = []

    def dispatch(request: httpx.Request) -> httpx.Response:
        state.requests.append(request)
        return state.handler(request)

    client.configure(
        transport=httpx.MockTransport(dispatch),
        settings=Settings(
            api_internal_url="http://api.test:8001",
            internal_token="test-token",
            assessment_token=TOKEN,
        ),
    )
    yield state
    client.configure()


@pytest.fixture
def presented(monkeypatch):
    """메모리 내 호출에는 HTTP 헤더가 없으므로 제시 토큰을 바꿔 끼운다. 기본은 올바른 토큰."""
    holder = {"token": TOKEN}
    monkeypatch.setattr(server, "request_token", lambda: holder["token"])
    return holder


@pytest.fixture
async def mcp_client(presented):
    async with Client(server.mcp) as c:
        yield c


async def call(mcp_client, name, args):
    """도구를 호출하고 `{ok, ...}` 본문을 돌려준다."""
    result = await mcp_client.call_tool(name, args, raise_on_error=False)
    return result.structured_content
