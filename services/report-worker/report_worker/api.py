"""api 내부 앱(`/internal/*`, X-Internal-Token) 클라이언트.

워커가 내부 REST로 읽는 것: 리포트 머리용 세션 정보, 어시스턴트 호출(ai_usage, 요청·응답 원문
포함), 저장된 평가 재조회(`GET /evaluations`). 쓰는 것: draft·final·report_failed.
평가 입력 묶음·척도·Contributions·근거 맥락·평가 저장은 assessment-mcp로 한다(assessment.py).

4xx·5xx는 ApiError, 연결 실패·타임아웃은 httpx.TransportError로 올린다.
재시도는 여기서 하지 않고 큐 소비자(attempt+1 재발행)가 맡는다.
"""

from typing import Any

import httpx

TIMEOUT_SECONDS = 10.0


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

    @staticmethod
    def _path(session_id: str, suffix: str = "") -> str:
        return f"/internal/sessions/{session_id}{suffix}"

    async def get_session(self, session_id: str) -> dict[str, Any]:
        return await self._call("GET", self._path(session_id))

    async def assistant_calls(self, session_id: str) -> list[dict[str, Any]]:
        return await self._call("GET", self._path(session_id, "/assistant_calls"))

    async def get_evaluation(self, session_id: str, run_id: str) -> dict[str, Any] | None:
        """그 run_id로 저장된 평가(차원 + 요소 요약). 없으면 None(404)."""
        try:
            return await self._call(
                "GET", self._path(session_id, "/evaluations"), params={"run_id": run_id}
            )
        except ApiError as exc:
            if exc.status == 404:
                return None
            raise

    async def save_draft(
        self, session_id: str, content: dict[str, Any], usage: dict[str, Any] | None
    ) -> dict[str, Any]:
        # usage는 reports.usage로 저장된다. 해시는 content에만
        body = {"content": content, "usage": usage or {}}
        return await self._call("POST", self._path(session_id, "/report/draft"), json=body)

    async def save_final(self, session_id: str, content: dict[str, Any]) -> dict[str, Any]:
        return await self._call(
            "POST", self._path(session_id, "/report/final"), json={"content": content}
        )

    async def report_failed(self, session_id: str, error: str) -> dict[str, Any]:
        return await self._call(
            "POST", self._path(session_id, "/report_failed"), json={"error": error}
        )
