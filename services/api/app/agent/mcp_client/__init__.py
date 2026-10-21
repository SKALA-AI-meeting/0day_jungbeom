"""debate-mcp·rag-mcp·assessment-mcp Streamable HTTP 클라이언트(docs/contracts/mcp.md "MCP 도구").

- 한 실행(run) 동안 서버 연결을 열어 둔다. 연결은 들어간 task에서 닫아야 하므로(anyio) runner가
  `async with`로 열고 닫고, 그래프 노드는 열린 연결로 호출만 한다.
- 주체별 허용 목록(docs/contracts/mcp.md "도구 허용 목록")을 `scope(allowed)`로 고정한다. 허용 밖
도구는
  서버를
  부르지 않고 `{ok:false, error:{code:"forbidden"}}`를 돌려준다.
- **assessment는 클라이언트를 분리한다**: assessment URL·토큰은 `AssessmentClient`만 갖고, 페르소나
  scope를 만드는 `McpClient`에는 assessment 서버가 아예 없다(허용 목록 + 클라이언트 분리의 이중
  차단).
- session_id는 이 클라이언트가 주입한다. 모델이 인자로 넣어도 덮어쓴다.
- 도구 결과 `{ok:false}`는 예외가 아니라 값이다. 연결 실패·전송 오류는
  `upstream_unavailable`(retryable)
  값으로 바꾸고 1회 재시도한다(harness.md Recovery). 호출한 노드가 폴백을 정한다.
"""

import json
import logging
import uuid
from collections.abc import Mapping
from contextlib import AsyncExitStack
from typing import Any, Protocol

log = logging.getLogger(__name__)

DEBATE = "debate"
RAG = "rag"
ASSESSMENT = "assessment"

DEBATE_TOOLS = frozenset(
    {
        "get_debate_state",
        "get_transcript",
        "get_draft",
        "post_message",
        "propose_option",
        "set_stance",
        "fill_slot",
    }
)
RAG_TOOLS = frozenset({"search_materials", "get_material", "reindex_materials"})
ASSESSMENT_TOOLS = frozenset(
    {
        "record_observation",
        "get_rubric",
        "get_session_record",
        "get_transcript_span",
        "get_contributions",
        "save_evaluation",
    }
)
TOOL_SERVER: dict[str, str] = {
    **{name: DEBATE for name in DEBATE_TOOLS},
    **{name: RAG for name in RAG_TOOLS},
    **{name: ASSESSMENT for name in ASSESSMENT_TOOLS},
}

# 주체별 허용 목록(docs/contracts/mcp.md). reindex_materials는 어느 에이전트에도 열지 않는다.
CODE_TOOLS = DEBATE_TOOLS | frozenset({"record_observation"})  # 결정적 노드(load·cards·apply·fill)
PERSONA_TOOLS = frozenset({"get_transcript", "search_materials", "get_material"})
PERSONA_PROPOSAL_TOOLS = PERSONA_TOOLS | frozenset({"get_draft"})  # get_draft는 proposal 단계만
ASSISTANT_TOOLS = frozenset({"search_materials", "get_material"})
TURN_TOOLS: frozenset[str] = frozenset()

RESULT_CHARS = 2000  # 모델에 넘기는 도구 결과 절단(harness.md Tools)
ASSESSMENT_HEADER = "X-Assessment-Token"


def ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def fail(code: str, message: str, retryable: bool = False) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "retryable": retryable}}


def error_code(result: dict[str, Any]) -> str | None:
    return None if result.get("ok") else (result.get("error") or {}).get("code")


def error_message(result: dict[str, Any]) -> str | None:
    """409 세부 코드(no_consensus·stale_generation·slot_confirmed·phase_not_open)가 담기는 곳."""
    return None if result.get("ok") else (result.get("error") or {}).get("message")


def for_model(result: dict[str, Any]) -> str:
    """모델에 넘길 도구 결과 문자열(2k자 절단)."""
    text = json.dumps(result, ensure_ascii=False, default=str)
    return text if len(text) <= RESULT_CHARS else text[:RESULT_CHARS] + "…(잘림)"


class Caller(Protocol):
    """도구를 실제로 부르는 쪽(McpClient·AssessmentClient·테스트의 가짜 서버)."""

    async def _call(self, name: str, args: dict[str, Any]) -> dict[str, Any]: ...

    async def _all_specs(self) -> dict[str, dict[str, Any]]: ...


