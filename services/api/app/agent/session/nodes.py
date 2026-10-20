"""세션 그래프 노드(agent-min: route, classify, respond, inject 최소, close).

전이표 전체·negotiate·observe·draft·review는 M2(agent-session)에서 더한다. 노드는 실행마다 바뀌는
의존성(LLM, MCP 연결, usage, 진행 알림)을 Runtime context(RunDeps)로 받는다.
"""

import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END
from langgraph.runtime import Runtime
from langgraph.types import Command

from app.agent.guard import guard_for
from app.agent.llm import BaseLLM, LLMUnavailable, Trace, Usage
from app.agent.mcp_client import (
    PERSONA_TOOLS,
    SESSION_CODE_TOOLS,
    McpClient,
    ToolScope,
    error_code,
    fail,
    for_model,
)
from app.agent.session import prompts, seq
from app.agent.session.classify import classify
from app.agent.session.state import SessionState, defaults
from app.agent.session.store import AgentStore

log = logging.getLogger(__name__)

MAX_TOOL_CALLS = 3  # 응답당 모델 도구 호출(harness.md Tools)
SEARCH_TOP_K = 3
PAGE = 50  # list_messages 한 번에(계약 상한)
MAX_PAGES = 5
RECENT_KEEP = 80  # State에 남기는 최근 메시지(페르소나별로 다시 30개로 거른다)
PERSONA_CHANNELS = ("team", "dm")  # notice·assistant는 State에도 넣지 않는다
FALLBACK_TEXT = "잠시만요."  # LLM 재시도 실패(decisions.md 2026-10-20 Recovery)
BUDGET_TEXT = "지금은 대화를 더 이어가기 어려워요. 마감까지 기획안을 마무리해 주세요."
# 미공개 문서 고정 응답(common_rules.md 5절, grounding g05)
NOT_RELEASED_TEXT = "아직 공유되지 않은 자료예요."
NOT_RELEASED_PATTERN = re.compile(r"아직\s*공유되지\s*않은\s*자료")
# 시나리오에서 State에 담지 않는 큰 값(회사 문서 본문은 rag-mcp가 가진다)
SCENARIO_SKIP = ("documents",)

Progress = Callable[[str, str, str, str | None], Awaitable[None]]


@dataclass
class Outcome:
    ok: bool = True
    fallback_used: bool = False
    error: str | None = None

    def fail(self, error: str) -> None:
        self.ok = False
        self.error = self.error or error


@dataclass
class RunDeps:
    llm: BaseLLM
    mcp: McpClient
    store: AgentStore
    usage: Usage
    progress: Progress
    outcome: Outcome = field(default_factory=Outcome)

    def trace(self, state: SessionState, node: str) -> Trace:
        return Trace(state["run_id"], state["session_id"], node)

    @property
    def code(self) -> ToolScope:
        """결정적 노드가 코드로 부르는 도구."""
        return self.mcp.scope(SESSION_CODE_TOOLS)


def stimulus_keys(state: SessionState) -> list[str]:
    stimulus = state["stimulus"]
    if stimulus["type"] == "message":
        return [stimulus["message_id"]]
    if stimulus["type"] == "event":
        return list(stimulus["event_ids"])
    return [f"end:{state['run_id']}"]


def _slim(message: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "channel", "sender", "content", "t_min", "run_id", "event_id")
    return {k: message.get(k) for k in keys}


async def _refresh_messages(
    code: ToolScope, recent: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], str | None]:
    """마지막으로 본 시각부터 이어 읽어 State의 최근 메시지를 갱신한다(조회 상한 50개씩)."""
    merged = list(recent)
    known = {m["id"] for m in merged}
    last = merged[-1]["t_min"] if merged and merged[-1].get("t_min") is not None else None
    # t_min은 0.01분 단위라 경계의 메시지를 놓치지 않게 조금 앞에서 읽고 id로 중복을 거른다
    since = None if last is None else last - 0.02
    for _ in range(MAX_PAGES):
        result = await code.call("list_messages", {"since_t_min": since, "limit": PAGE})
        if not result.get("ok"):
            return merged[-RECENT_KEEP:], error_code(result)
        page = result["data"]
        for message in page:
            if message["id"] not in known and message["channel"] in PERSONA_CHANNELS:
                merged.append(_slim(message))
                known.add(message["id"])
        if len(page) < PAGE:
            break
        since = page[-1]["t_min"] - 0.02
    return merged[-RECENT_KEEP:], None


