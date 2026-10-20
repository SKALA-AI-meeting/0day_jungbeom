"""business-mcp 서버 골격: FastMCP(Streamable HTTP `/mcp`)와 `/health`.

세션·메시지·보드·문서·관찰 도구는 business-mcp 트랙이 추가한다.
"""

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

PORT = 9101

mcp = FastMCP("business-mcp")


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def create_app():
    return mcp.http_app(path="/mcp", transport="streamable-http")
