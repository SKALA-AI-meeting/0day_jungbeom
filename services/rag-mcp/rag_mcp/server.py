"""rag-mcp 서버: FastMCP(Streamable HTTP `/mcp`)와 `/health`. 도구는 `tools.py`.

임베딩 모델은 시작 시 1회 로드한다. 로드가 끝나야 `/health`가 응답하므로
compose healthcheck가 모델 로드를 기다린다.
"""

import asyncio

from fastmcp import FastMCP
from fastmcp.exceptions import ValidationError
from fastmcp.server.lifespan import lifespan
from fastmcp.server.middleware import Middleware
from fastmcp.tools import ToolResult
from starlette.requests import Request
from starlette.responses import JSONResponse

from rag_mcp import client
from rag_mcp.embedder import get_embedder

PORT = 9102


class InvalidInputAsResult(Middleware):
    """도구 인자 검증 실패(Pydantic)를 프로토콜 오류 대신 invalid_input 결과로 돌려준다."""

    async def on_call_tool(self, context, call_next):
        try:
            return await call_next(context)
        except ValidationError as exc:
            error = {"code": "invalid_input", "message": str(exc), "retryable": False}
            return ToolResult(structured_content={"ok": False, "error": error})


@lifespan
async def load_model(server):
    embedder = get_embedder(client.current_settings().embedding_model)
    if hasattr(embedder, "load"):
        await asyncio.to_thread(embedder.load)
    yield {}


mcp = FastMCP("rag-mcp", middleware=[InvalidInputAsResult()], lifespan=load_model)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def create_app():
    from rag_mcp import tools  # noqa: F401  (도구 등록)

    return mcp.http_app(path="/mcp", transport="streamable-http")