async def route(
    state: SessionState, runtime: Runtime[RunDeps]
) -> Command[Literal["classify", "inject", "close", "__end__"]]:
    """자극 종류로 갈 노드를 고른다. 이미 처리한 자극(재실행)이면 아무것도 하지 않는다."""
    deps = runtime.context
    update: dict[str, Any] = {
        k: v for k, v in defaults(state["session_id"]).items() if state.get(k) is None
    }
    handled = set(state.get("handled_stimuli") or [])
    if all(key in handled for key in stimulus_keys(state)):
        return Command(goto=END, update=update)

    session = await deps.code.call("get_session")
    if not session.get("ok"):
        deps.outcome.fail(f"get_session:{error_code(session)}")
        return Command(goto=END, update={**update, "last_error": deps.outcome.error})
    if state.get("scenario") is None:
        scenario = session["data"]["position"]["scenario"]
        update["scenario"] = {k: v for k, v in scenario.items() if k not in SCENARIO_SKIP}
    update["division"] = session["data"].get("division")

    recent, error = await _refresh_messages(deps.code, state.get("recent_messages") or [])
    update["recent_messages"] = recent
    if error:
        deps.outcome.fail(f"list_messages:{error}")
        return Command(goto=END, update={**update, "last_error": deps.outcome.error})
    goto = {"message": "classify", "event": "inject", "end": "close"}[state["stimulus"]["type"]]
    return Command(goto=goto, update=update)


def _candidate_message(state: SessionState) -> dict[str, Any] | None:
    message_id = state["stimulus"]["message_id"]
    return next((m for m in state["recent_messages"] if m["id"] == message_id), None)


async def classify_node(state: SessionState, runtime: Runtime[RunDeps]) -> dict[str, Any]:
    """수신자·kind 분류 → meta.classification 저장 → 지시면 작업 기억에 추가."""
    deps = runtime.context
    message = _candidate_message(state)
    if message is None:
        deps.outcome.fail("message_not_found")
        return {"last_error": deps.outcome.error}
    result, fallback = await classify(
        deps.llm,
        message["content"],
        message["channel"],
        state["scenario"],
        usage=deps.usage,
        trace=deps.trace(state, "classify"),
        current_element=state.get("current_element"),
    )
    deps.outcome.fallback_used |= fallback
    part_no = result.pop("part_no", None)
    await deps.store.save_classification(
        uuid.UUID(state["session_id"]), uuid.UUID(message["id"]), result
    )
    work_notes = dict(state["work_notes"])
    instructions = list(work_notes.get("instructions") or [])
    recipient_is_colleague = result["recipient"] == "colleague"
    if recipient_is_colleague and result["kind"] in ("instruction", "redivide"):
        if all(i.get("source_message_id") != message["id"] for i in instructions):
            instructions.append(
                {
                    "t_min": message.get("t_min"),
                    "text": result.get("instruction") or message["content"],
                    "part_no": part_no,
                    "source_message_id": message["id"],
                }
            )
    work_notes["instructions"] = instructions
    stimulus = {**state["stimulus"], "classification": result}
    return {"stimulus": stimulus, "work_notes": work_notes}


def _respond_messages(
    state: SessionState,
    persona: str,
    message: dict[str, Any],
    board: dict[str, Any],
    document: dict[str, Any],
    search: dict[str, Any] | None,
) -> list[BaseMessage]:
    scenario = state["scenario"]
    blocks = [
        prompts.board_block(
            scenario,
            state.get("division"),
            board["data"] if board.get("ok") else None,
            document["data"] if document.get("ok") else None,
        )
    ]
    if persona == "colleague":
        blocks.append(prompts.work_notes_block(state["work_notes"]))
        blocks.append(prompts.search_block(search))
    blocks.append(
        prompts.recent_block(state["recent_messages"], scenario, persona, state.get("summary", ""))
    )
    channel = prompts.CHANNEL_NAME.get(message["channel"], message["channel"])
    me = prompts.names(scenario)[persona]
    blocks.append(f"리드가 방금 {channel}으로 보낸 마지막 메시지에 {me}(으)로 답한다.")
    return [
        SystemMessage(prompts.system_prompt(scenario, persona)),
        HumanMessage("\n\n".join(blocks)),
    ]


@dataclass
class LoopResult:
    text: str  # 빈 문자열이면 폴백
    limit_hit: bool = False
    not_released: list[str] = field(default_factory=list)  # 공개 전이라 거절된 doc_id


