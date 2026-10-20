"""rag-mcp 서버 골격: FastMCP(Streamable HTTP `/mcp`)와 `/health`.

회사 문서 검색·조회·색인 도구는 rag-mcp 트랙이 추가한다.
"""

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

PORT = 9102

mcp = FastMCP("rag-mcp")


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def create_app():
    return mcp.http_app(path="/mcp", transport="streamable-http")
