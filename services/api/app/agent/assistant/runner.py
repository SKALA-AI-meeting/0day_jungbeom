"""어시스턴트: AssistantRunner Protocol 구현(docs/architecture/agents.md "어시스턴트", R5-13).

```
agent(LLM, 도구 바인딩) ⇄ tools(search_materials·get_material) … 최대 3회 → answer → guard
```

- 모델이 질문을 보고 도구 호출 여부와 인자를 스스로 고른다. 응답당 도구 3회, 넘으면 지금까지
  결과로 답한다.
- 열린 자료만 검색된다. 도구가 `not_released`만 돌려주면 LLM 답 대신 고정 문장("키워드가 정해지면
  …").
- 인용: 도구로 받은 자료 중 답에 쓴 것을 `cited_material_ids`로 내고 본문에 출처 제목을 붙인다.
- guard: 공통 금지 패턴 → 재생성 1회 → 그 그룹의 notice. 토론방 대화·다른 참여자 정보는 보지 않는다.
- 요청·응답 메시지 저장, assistant_calls, 60회 한도(429)는 api가 한다. 같은 세션 호출은 세션
  Lock으로
  하나씩 돌고, 자기 대화(thread `assistant:{session_id}`)는 프로세스 메모리에 최근 몇 턴만 둔다.
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.agent.catalog import Catalog
from app.agent.guard import guard_from_prompts
from app.agent.llm import BaseLLM, LLMUnavailable, Trace, Usage
from app.agent.mcp_client import ASSISTANT_TOOLS, RAG, McpClient, ToolScope, error_code, for_model
from app.agent.runner import AssistantResult
from app.masking import mask

log = logging.getLogger(__name__)

MAX_TOOL_CALLS = 3
QUESTION_CHARS = 2000
HISTORY_TURNS = 6
SOURCE_PREFIX = "출처: "
FALLBACK_TEXT = "잠시 후 다시 시도해 주세요."
LOCKED_TEXT = "키워드가 정해지면 자료를 찾을 수 있어요."

RagFactory = Callable[[uuid.UUID], AbstractAsyncContextManager[ToolScope]]
ScenarioLoader = Callable[[uuid.UUID], Awaitable[dict[str, Any]]]


def thread_id(session_id: object) -> str:
    return f"assistant:{session_id}"


def mcp_rag(url: str) -> RagFactory:
    """운영 경로: 호출마다 rag-mcp 연결을 열고 어시스턴트 허용 목록으로 고정한다."""

    @asynccontextmanager
    async def open_rag(session_id: uuid.UUID) -> AsyncIterator[ToolScope]:
        async with McpClient({RAG: url}, session_id) as client:
            yield client.scope(ASSISTANT_TOOLS)

    return open_rag


class AssistantGraphRunner:
    def __init__(
        self,
        *,
        llm: BaseLLM,
        rag: RagFactory,
        scenario: ScenarioLoader,
        scenarios_dir: Path | None = None,
    ) -> None:
        self.llm = llm
        self.rag = rag
        self.scenario = scenario
        self.scenarios_dir = scenarios_dir
        self._catalogs: dict[uuid.UUID, Catalog] = {}
        self._history: defaultdict[uuid.UUID, list[dict[str, str]]] = defaultdict(list)
        self._locks: defaultdict[uuid.UUID, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def catalog(self, session_id: uuid.UUID) -> Catalog:
        if session_id not in self._catalogs:
            scenario = await self.scenario(session_id)
            self._catalogs[session_id] = Catalog.from_scenario(scenario, self.scenarios_dir)
        return self._catalogs[session_id]

    async def answer(
        self, session_id: uuid.UUID, prompt: str, call_id: uuid.UUID
    ) -> AssistantResult:
        async with self._locks[session_id]:
            return await self._answer(session_id, prompt, call_id)

    async def _answer(
        self, session_id: uuid.UUID, prompt: str, call_id: uuid.UUID
    ) -> AssistantResult:
        catalog = await self.catalog(session_id)
        question = mask(prompt).strip()[:QUESTION_CHARS]
        usage = Usage()
        trace = Trace(str(call_id), str(session_id), "assistant")
        async with self.rag(session_id) as rag:
            loop = _Loop(self.llm, rag, catalog, usage, trace)
            content, cited, fallback = await loop.run(question, self._history[session_id])
        history = self._history[session_id]
        history.extend(
            [{"role": "user", "content": question}, {"role": "assistant", "content": content}]
        )
        del history[: -HISTORY_TURNS * 2]
        body = usage.as_dict()
        body["fallback_used"] = fallback
        return AssistantResult(
            content=content, cited_material_ids=cited, tool_calls=loop.tool_calls, usage=body
        )


class _Loop:
    def __init__(
        self, llm: BaseLLM, rag: ToolScope, catalog: Catalog, usage: Usage, trace: Trace
    ) -> None:
        self.llm = llm
        self.rag = rag
        self.catalog = catalog
        self.usage = usage
        self.trace = trace
        self.guard = guard_from_prompts(catalog.prompts)
        self.tool_calls: list[dict[str, Any]] = []
        self.retrieved: dict[str, str] = {}  # material_id → title(열린 자료만)
        self.locked = False

    def _system(self) -> str:
        return self.catalog.prompts.get("assistant.md", "").strip()

    async def run(
        self, question: str, history: list[dict[str, str]]
    ) -> tuple[str, list[str], bool]:
        messages: list[BaseMessage] = [SystemMessage(self._system())]
        for turn in history[-HISTORY_TURNS * 2 :]:
            cls = HumanMessage if turn["role"] == "user" else AIMessage
            messages.append(cls(turn["content"]))
        messages.append(HumanMessage(question))
        try:
            draft = await self._agent(messages)
        except LLMUnavailable as exc:
            log.warning("assistant llm unavailable: %s", exc)
            return FALLBACK_TEXT, [], True
        if self.locked and not self.retrieved:
            return self.catalog.fixed.get("assistant_locked", LOCKED_TEXT), [], False
        checked = self.guard.check(draft)
        if not checked.ok:
            note = HumanMessage(
                f"[다시 쓰기] 앞 답은 금지 표현({', '.join(checked.hits)}) 때문에 쓸 수 없다. "
                "다시 답한다."
            )
            try:
                again = await self.llm.ainvoke(
                    [*messages, note], usage=self.usage, trace=self.trace
                )
                second = self.guard.check(str(again.content))
            except LLMUnavailable:
                second = None
            if second is None or not second.ok:
                key = self.guard.notice_key(checked.hits[0]) or "evaluation"
                return self.catalog.notices.get(key, FALLBACK_TEXT), [], False
            checked = second
        return (*self._cite(checked.text), False)

    async def _agent(self, messages: list[BaseMessage]) -> str:
        specs = await self.rag.specs()
        history = list(messages)
        while True:
            bind = specs if specs and len(self.tool_calls) < MAX_TOOL_CALLS else None
            message = await self.llm.ainvoke(
                history, usage=self.usage, trace=self.trace, tools=bind
            )
            if not (message.tool_calls and bind):
                return str(message.content or "").strip()
            history.append(message)
            for call in message.tool_calls:
                args = dict(call.get("args") or {})
                if len(self.tool_calls) >= MAX_TOOL_CALLS:
                    result = {"ok": False, "error": {"code": "forbidden", "message": "tool limit"}}
                else:
                    result = await self.rag.call(call["name"], args)
                    self.usage.tool_calls += 1
                    self.tool_calls.append({"name": call["name"], **args})
                    self._collect(call["name"], result)
                history.append(ToolMessage(for_model(result), tool_call_id=call["id"]))

    def _collect(self, name: str, result: dict[str, Any]) -> None:
        if error_code(result) == "not_released":
            self.locked = True
            return
        data = result.get("data") if result.get("ok") else None
        items = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
        for item in items:
            if isinstance(item, dict) and item.get("material_id"):
                self.retrieved.setdefault(
                    item["material_id"], item.get("title") or item["material_id"]
                )

    def _cite(self, text: str) -> tuple[str, list[str]]:
        """답에 제목·id가 나온 자료를 인용으로. 하나도 없으면 받은 자료 전부(최대 3)를 출처로
        붙인다.
        """
        body = text.strip()
        cited = [m for m, t in self.retrieved.items() if t in body or m in body]
        if not cited:
            cited = list(self.retrieved)[:MAX_TOOL_CALLS]
        missing = [self.retrieved[m] for m in cited if self.retrieved[m] not in body]
        if missing:
            line = SOURCE_PREFIX + ", ".join(missing)
            room = self.guard.max_chars - len(line) - 1
            body = f"{body[: max(room, 0)].rstrip()}\n{line}"
        return body[: self.guard.max_chars], cited
