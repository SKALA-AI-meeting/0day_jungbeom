"""api 내부 앱(`/internal/*`, X-Internal-Token) 클라이언트. 워커는 MCP 없이 내부 REST만 쓴다.

4xx·5xx는 ApiError, 연결 실패·타임아웃은 httpx.TransportError로 올린다.
재시도는 여기서 하지 않고 큐 소비자(attempt+1 재발행)가 맡는다.
"""

import uuid
from typing import Any

import httpx

TIMEOUT_SECONDS = 10.0
# 리포트에 필요한 메시지는 세션 전체다. 한 페이지 500개씩 offset으로 끝까지 읽는다.
MESSAGE_PAGE = 500


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code


def api_down(exc: BaseException) -> bool:
    """api가 내려가 있거나 일시 장애인지. dlq 소비자가 ack하지 않고 기다릴지 정한다."""
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, ApiError) and exc.status >= 500


class InternalApi:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-Internal-Token": token},
            timeout=TIMEOUT_SECONDS,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._client.request(method, path, **kwargs)
        if response.status_code >= 400:
            try:
                error = response.json()["error"]
                code, message = error.get("code", ""), error.get("message", "")
            except (ValueError, KeyError, TypeError, AttributeError):
                code, message = "", response.text[:200]
            raise ApiError(response.status_code, code, message)
        return response.json()

    def _session(self, session_id: str | uuid.UUID, suffix: str = "") -> str:
        return f"/internal/sessions/{session_id}{suffix}"

    async def collect(self, session_id: str) -> dict[str, Any]:
        """collect 노드의 입력 전부(docs/worker-infra/design.md 2단계)."""
        get = self._call
        return {
            "session": await get("GET", self._session(session_id)),
            "observations": await get("GET", self._session(session_id, "/observations")),
            "assistant_calls": await get("GET", self._session(session_id, "/assistant_calls")),
            "assistant_reuse": await get("GET", self._session(session_id, "/assistant_reuse")),
            "messages": await self.all_messages(session_id),
            "document_revisions": await get(
                "GET", self._session(session_id, "/document_revisions")
            ),
            "doc_views": await get("GET", self._session(session_id, "/doc_views")),
        }

    async def all_messages(self, session_id: str) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        while True:
            page = await self._call(
                "GET",
                self._session(session_id, "/messages"),
                params={"limit": MESSAGE_PAGE, "offset": len(messages)},
            )
            messages.extend(page)
            if len(page) < MESSAGE_PAGE:
                return messages

    async def save_draft(
        self, session_id: str, content: dict[str, Any], usage: dict[str, Any] | None
    ) -> dict[str, Any]:
        # usage는 reports.usage로 저장된다(재전달은 최초 값 유지). 해시는 content에만
        body = {"content": content, "usage": usage or {}}
        return await self._call("POST", self._session(session_id, "/report/draft"), json=body)

    async def save_final(self, session_id: str, content: dict[str, Any]) -> dict[str, Any]:
        return await self._call(
            "POST", self._session(session_id, "/report/final"), json={"content": content}
        )

    async def report_failed(self, session_id: str, error: str) -> dict[str, Any]:
        return await self._call(
            "POST", self._session(session_id, "/report_failed"), json={"error": error}
        )
