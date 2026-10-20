"""business-mcp·rag-mcp Streamable HTTP 클라이언트(contracts.md "MCP 도구").

- 한 실행(run) 동안 두 서버 연결을 열어 둔다. 연결은 들어간 task에서 닫아야 하므로(anyio)
  runner가 `async with McpClient(...)`로 열고 닫고, 그래프 노드는 열린 연결로 호출만 한다.
- 그래프별 허용 목록(계약 표)을 `scope(allowed)`로 고정한다. 허용 밖 도구는 서버를 부르지 않고
  `{ok:false, error:{code:"forbidden"}}`를 돌려준다.
- session_id는 이 클라이언트가 주입한다. 모델이 인자로 넣어도 덮어쓴다.
- 도구 결과 `{ok:false}`는 예외가 아니라 값이다. 연결 실패·전송 오류는
  `upstream_unavailable`(retryable) 값으로 바꾼다. 호출한 노드가 폴백을 정한다.
"""

import json
import logging
import uuid
from collections.abc import Mapping
from contextlib import AsyncExitStack
from typing import Any

from mcp import Client

log = logging.getLogger(__name__)

BUSINESS = "business"
RAG = "rag"

TOOL_SERVER: dict[str, str] = {
    **{
        name: BUSINESS
        for name in (
            "get_session",
            "list_messages",
            "get_board",
            "get_shared_documents",
            "post_message",
            "set_division",
            "update_task",
            "send_document",
            "release_document",
            "record_observation",
            "update_observation",
        )
    },
    **{
        name: RAG
        for name in ("search_documents", "get_document", "list_documents", "reindex_documents")
    },
}

# 그래프별 허용 목록. reindex_documents는 어느 에이전트에도 열지 않는다. respond는 페르소나별로
# 나눈다(contracts.md 허용 목록): 팀장은 회사 문서의 뜻 질문에 답하려고 search_documents만 쓰고
# get_document는 없다.
RESPOND_TOOLS = frozenset({"search_documents", "get_document", "get_board", "get_shared_documents"})
MANAGER_RESPOND_TOOLS = frozenset({"search_documents", "get_board", "get_shared_documents"})
PERSONA_TOOLS = {"colleague": RESPOND_TOOLS, "manager": MANAGER_RESPOND_TOOLS}
ASSISTANT_TOOLS = frozenset({"search_documents", "get_document"})
# 결정적 노드가 코드로 직접 부르는 도구(business-mcp 전부 + rag 조회)
SESSION_CODE_TOOLS = frozenset(
    {n for n, s in TOOL_SERVER.items() if s == BUSINESS}
    | {"search_documents", "get_document", "list_documents"}
)

RESULT_CHARS = 2000  # 모델에 넘기는 도구 결과 절단(harness.md Tools)


def ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def fail(code: str, message: str, retryable: bool = False) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "retryable": retryable}}


def error_code(result: dict[str, Any]) -> str | None:
    return None if result.get("ok") else (result.get("error") or {}).get("code")


def for_model(result: dict[str, Any]) -> str:
    """모델에 넘길 도구 결과 문자열(2k자 절단)."""
    text = json.dumps(result, ensure_ascii=False, default=str)
    return text if len(text) <= RESULT_CHARS else text[:RESULT_CHARS] + "…(잘림)"


class McpClient:
    def __init__(self, urls: Mapping[str, str], session_id: uuid.UUID | str) -> None:
        self.urls = dict(urls)
        self.session_id = str(session_id)
        self._stack = AsyncExitStack()
        self._clients: dict[str, Client] = {}
        self._down: dict[str, str] = {}
        self._specs: dict[str, dict[str, Any]] | None = None

    async def __aenter__(self) -> "McpClient":
        for server, url in self.urls.items():
            try:
                self._clients[server] = await self._stack.enter_async_context(
                    Client(url, mode="legacy")
                )
            except Exception as exc:  # 연결 실패는 그 서버의 모든 호출을 upstream_unavailable로
                log.warning("mcp %s unavailable at %s: %r", server, url, exc)
                self._down[server] = type(exc).__name__
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        try:
            await self._stack.aclose()
        except Exception:  # 서버가 먼저 끊긴 경우. 실행 결과에는 영향 없음
            log.debug("mcp close failed", exc_info=True)

    def scope(self, allowed: frozenset[str]) -> "ToolScope":
        return ToolScope(self, allowed)

    async def _call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        server = TOOL_SERVER.get(name)
        if server is None:
            return fail("not_found", f"unknown tool {name}")
        if server in self._down or server not in self._clients:
            reason = self._down.get(server, "not configured")
            return fail("upstream_unavailable", f"{server}-mcp: {reason}", True)
        args = {**args, "session_id": self.session_id}
        if name == "reindex_documents":
            args.pop("session_id")
        try:
            result = await self._clients[server].call_tool(name, args)
        except Exception as exc:
            log.warning("mcp call %s failed: %r", name, exc)
            return fail("upstream_unavailable", f"{name}: {type(exc).__name__}", True)
        data = result.structured_content
        if isinstance(data, dict) and "ok" in data:
            return data
        text = " ".join(getattr(c, "text", "") for c in result.content)
        return fail("internal", text or f"{name}: unexpected result")

    async def _all_specs(self) -> dict[str, dict[str, Any]]:
        """서버가 광고한 도구 스키마(session_id 제외)를 OpenAI function 형식으로. 실행당 1회."""
        if self._specs is None:
            self._specs = {}
            for client in self._clients.values():
                try:
                    listed = await client.list_tools()
                except Exception as exc:
                    log.warning("mcp list_tools failed: %r", exc)
                    continue
                for tool in listed.tools:
                    self._specs[tool.name] = _function_spec(tool)
        return self._specs


class ToolScope:
    """허용 목록이 고정된 호출 창구. 그래프 노드는 이것만 받는다."""

    def __init__(self, client: McpClient, allowed: frozenset[str]) -> None:
        self._client = client
        self.allowed = allowed
        self.rejected: list[str] = []

    async def call(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        if name not in self.allowed:
            self.rejected.append(name)
            log.warning("tool %s rejected (not in allowlist)", name)
            return fail("forbidden", f"tool {name} is not allowed here")
        return await self._client._call(name, dict(args or {}))

    async def specs(self) -> list[dict[str, Any]]:
        specs = await self._client._all_specs()
        return [specs[name] for name in sorted(self.allowed) if name in specs]


def _function_spec(tool: Any) -> dict[str, Any]:
    schema = json.loads(json.dumps(tool.input_schema or {"type": "object", "properties": {}}))
    schema.get("properties", {}).pop("session_id", None)
    if "required" in schema:
        schema["required"] = [r for r in schema["required"] if r != "session_id"]
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": (tool.description or "").strip(),
            "parameters": schema,
        },
    }