class McpClient:
    """여러 서버 연결 묶음. urls에 없는 서버의 도구는 upstream_unavailable."""

    def __init__(
        self,
        urls: Mapping[str, str],
        session_id: uuid.UUID | str,
        headers: Mapping[str, Mapping[str, str]] | None = None,
    ) -> None:
        self.urls = dict(urls)
        self.session_id = str(session_id)
        self._headers = {k: dict(v) for k, v in (headers or {}).items()}
        self._stack = AsyncExitStack()
        self._clients: dict[str, Any] = {}
        self._down: dict[str, str] = {}
        self._specs: dict[str, dict[str, Any]] | None = None

    async def __aenter__(self) -> "McpClient":
        from mcp import Client

        for server, url in self.urls.items():
            try:
                target: Any = url
                if self._headers.get(server):
                    from mcp.client.streamable_http import streamable_http_client
                    from mcp.shared._httpx_utils import create_mcp_http_client

                    http = create_mcp_http_client(headers=self._headers[server])
                    target = streamable_http_client(url, http_client=http)
                self._clients[server] = await self._stack.enter_async_context(
                    Client(target, mode="legacy")
                )
            except Exception as exc:  # 연결 실패는 그 서버의 모든 호출을 upstream_unavailable로
                log.warning("mcp %s unavailable: %r", server, exc)
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
        if name == "reindex_materials":
            args.pop("session_id")
        try:
            result = await self._clients[server].call_tool(name, args)
        except Exception as exc:
            log.warning("mcp call %s failed: %r", name, exc)
            return fail("upstream_unavailable", f"{name}: {type(exc).__name__}", True)
        data = getattr(result, "structured_content", None)
        if isinstance(data, dict) and "ok" in data:
            return data
        text = " ".join(getattr(c, "text", "") for c in getattr(result, "content", []) or [])
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "ok" in parsed:
                return parsed
        except ValueError:
            pass
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
                    self._specs[tool.name] = function_spec(
                        tool.name, tool.description or "", tool.input_schema
                    )
        return self._specs


class AssessmentClient(McpClient):
    """assessment-mcp 전용 클라이언트(토큰 헤더). 결정적 노드만 만든다."""

    def __init__(self, url: str, token: str, session_id: uuid.UUID | str) -> None:
        super().__init__({ASSESSMENT: url}, session_id, {ASSESSMENT: {ASSESSMENT_HEADER: token}})

    async def _call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if TOOL_SERVER.get(name) != ASSESSMENT:
            return fail("forbidden", f"tool {name} is not served by assessment client")
        return await super()._call(name, args)


class ToolScope:
    """허용 목록이 고정된 호출 창구. 그래프 노드는 이것만 받는다.

    callers는 서버별 호출자(도구 이름 → 서버로 고른다). 같은 서버에 호출자가 없으면
    upstream_unavailable.
    """

    def __init__(
        self, caller: Caller, allowed: frozenset[str], extra: Mapping[str, Caller] | None = None
    ) -> None:
        self._caller = caller
        self._extra = dict(extra or {})
        self.allowed = allowed
        self.rejected: list[str] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _route(self, name: str) -> Caller:
        return self._extra.get(TOOL_SERVER.get(name, ""), self._caller)

    async def call(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        if name not in self.allowed:
            self.rejected.append(name)
            log.warning("tool %s rejected (not in allowlist)", name)
            return fail("forbidden", f"tool {name} is not allowed here")
        body = dict(args or {})
        body.pop("session_id", None)  # session_id는 클라이언트가 주입한다
        self.calls.append((name, body))
        caller = self._route(name)
        result = await caller._call(name, body)
        if not result.get("ok") and (result.get("error") or {}).get("retryable"):
            result = await caller._call(name, body)  # upstream_unavailable 1회 재시도
        return result

    async def specs(self) -> list[dict[str, Any]]:
        specs: dict[str, dict[str, Any]] = {}
        for caller in (self._caller, *self._extra.values()):
            specs.update(await caller._all_specs())
        return [specs[name] for name in sorted(self.allowed) if name in specs]


def function_spec(name: str, description: str, input_schema: dict[str, Any] | None) -> dict:
    schema = json.loads(json.dumps(input_schema or {"type": "object", "properties": {}}))
    schema.get("properties", {}).pop("session_id", None)
    if "required" in schema:
        schema["required"] = [r for r in schema["required"] if r != "session_id"]
    return {
        "type": "function",
        "function": {"name": name, "description": description.strip(), "parameters": schema},
    }


class RunTools:
    """한 실행의 도구 창구 묶음. code = 결정적 노드, persona(phase) = 페르소나 respond."""

    def __init__(self, main: Caller, assessment: Caller | None) -> None:
        self._main = main
        self._assessment = assessment
        extra = {ASSESSMENT: assessment} if assessment is not None else {}
        self.code = ToolScope(main, CODE_TOOLS, extra)

    def persona(self, phase: str) -> ToolScope:
        # 페르소나 scope에는 assessment 호출자를 넘기지 않는다(허용 목록과 별개의 차단)
        allowed = PERSONA_PROPOSAL_TOOLS if phase == "proposal" else PERSONA_TOOLS
        return ToolScope(self._main, allowed)


class McpRunTools:
    """운영 경로: 실행마다 debate+rag 연결과 assessment 연결(토큰)을 따로 연다."""

    def __init__(
        self,
        session_id: uuid.UUID,
        *,
        debate_url: str,
        rag_url: str,
        assessment_url: str,
        assessment_token: str,
    ) -> None:
        self._main = McpClient({DEBATE: debate_url, RAG: rag_url}, session_id)
        self._assessment = AssessmentClient(assessment_url, assessment_token, session_id)

    async def __aenter__(self) -> RunTools:
        await self._main.__aenter__()
        await self._assessment.__aenter__()
        return RunTools(self._main, self._assessment)

    async def __aexit__(self, *exc_info: object) -> None:
        await self._assessment.__aexit__(*exc_info)
        await self._main.__aexit__(*exc_info)
