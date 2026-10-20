"""api 내부 앱(`/internal/*`) 호출과 응답을 `{ok, data}`·`{ok:false, error}`로 변환한다.

권한·상태 판단은 하지 않는다. api의 4xx를 코드로 옮기고,
5xx·연결 실패는 1회 재시도한 뒤 upstream_unavailable.

| api 응답 | 코드 | 비고 |
|---|---|---|
| 401 | forbidden | 내부 토큰 불일치. 호출 인자로 고칠 수 없음, retryable=false |
| 403 | forbidden | |
| 404 | not_found | |
| 409, 410 | conflict | 410은 만료·취소 |
| 422, 그 외 400 | invalid_input | |
| 423 | not_released | 공개 전 문서 |
| 5xx, 연결 실패, 타임아웃 | upstream_unavailable | 1회 재시도, retryable=true |
| 2xx인데 JSON이 아님 | upstream_unavailable | 재시도 없음, retryable=true |
"""

import logging
from typing import Any

import httpx

from rag_mcp.config import TIMEOUT_SECONDS, Settings, load_settings

logger = logging.getLogger("rag_mcp")

# api 4xx → 계약 오류 코드(표는 모듈 docstring). 표에 없는 4xx는 invalid_input.
STATUS_CODES = {
    401: "forbidden",
    404: "not_found",
    403: "forbidden",
    409: "conflict",
    410: "conflict",
    422: "invalid_input",
    423: "not_released",
}

# 테스트가 api 응답을 mock하려고 바꾸는 값. None이면 실제 네트워크.
_transport: httpx.AsyncBaseTransport | None = None
_settings: Settings | None = None


def configure(
    *, transport: httpx.AsyncBaseTransport | None = None, settings: Settings | None = None
) -> None:
    global _transport, _settings
    _transport = transport
    _settings = settings


def current_settings() -> Settings:
    return _settings or load_settings()


def ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def fail(code: str, message: str, retryable: bool = False) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "retryable": retryable}}


def _error_message(response: httpx.Response) -> str:
    try:
        error = response.json()["error"]
        # api 오류 코드(draft_mismatch 등)는 세부 구분을 위해 메시지에 함께 싣는다.
        return f"{error.get('code', '')}: {error.get('message', '')}".strip(": ")
    except (ValueError, KeyError, TypeError, AttributeError):
        return f"api responded {response.status_code}"


async def call(
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    conf = current_settings()
    params = {k: v for k, v in (params or {}).items() if v is not None}
    last = "api unreachable"
    async with httpx.AsyncClient(
        base_url=conf.api_internal_url,
        headers={"X-Internal-Token": conf.internal_token},
        timeout=TIMEOUT_SECONDS,
        transport=_transport,
    ) as client:
        for attempt in (1, 2):
            try:
                response = await client.request(method, path, json=json, params=params)
            except httpx.TransportError as exc:  # 연결 실패·타임아웃
                last = f"{type(exc).__name__}"
            else:
                if response.status_code < 400:
                    try:
                        return ok(response.json() if response.content else None)
                    except ValueError:
                        logger.warning("api returned non-JSON body: %s %s", method, path)
                        return fail("upstream_unavailable", "api returned invalid JSON", True)
                if response.status_code < 500:
                    code = STATUS_CODES.get(response.status_code, "invalid_input")
                    return fail(code, _error_message(response))
                last = f"api responded {response.status_code}"
            logger.warning("api call failed (attempt %d): %s %s -> %s", attempt, method, path, last)
    return fail("upstream_unavailable", last, retryable=True)
