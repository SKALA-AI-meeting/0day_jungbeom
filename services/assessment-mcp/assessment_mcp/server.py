"""assessment-mcp 서버: FastMCP(Streamable HTTP `/mcp`)와 `/health`. 도구 6개는 `tools.py`.

모든 도구 호출에 `X-Assessment-Token`(env `ASSESSMENT_MCP_TOKEN`)이 있어야 한다. 없거나 다르면
api를 부르지 않고 `forbidden`을 돌려준다. 서버 토큰이 비어 있으면 모든 호출을 거부한다(닫힌 기본값).
페르소나 클라이언트에는 이 토큰을 주지 않는다(docs/contracts/mcp.md "도구 허용 목록").
"""

import hmac

from fastmcp import FastMCP
from fastmcp.exceptions import ValidationError
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import Middleware
from fastmcp.tools import ToolResult
from starlette.requests import Request
from starlette.responses import JSONResponse

from assessment_mcp import client

PORT = 9103
TOKEN_HEADER = "x-assessment-token"


def _error_result(code: str, message: str) -> ToolResult:
    error = {"code": code, "message": message, "retryable": False}
    return ToolResult(structured_content={"ok": False, "error": error})


def request_token() -> str | None:
    """현재 HTTP 요청의 X-Assessment-Token. HTTP 밖(메모리 내 호출)이면 None."""
    return get_http_headers(include_all=True).get(TOKEN_HEADER)


def token_ok(presented: str | None) -> bool:
    expected = client.current_settings().assessment_token
    if not expected or not presented:
        return False
    return hmac.compare_digest(presented.encode(), expected.encode())


class RequireAssessmentToken(Middleware):
    """도구 호출마다 토큰을 검사한다. 실패하면 api 호출 없이 forbidden 결과."""

    async def on_call_tool(self, context, call_next):
        if not token_ok(request_token()):
            return _error_result("forbidden", "missing or invalid X-Assessment-Token")
        return await call_next(context)


class InvalidInputAsResult(Middleware):
    """도구 인자 검증 실패(Pydantic)를 프로토콜 오류 대신 invalid_input 결과로 돌려준다."""

    async def on_call_tool(self, context, call_next):
        try:
            return await call_next(context)
        except ValidationError as exc:
            return _error_result("invalid_input", str(exc))


# 토큰 검사가 먼저다: 토큰 없는 호출은 입력이 틀려도 forbidden
mcp = FastMCP("assessment-mcp", middleware=[RequireAssessmentToken(), InvalidInputAsResult()])


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def create_app():
    from assessment_mcp import tools  # noqa: F401  (도구 등록)

    return mcp.http_app(path="/mcp", transport="streamable-http")
