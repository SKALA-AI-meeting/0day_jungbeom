"""어시스턴트 그래프(docs/agent/design.md "어시스턴트 그래프").

START → retrieve → answer → guard → END.

thread `assistant:{session_id}`, 호출 하나에 한 번 실행한다. State에는 자기 대화(history)만 이어지고
검색 결과·초안은 호출마다 새로 쓴다. 컨텍스트 허용 목록(harness.md Context): 자기 대화 + 공개된 회사
문서 청크. 팀 대화·동료 문서·카드·관찰 레이블은 노드가 받지도 않는다(도구는 search_documents·
get_document뿐, 둘 다 rag-mcp가 공개 문서로 거른다).
"""

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from app.agent.assistant import tokens
from app.agent.guard import Guard, guard_for
from app.agent.llm import BaseLLM, LLMUnavailable, Trace, Usage
from app.agent.mcp_client import error_code
from app.masking import mask

log = logging.getLogger(__name__)

SEARCH_TOP_K = 3  # harness.md Tools
MAX_TOOL_CALLS = 3  # 응답당 도구 호출(검색 포함, harness.md Tools)
DOC_CHARS = 800  # 이름으로 짚은 문서를 get_document로 읽었을 때 넣는 앞부분
HISTORY_KEEP = 12  # State에 남기는 자기 대화(요청·응답 합쳐서)
# 호출당 입력 예산(harness.md Context 6k 토큰, gpt-4o-mini 인코딩으로 실제 계산). system을 먼저
# 넣고, 질문(최대 QUESTION_TOKENS)·검색 블록(남는 만큼 자름)을 넣은 뒤 남는 만큼 최근 대화를 넣는다.
# 들어가지 않는 오래된 대화는 질문 앞부분 한 줄씩 접고, 그 요약도 남는 만큼만 넣는다.
INPUT_TOKENS = 6000
QUESTION_TOKENS = 1500
FOLD_CHARS = 40  # 접힌 대화 한 건당 남기는 질문 앞부분
# 고정 문장. 미공개 문서는 assistant.md 2절, LLM 실패는 harness.md Recovery
NOT_RELEASED_TEXT = "아직 공유되지 않은 자료라 볼 수 없어요."
FALLBACK_TEXT = "잠시 후 다시 시도해 주세요."
SOURCE_PREFIX = "출처: "
LONG_QUESTION_NOTICE = "질문이 길어서 앞부분까지만 보고 답했어요."


class Tools(Protocol):
    """허용 목록이 고정된 도구 창구(mcp_client.ToolScope와 같은 모양)."""

    async def call(self, name: str, args: dict[str, Any] | None = None) -> dict[str, Any]: ...


Progress = Callable[[str, str, str | None], Awaitable[None]]


@dataclass
class AssistantDeps:
    """호출마다 바뀌는 의존성(Runtime context)."""

    llm: BaseLLM
    rag: Tools
    scenario: dict[str, Any]
    usage: Usage
    progress: Progress

    def trace(self, state: "AssistantState", node: str) -> Trace:
        return Trace(state["call_id"], state["session_id"], node)


class AssistantState(TypedDict, total=False):
    session_id: str
    call_id: str
    prompt: str  # 마스킹·길이 제한을 거친 질문(runner가 넣는다)
    prompt_truncated: bool
    history: list[dict[str, str]]  # [{role: user|assistant, content}] 오래된 것부터
    results: list[dict[str, Any]]  # 이번 호출의 공개 문서 청크 [{doc_id, title, chunk}]
    # 인용 허용 집합 = searched ∪ fetched. 그 밖의 문서 인용은 지운다
    searched: list[str]  # search_documents가 돌려준 doc_id
    fetched: list[str]  # get_document로 읽은 공개 문서 doc_id
    not_released: list[str]  # 질문이 짚었지만 아직 공개 전인 문서 id
    draft: str
    fixed: bool  # draft가 고정 문장(인용 없음)
    fallback_used: bool
    content: str
    cited_docs: list[str]


def thread_id(session_id: object) -> str:
    return f"assistant:{session_id}"


