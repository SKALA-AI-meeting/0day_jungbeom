"""완료 기준: 실제 Streamable HTTP 경로에서 X-Assessment-Token 헤더를 검사한다."""

import contextlib

import httpx
import pytest
from assessment_mcp import client
from assessment_mcp.config import Settings
from assessment_mcp.server import create_app
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from tests.conftest import TOKEN, fixture


@pytest.fixture
def api_rubric():
    client.configure(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json=fixture("internal_rubric"))
        ),
        settings=Settings(
            api_internal_url="http://api.test", internal_token="t", assessment_token=TOKEN
        ),
    )
    yield
    client.configure()


@contextlib.asynccontextmanager
async def http_client(headers):
    app = create_app()
    async with app.router.lifespan_context(app):

        def factory(**kwargs):
            import httpx2

            kwargs.pop("verify", None)
            return httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), **kwargs)

        transport = StreamableHttpTransport(
            "http://test/mcp", headers=headers, httpx_client_factory=factory
        )
        async with Client(transport) as c:
            yield c


@pytest.mark.parametrize(
    ("headers", "ok"),
    [({"X-Assessment-Token": TOKEN}, True), ({"X-Assessment-Token": "nope"}, False), ({}, False)],
)
async def test_token_header_checked_over_http(api_rubric, headers, ok):
    async with http_client(headers) as c:
        result = await c.call_tool("get_rubric", {"session_id": "sess-1"}, raise_on_error=False)
    body = result.structured_content
    assert body["ok"] is ok
    if not ok:
        assert body["error"]["code"] == "forbidden"
