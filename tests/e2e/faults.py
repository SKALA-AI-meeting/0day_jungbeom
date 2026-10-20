"""장애 주입 층. api 내부 앱(8001) 앞에 끼우는 ASGI 미들웨어다.

실 스택에서는 러너가 business-mcp·report-worker의 API_INTERNAL_URL을 이 프록시(Forward)로 돌려
요청을 지나가게 한다. 테스트에서는 같은 미들웨어로 프로세스 안 내부 앱을 감싼다.

- fail: 다음 n번의 일치 요청을 503으로 돌려준다(MCP는 5xx를 upstream_unavailable로,
  워커는 재시도로).
  fail_tool은 MCP 도구 호출 단위(MCP 안 재시도 포함)다.
- after: 일치 요청이 2xx로 지나간 직후 콜백을 부른다(변경 도구 성공 직후·final 저장 직후 종료).
"""

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

# business-mcp 도구 → api 내부 경로(contracts.md MCP 도구 표). 장애 주입 대상만
TOOL_PATHS = {
    "send_document": ("POST", r"/internal/sessions/[^/]+/docs/send$"),
    "post_message": ("POST", r"/internal/sessions/[^/]+/messages$"),
    "record_observation": ("POST", r"/internal/sessions/[^/]+/observations$"),
    "report_draft": ("POST", r"/internal/sessions/[^/]+/report/draft$"),
    "report_final": ("POST", r"/internal/sessions/[^/]+/report/final$"),
}

# business-mcp는 api 5xx를 1회 재시도한 뒤 upstream_unavailable을 돌려준다(business_mcp/client.py).
# 대본 inject의 fail_times는 도구 호출 단위라 HTTP 실패 수로는 이 배수다
MCP_HTTP_ATTEMPTS = 2


@dataclass
class Rule:
    method: str
    pattern: re.Pattern
    times: int  # fail: 남은 실패 횟수, after: 남은 콜백 횟수
    callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None
    match_body: Callable[[dict[str, Any]], bool] | None = None
    hits: int = 0


class Faults:
    """ASGI 미들웨어. 규칙은 등록 순서대로 본다."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.rules: list[Rule] = []
        self.log: list[dict[str, Any]] = []

    def fail(self, tool: str, times: int) -> Rule:
        method, pattern = TOOL_PATHS[tool]
        rule = Rule(method, re.compile(pattern), times)
        self.rules.append(rule)
        return rule

    def fail_tool(self, tool: str, calls: int) -> Rule:
        """도구 호출 calls번이 실패하도록(MCP 안 재시도까지 모두 503)."""
        return self.fail(tool, calls * MCP_HTTP_ATTEMPTS)

    def after(
        self,
        tool: str,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
        match_body: Callable[[dict[str, Any]], bool] | None = None,
    ) -> Rule:
        method, pattern = TOOL_PATHS[tool]
        rule = Rule(method, re.compile(pattern), 1, callback, match_body)
        self.rules.append(rule)
        return rule

    def _find(self, scope: dict[str, Any], kind: str) -> Rule | None:
        for rule in self.rules:
            if (
                rule.times > 0
                and (rule.callback is None) == (kind == "fail")
                and scope["method"] == rule.method
                and rule.pattern.search(scope["path"])
            ):
                return rule
        return None

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        failing = self._find(scope, "fail")
        if failing is not None:
            failing.times -= 1
            failing.hits += 1
            self.log.append({"fail": scope["path"]})
            body = b'{"error":{"code":"internal","message":"e2e fault injection"}}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 503,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        watching = self._find(scope, "after")
        if watching is None:
            await self.app(scope, receive, send)
            return

        # 요청 본문을 읽어 두었다가(조건 검사) 앱에 그대로 다시 준다
        chunks = []
        while True:
            message = await receive()
            chunks.append(message.get("body", b""))
            if not message.get("more_body"):
                break
        raw = b"".join(chunks)

        async def replay():
            return {"type": "http.request", "body": raw, "more_body": False}

        status = {}

        async def capture(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        await self.app(scope, replay, capture)
        try:
            body = httpx.Response(200, content=raw).json() if raw else {}
        except ValueError:
            body = {}
        ok = 200 <= status.get("code", 500) < 300
        if ok and (watching.match_body is None or watching.match_body(body)):
            watching.times -= 1
            watching.hits += 1
            self.log.append({"after": scope["path"]})
            await watching.callback(body)


class Forward:
    """요청을 upstream(api 내부 앱)으로 그대로 넘기는 ASGI 앱. 실 스택 프록시의 안쪽."""

    def __init__(self, upstream: str) -> None:
        self.client = httpx.AsyncClient(base_url=upstream, timeout=60)

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await self.client.aclose()
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        chunks = []
        while True:
            message = await receive()
            chunks.append(message.get("body", b""))
            if not message.get("more_body"):
                break
        path = scope["path"] + (
            f"?{scope['query_string'].decode()}" if scope["query_string"] else ""
        )
        headers = [(k.decode(), v.decode()) for k, v in scope["headers"] if k != b"host"]
        try:
            response = await self.client.request(
                scope["method"], path, content=b"".join(chunks), headers=headers
            )
            status, content = response.status_code, response.content
            out_headers = [
                (b"content-type", response.headers.get("content-type", "application/json").encode())
            ]
        except httpx.TransportError:
            # api가 내려가 있을 때(재시작 장애 주입 중) 연결 실패를 502로 전한다
            status, content, out_headers = 502, b"", []
        await send({"type": "http.response.start", "status": status, "headers": out_headers})
        await send({"type": "http.response.body", "body": content})