async def _tool_loop(
    deps: RunDeps, state: SessionState, persona: str, messages: list[BaseMessage]
) -> LoopResult:
    """모델이 페르소나 허용 도구를 최대 3회 고른 뒤 답한다.

    상한을 넘겨 다시 도구를 고르면 루프를 끝내고 폴백으로 간다(빈 text, limit_hit).
    """
    tools = deps.mcp.scope(PERSONA_TOOLS[persona])
    specs = await tools.specs()
    trace = deps.trace(state, "respond")
    calls = 0
    not_released: list[str] = []
    for _ in range(MAX_TOOL_CALLS + 1):
        offer = specs if calls < MAX_TOOL_CALLS else None
        reply = await deps.llm.ainvoke(messages, usage=deps.usage, trace=trace, tools=offer)
        messages.append(reply)
        if not reply.tool_calls:
            return LoopResult(str(reply.content or "").strip(), not_released=not_released)
        if calls >= MAX_TOOL_CALLS:
            break
        for tool_call in reply.tool_calls:
            if calls >= MAX_TOOL_CALLS:
                result = fail("limit_exceeded", "tool call limit reached for this reply")
            else:
                calls += 1
                deps.usage.tool_calls += 1
                name, args = tool_call["name"], tool_call.get("args") or {}
                await deps.progress(persona, "respond", "tool_start", name)
                result = await tools.call(name, args)
                await deps.progress(persona, "respond", "tool_end", name)
                if error_code(result) == "not_released" and args.get("doc_id"):
                    not_released.append(str(args["doc_id"]))
            messages.append(ToolMessage(for_model(result), tool_call_id=tool_call["id"]))
    return LoopResult("", limit_hit=True, not_released=not_released)


def _with_not_released(text: str, doc_ids: list[str], titles: dict[str, str]) -> str:
    """rag가 not_released를 돌려준 문서는 코드가 고정 문장을 넣는다(LLM 문구에 기대지 않음)."""
    if not doc_ids or NOT_RELEASED_PATTERN.search(text):
        return text
    names = ", ".join(dict.fromkeys(titles.get(d, d) for d in doc_ids))
    return f"{names} 문서는 {NOT_RELEASED_TEXT} {text}".strip()


async def respond(state: SessionState, runtime: Runtime[RunDeps]) -> dict[str, Any]:
    """컨텍스트 조립 → rag 검색 → 응답 생성(도구 루프) → guard → post_message."""
    deps = runtime.context
    stimulus = state["stimulus"]
    message = _candidate_message(state)
    handled = [*state.get("handled_stimuli", []), stimulus["message_id"]]
    if message is None or "classification" not in stimulus:
        deps.outcome.fail(deps.outcome.error or "message_not_found")
        return {"last_error": deps.outcome.error}
    persona = stimulus["classification"]["recipient"]
    # 멱등: 이 run_id의 응답이 이미 저장됐으면(체크포인트 전에 죽은 재실행) 생성 없이 끝낸다
    run_id = state["run_id"]
    if any(
        m.get("run_id") == run_id and m["sender"] != "candidate" for m in state["recent_messages"]
    ):
        return {"handled_stimuli": handled, "seq": seq.RESPOND}

    await deps.progress(persona, "respond", "started", None)
    used_before = deps.usage.tool_calls
    slot, error = seq.RESPOND, None
    if state["token_budget_left"] - deps.usage.tokens <= 0:
        text, slot, error = BUDGET_TEXT, seq.FALLBACK, "token_budget_exhausted"
    else:
        board = await deps.code.call("get_board")
        document = await deps.code.call("get_document_state")
        search = None
        if persona == "colleague":
            await deps.progress(persona, "respond", "tool_start", "search_documents")
            search = await deps.code.call(
                "search_documents", {"query": message["content"], "top_k": SEARCH_TOP_K}
            )
            await deps.progress(persona, "respond", "tool_end", "search_documents")
        llm_messages = _respond_messages(state, persona, message, board, document, search)
        try:
            loop = await _tool_loop(deps, state, persona, llm_messages)
        except LLMUnavailable:
            loop = LoopResult("")
        text = loop.text
        if not text:
            error = "tool_call_limit" if loop.limit_hit else "llm_unavailable"
            text, slot = FALLBACK_TEXT, seq.FALLBACK
            deps.outcome.fallback_used = True
        text = _with_not_released(text, loop.not_released, guard_for(state["scenario"]).titles)

    guard = guard_for(state["scenario"])
    guarded = guard.apply(text)
    usage = deps.usage
    meta = {
        "model": deps.llm.model,
        "node": "respond",
        "tokens_in": usage.tokens_in,
        "tokens_out": usage.tokens_out,
        "latency_ms": usage.latency_ms,
        "llm_calls": usage.llm_calls,
        "tool_calls": usage.tool_calls,
        "cited_docs": guard.cited_docs(guarded.text),
        "guard_hits": list(guarded.hits),
        "fallback": error,
    }
    posted = await deps.code.call(
        "post_message",
        {
            "channel": message["channel"],
            "sender": persona,
            "content": guarded.text,
            "run_id": run_id,
            "seq": slot,
            "meta": meta,
        },
    )
    if not posted.get("ok"):
        deps.outcome.fail(f"post_message:{error_code(posted)}")
        await deps.progress(persona, "respond", "failed", None)
        return {"last_error": deps.outcome.error, "token_budget_left": _budget(state, deps)}
    await deps.progress(persona, "respond", "finished", None)
    return {
        "handled_stimuli": handled,
        "seq": slot,
        "tool_calls_used": state.get("tool_calls_used", 0) + usage.tool_calls - used_before,
        "token_budget_left": _budget(state, deps),
        "last_error": error,
    }