async def retrieve(state: AssistantState, runtime: Runtime[AssistantDeps]) -> dict[str, Any]:
    """search_documents top3. 질문이 문서 이름을 짚었는데 결과에 없으면 get_document로 확인한다.

    공개 전이면 not_released로 남기고(내용은 받지 않는다), 공개된 문서면 앞부분을 결과에 더한다.
    도구 호출은 검색 포함 MAX_TOOL_CALLS까지만. 넘는 문서 이름은 확인하지 않는다.
    """
    deps = runtime.context
    guard = guard_for(deps.scenario)
    await deps.progress("retrieve", "tool_start", "search_documents")
    found = await deps.rag.call(
        "search_documents", {"query": state["prompt"], "top_k": SEARCH_TOP_K}
    )
    deps.usage.tool_calls += 1
    await deps.progress("retrieve", "tool_end", "search_documents")
    if not found.get("ok"):
        # 검색이 안 되면 근거 없이 답하지 않는다(answer가 폴백 문장으로 간다)
        log.warning("assistant search failed: %s", error_code(found))
        return {
            "results": [],
            "searched": [],
            "fetched": [],
            "not_released": [],
            "fixed": True,
            "fallback_used": True,
        }
    results = [
        {"doc_id": r["doc_id"], "title": r["title"], "chunk": r["chunk"]} for r in found["data"]
    ]
    searched = list(dict.fromkeys(r["doc_id"] for r in results))
    fetched: list[str] = []
    not_released: list[str] = []
    calls = 1
    for doc_id in guard.cited_docs(state["prompt"]):
        if doc_id in searched:
            continue
        if calls >= MAX_TOOL_CALLS:
            break
        await deps.progress("retrieve", "tool_start", "get_document")
        doc = await deps.rag.call("get_document", {"doc_id": doc_id})
        calls += 1
        deps.usage.tool_calls += 1
        await deps.progress("retrieve", "tool_end", "get_document")
        if doc.get("ok"):
            data = doc["data"]
            fetched.append(doc_id)
            results.append(
                {"doc_id": doc_id, "title": data["title"], "chunk": data["content"][:DOC_CHARS]}
            )
        elif error_code(doc) == "not_released":
            not_released.append(doc_id)
    return {
        "results": results,
        "searched": searched,
        "fetched": fetched,
        "not_released": not_released,
        "fixed": False,
        "fallback_used": False,
    }


async def answer(state: AssistantState, runtime: Runtime[AssistantDeps]) -> dict[str, Any]:
    """인용 포함 답 생성. 질문이 짚은 문서가 모두 공개 전이면 LLM 없이 고정 문장으로 답한다."""
    deps = runtime.context
    if state.get("fixed"):
        return {"draft": FALLBACK_TEXT}
    named = guard_for(deps.scenario).cited_docs(state["prompt"])
    if state["not_released"] and set(named) <= set(state["not_released"]):
        return {"draft": NOT_RELEASED_TEXT, "fixed": True}
    await deps.progress("answer", "started", None)
    try:
        message = await deps.llm.ainvoke(
            _messages(state, deps.scenario), usage=deps.usage, trace=deps.trace(state, "answer")
        )
    except LLMUnavailable as exc:
        log.warning("assistant llm unavailable: %s", exc)
        await deps.progress("answer", "failed", None)
        return {"draft": FALLBACK_TEXT, "fixed": True, "fallback_used": True}
    await deps.progress("answer", "finished", None)
    draft = str(message.content)
    if state.get("prompt_truncated"):
        draft = f"{LONG_QUESTION_NOTICE}\n{draft}"
    return {"draft": draft}


async def guard_node(state: AssistantState, runtime: Runtime[AssistantDeps]) -> dict[str, Any]:
    """금지 패턴 치환·600자. 인용은 허용 집합(searched ∪ fetched) 안의 문서만 남기고 출처 줄을 다시
    쓴다.
    """
    guard = guard_for(runtime.context.scenario)
    if state.get("fixed"):
        content, cited = guard.apply(state["draft"]).text, []
    else:
        allowed = set(state["searched"]) | set(state["fetched"])
        content, cited = _cite(guard, state["draft"], allowed)
    turn = [
        {"role": "user", "content": state["prompt"]},
        {"role": "assistant", "content": content},
    ]
    history = (state.get("history") or []) + turn
    return {"content": content, "cited_docs": cited, "history": history[-HISTORY_KEEP:]}


