import httpx
import pytest
from debate_mcp import client, tools  # noqa: F401  (도구 등록)
from debate_mcp.config import Settings
from debate_mcp.server import mcp
from fastmcp import Client


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
        settings=Settings(api_internal_url="http://api.test:8001", internal_token="test-token"),
    )
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