def _budget(state: SessionState, deps: RunDeps) -> int:
    return max(0, state["token_budget_left"] - deps.usage.tokens)


async def inject(state: SessionState, runtime: Runtime[RunDeps]) -> dict[str, Any]:
    """카드 실행 최소판. system은 text 그대로, colleague·manager는 brief로 생성한다.

    카드마다 event_id를 단 메시지 1건.

    전이(분업 확정·phase)·observe·draft·review는 M2에서 한다.
    """
    deps = runtime.context
    scenario = state["scenario"]
    session_id = uuid.UUID(state["session_id"])
    event_ids = list(state["stimulus"]["event_ids"])
    card_ids = await deps.store.event_cards(session_id, [uuid.UUID(e) for e in event_ids])
    cards = {c["card_id"]: c for c in scenario["cards"]}
    handled = list(state.get("handled_stimuli", []))
    posted_events = {m.get("event_id") for m in state["recent_messages"]}
    guard = guard_for(scenario)
    for index, event_id in enumerate(event_ids):
        if event_id in handled:
            continue
        if event_id in posted_events:  # 저장 뒤 체크포인트 전에 죽은 재실행
            handled.append(event_id)
            continue
        card = cards.get(card_ids.get(uuid.UUID(event_id), ""))
        if card is None:
            deps.outcome.fail(f"card_not_found:{event_id}")
            continue
        actor = card.get("actor", "system")
        if actor == "system":
            text = card.get("text") or card.get("brief") or ""
        else:
            await deps.progress(actor, "inject", "started", None)
            try:
                text = await _card_text(deps, state, card, actor)
            except LLMUnavailable:
                deps.outcome.fail(f"llm_unavailable:{card['card_id']}")
                await deps.progress(actor, "inject", "failed", None)
                continue
            text = guard.apply(text).text
        posted = await deps.code.call(
            "post_message",
            {
                "channel": card.get("channel", "team"),
                "sender": actor,
                "content": text,
                "event_id": event_id,
                "run_id": state["run_id"],
                "seq": seq.INJECT + index,
                "meta": {"model": deps.llm.model, "node": "inject", "card_id": card["card_id"]},
            },
        )
        if not posted.get("ok"):
            deps.outcome.fail(f"post_message:{error_code(posted)}")
            continue
        handled.append(event_id)
        if actor != "system":
            await deps.progress(actor, "inject", "finished", None)
    return {"handled_stimuli": handled, "seq": seq.INJECT, "last_error": deps.outcome.error}


async def _card_text(deps: RunDeps, state: SessionState, card: dict[str, Any], actor: str) -> str:
    scenario = state["scenario"]
    brief = prompts.fill_brief(card.get("brief") or "", scenario, state.get("division"))
    if card.get("texture") and state.get("division") is None:
        brief += " (분업이 아직 정해지지 않아 초안은 쓰지 않았다. 쓴 것처럼 말하지 않는다)"
    blocks = [prompts.card_block(card, brief)]
    if actor == "colleague":
        blocks.append(prompts.work_notes_block(state["work_notes"]))
    blocks.append(
        prompts.recent_block(state["recent_messages"], scenario, actor, state.get("summary", ""))
    )
    reply = await deps.llm.ainvoke(
        [SystemMessage(prompts.system_prompt(scenario, actor)), HumanMessage("\n\n".join(blocks))],
        usage=deps.usage,
        trace=deps.trace(state, "inject"),
    )
    text = str(reply.content or "").strip()
    if not text:  # brief(지시문)를 그대로 내보내지 않는다. 카드 실패로 재실행
        raise LLMUnavailable("empty card text")
    return text


async def close(state: SessionState, runtime: Runtime[RunDeps]) -> dict[str, Any]:
    """종료 자극. 열린 창 닫기(observe)는 M2. 지금은 phase만 done으로."""
    handled = [*state.get("handled_stimuli", []), *stimulus_keys(state)]
    return {"handled_stimuli": handled, "phase": "done"}
