"""assessment-mcp 서버 골격: FastMCP(Streamable HTTP `/mcp`)와 `/health`(G-F).

도구 6개(record_observation·get_rubric·get_session_record·get_transcript_span·get_contributions·
save_evaluation, 모두 `async def`)와 X-Assessment-Token 검사(없거나 다르면 `forbidden`)는 mcp 트랙이
`tools.py`에 더한다(contracts.md "assessment-mcp").
"""

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

PORT = 9103

mcp = FastMCP("assessment-mcp")


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def create_app():
    return mcp.http_app(path="/mcp", transport="streamable-http")
