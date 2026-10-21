"""assessment-mcp 클라이언트(Streamable HTTP, `X-Assessment-Token`).

워커 허용 도구는 `get_rubric`·`get_session_record`·`get_transcript_span`·`get_contributions`·
`save_evaluation`이다(docs/contracts/mcp.md 허용 목록). 평가 LLM에는 도구를 바인딩하지 않고
코드가 직접 부른다.
도구 결과 `{ok:false}`와 연결 실패는 모두 AssessmentError로 올린다. 재시도는 큐 소비자가 맡는다.
호출마다 연결을 열고 닫는다(작업당 호출 수가 적고, anyio 연결을 task 사이에 넘기지 않기 위해서).
"""

import json
from typing import Any, Protocol

ALLOWED_TOOLS = frozenset(
    {
        "get_rubric",
        "get_session_record",
        "get_transcript_span",
        "get_contributions",
        "save_evaluation",
    }
)


class AssessmentError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.retryable = retryable


class Assessment(Protocol):
    async def get_rubric(self, session_id: str) -> dict[str, Any]: ...

    async def get_session_record(self, session_id: str) -> dict[str, Any]: ...

    async def get_contributions(self, session_id: str) -> dict[str, Any]: ...

    async def get_transcript_span(
        self, session_id: str, message_id: str, before: int = 5, after: int = 3
    ) -> dict[str, Any]: ...

    async def save_evaluation(self, body: dict[str, Any]) -> dict[str, Any]: ...


def envelope(result: Any) -> dict[str, Any] | None:
    """도구 결과의 `{ok, data|error}` 봉투. 구조화 결과가 없으면 텍스트 JSON을 읽는다."""
    data = result.structured_content
    if isinstance(data, dict) and "ok" not in data and isinstance(data.get("result"), dict):
        data = data["result"]  # 반환 타입 주석이 dict가 아닌 서버는 {"result": ...}로 감싼다
    if not isinstance(data, dict) or "ok" not in data:
        text = "".join(getattr(c, "text", "") for c in result.content)
        try:
            data = json.loads(text)
        except ValueError:
            return None
    return data if isinstance(data, dict) and "ok" in data else None


class AssessmentClient:
    def __init__(self, url: str, token: str) -> None:
        self.url = url
        self.token = token

    async def call(self, name: str, args: dict[str, Any]) -> Any:
        if name not in ALLOWED_TOOLS:
            raise AssessmentError("forbidden", f"tool {name} not allowed for report-worker")
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client
        from mcp.shared._httpx_utils import create_mcp_http_client

        http = create_mcp_http_client(headers={"X-Assessment-Token": self.token})
        try:
            async with http:
                transport = streamable_http_client(self.url, http_client=http)
                async with Client(transport, mode="legacy") as client:
                    result = await client.call_tool(name, args)
        except AssessmentError:
            raise
        except Exception as exc:
            raise AssessmentError("upstream_unavailable", f"{name}: {exc!r}", True) from exc
        data = envelope(result)
        if data is None:
            text = " ".join(getattr(c, "text", "") for c in result.content)
            raise AssessmentError("internal", text[:200] or f"{name}: unexpected result")
        if not data["ok"]:
            error = data.get("error") or {}
            raise AssessmentError(
                error.get("code", "internal"),
                error.get("message", ""),
                error.get("retryable", False),
            )
        return data.get("data")

    async def get_rubric(self, session_id: str) -> dict[str, Any]:
        return await self.call("get_rubric", {"session_id": session_id})

    async def get_session_record(self, session_id: str) -> dict[str, Any]:
        return await self.call("get_session_record", {"session_id": session_id})

    async def get_contributions(self, session_id: str) -> dict[str, Any]:
        return await self.call("get_contributions", {"session_id": session_id})

    async def get_transcript_span(
        self, session_id: str, message_id: str, before: int = 5, after: int = 3
    ) -> dict[str, Any]:
        args = {
            "session_id": session_id,
            "message_id": message_id,
            "before": before,
            "after": after,
        }
        return await self.call("get_transcript_span", args)

    async def save_evaluation(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self.call("save_evaluation", body)
