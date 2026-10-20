"""business-mcp 서버: FastMCP(Streamable HTTP `/mcp`)와 `/health`. 도구는 `tools.py`."""

from fastmcp import FastMCP
from fastmcp.exceptions import ValidationError
from fastmcp.server.middleware import Middleware
from fastmcp.tools import ToolResult
from starlette.requests import Request
from starlette.responses import JSONResponse

PORT = 9101


class InvalidInputAsResult(Middleware):
    """도구 인자 검증 실패(Pydantic)를 프로토콜 오류 대신 invalid_input 결과로 돌려준다."""

    async def on_call_tool(self, context, call_next):
        try:
            return await call_next(context)
        except ValidationError as exc:
            error = {"code": "invalid_input", "message": str(exc), "retryable": False}
            return ToolResult(structured_content={"ok": False, "error": error})


mcp = FastMCP("business-mcp", middleware=[InvalidInputAsResult()])


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def create_app():
    from business_mcp import tools  # noqa: F401  (도구 등록)

    return mcp.http_app(path="/mcp", transport="streamable-http")