def _messages(state: AssistantState, scenario: dict[str, Any]) -> list[BaseMessage]:
    """system = common_rules + assistant.md. 예산 안의 최근 대화를 차례로 두고, 마지막 사람 메시지에
    검색 결과 블록과 질문을 넣는다. 이전 대화도 다시 보내기 전에 마스킹한다(옛 체크포인트 대비).
    """
    prompts = scenario["prompts"]
    system = f"{prompts['common_rules.md'].strip()}\n\n{prompts['assistant.md'].strip()}"
    overhead = tokens.MESSAGE_OVERHEAD
    room = INPUT_TOKENS - tokens.REPLY_PRIMING - tokens.count(system) - overhead
    # runner가 이미 잘랐지만 그래프만 따로 부르는 경우에도 상한을 지킨다
    question = "\n\n[질문]\n" + tokens.truncate(state["prompt"], QUESTION_TOKENS)
    room -= tokens.count(question) + overhead
    block = tokens.truncate(_documents_block(state, scenario), max(room, 0))
    room -= tokens.count(block)
    last = HumanMessage(block + question)
    turns = [{**t, "content": mask(t["content"])} for t in state.get("history") or []]
    kept: list[dict[str, str]] = []
    for turn in reversed(turns):
        cost = tokens.count(turn["content"]) + overhead
        if cost > room:
            break
        room -= cost
        kept.insert(0, turn)
    folded = [t for t in turns[: len(turns) - len(kept)] if t["role"] == "user"]
    lines = [f"- {t['content'][:FOLD_CHARS]}" for t in folded]
    header = "\n\n[이전 대화 요약] 앞서 받은 질문(길이 때문에 접음)\n"
    while lines and tokens.count(header + "\n".join(lines)) > room:
        lines.pop(0)  # 요약도 넘치면 오래된 줄부터 버린다
    if lines:
        system += header + "\n".join(lines)
    messages: list[BaseMessage] = [SystemMessage(system)]
    for turn in kept:
        cls = HumanMessage if turn["role"] == "user" else AIMessage
        messages.append(cls(turn["content"]))
    messages.append(last)
    return messages


def _documents_block(state: AssistantState, scenario: dict[str, Any]) -> str:
    lines = [f"- [{r['title']}] {r['chunk'].strip()}" for r in state["results"]]
    block = "[문서 검색 결과]\n" + ("\n".join(lines) if lines else "(검색된 공개 문서 없음)")
    titles = guard_for(scenario).titles
    if state["not_released"]:
        names = ", ".join(titles.get(d, d) for d in state["not_released"])
        block += f"\n\n[아직 공유되지 않은 자료] {names}"
    return block


def _cite(guard: Guard, draft: str, allowed: set[str]) -> tuple[str, list[str]]:
    """본문을 guard로 거르고, 인용 문서를 allowed 안으로 좁혀 출처 줄을 다시 붙인다.

    인용은 본문의 정확한 `[문서 제목]`과 마지막 출처 줄의 제목만 센다(별칭이 지나가며 나온 것은
    인용이 아니다). 허용 집합 밖 문서의 `[제목]` 표시는 지운다(미공개·지어낸 인용 방지).
    """
    source = re.compile(guard.spec["citation"]["assistant_source_line"])
    lines = draft.strip().splitlines()
    tail = lines[-1].strip() if len(lines) > 1 else ""
    body = "\n".join(lines[:-1]) if source.match(tail) else draft.strip()
    for doc_id, title in guard.titles.items():
        if doc_id not in allowed:
            body = re.sub(rf"\s*\[{re.escape(title)}\]", "", body)
    body = guard.apply(body).text
    sources = set()
    if source.match(tail):
        sources = {t.strip() for t in tail.split(":", 1)[1].split(",")}
    cited = [
        d
        for d, title in guard.titles.items()
        if d in allowed and (f"[{title}]" in body or title in sources)
    ]
    if not cited:
        return body, []
    line = SOURCE_PREFIX + ", ".join(guard.titles[d] for d in cited)
    room = guard.max_chars - len(line) - 1
    return f"{body[:room].rstrip()}\n{line}", cited


def build_graph(checkpointer: BaseCheckpointSaver | None) -> CompiledStateGraph:
    builder = StateGraph(AssistantState, context_schema=AssistantDeps)
    builder.add_node("retrieve", retrieve)
    builder.add_node("answer", answer)
    builder.add_node("guard", guard_node)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "answer")
    builder.add_edge("answer", "guard")
    builder.add_edge("guard", END)
    return builder.compile(checkpointer=checkpointer)
