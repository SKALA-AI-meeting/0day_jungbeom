"""세션 그래프 노드: route, classify, respond(동료·팀장). 카드는 cards.py, 분업은 division.py,
관찰 창은 observing.py.

노드는 실행마다 바뀌는 의존성(LLM, MCP 연결, usage, 진행 알림, 세션 조회 결과)을 Runtime
context(RunDeps)로 받는다. 코드가 보장하는 답(모델 문구에 기대지 않음):
- 미공개 문서를 물으면 "아직 공유되지 않은 자료"(rag not_released 또는 질문이 미공개 문서 제목을
가리킴)
- 주담당이 보내지 않은 자기 파트를 물으면 "아직 못 봤어요, 보내 주시면 볼게요"
- 팀장에게 정답·판단을 물으면 "그건 주담당님이 정해 주세요"
- 진행 질문은 work_notes.progress로만 답한다(두 번 물어도 같은 답)
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END
from langgraph.runtime import Runtime
from langgraph.types import Command

from app.agent.guard import guard_for
from app.agent.llm import LLMUnavailable
from app.agent.mcp_client import PERSONA_TOOLS, error_code, fail, for_model
from app.agent.session import drafts, prompts, seq
from app.agent.session.classify import classify, saved
from app.agent.session.common import (
    SPEAKER_PREFIX,
    Outcome,
    RunDeps,
    already,
    board_and_shared,
    cards_by_id,
    my_parts,
    post,
    prepare,
    resumed,
    sent_this_run,
)
from app.agent.session.state import SessionState, defaults

__all__ = ["Outcome", "RunDeps", "route", "classify_node", "respond"]

log = logging.getLogger(__name__)

MAX_TOOL_CALLS = 3  # 응답당 모델 도구 호출(harness.md Tools)
SEARCH_TOP_K = 3
FALLBACK_TEXT = "잠시만요."  # LLM 재시도 실패(decisions.md 2026-10-20 Recovery)
BUDGET_TEXT = "지금은 대화를 더 이어가기 어려워요. 마감까지 기획안을 마무리해 주세요."
# 미공개 문서 고정 응답(common_rules.md 5절, grounding g05)
NOT_RELEASED_TEXT = "아직 공유되지 않은 자료예요."
UNSENT_TEXT = "아직 못 봤어요, 보내 주시면 볼게요."  # 보내지 않은 지원자 문서(context_leak)
REDIRECT_TEXT = "그건 주담당님이 정해 주세요."  # 팀장 판단 요청(manager_dm md03·md04)
NO_DIVISION_PROGRESS = "아직 분업이 안 정해져서 제 파트는 시작 전이에요."
DEFAULT_PROGRESS = "자료 보면서 잡기 시작한 단계"


def stimulus_keys(state: SessionState) -> list[str]:
    stimulus = state["stimulus"]
    if stimulus["type"] == "message":
        return [stimulus["message_id"]]
    if stimulus["type"] == "event":
        return list(stimulus["event_ids"])
    return [f"{stimulus['type']}:{state['run_id']}"]


async def route(
    state: SessionState, runtime: Runtime[RunDeps]
) -> Command[Literal["classify", "inject", "division", "close", "__end__"]]:
    """자극 종류로 갈 노드를 고른다. 이미 처리한 자극(재실행)이면 아무것도 하지 않는다."""
    deps = runtime.context
    update: dict[str, Any] = {
        k: v for k, v in defaults(state["session_id"]).items() if state.get(k) is None
    }
    handled = set(state.get("handled_stimuli") or [])
    if all(key in handled for key in stimulus_keys(state)):
        # 그래프는 끝났는데 실행 기록(finish_run) 전에 끊긴 재실행: 그 응답이 LLM 실패 폴백이었으면
        # 같은 결과를 돌려줘야 llm_failures가 한 번 센다(체크포인트의 표시로 복원, 생성 없음)
        if state["stimulus"]["type"] == "message":
            if fallback_key(state["stimulus"]["message_id"]) in handled:
                deps.outcome.fallback_used = deps.outcome.reply_fallback = True
        return Command(goto=END, update=update)

    prepared = await prepare(deps, state)
    if prepared is None:
        return Command(goto=END, update={**update, "last_error": deps.outcome.error})
    update.update(prepared)
    goto = {"message": "classify", "event": "inject", "division": "division", "end": "close"}
    return Command(goto=goto[state["stimulus"]["type"]], update=update)


def _candidate_message(state: SessionState) -> dict[str, Any] | None:
    message_id = state["stimulus"]["message_id"]
    return next((m for m in state["recent_messages"] if m["id"] == message_id), None)


def _fired_cards(deps: RunDeps, state: SessionState) -> list[dict[str, Any]]:
    cards = cards_by_id(state)
    seen, out = set(), []
    for event in deps.events():
        card = cards.get(event["card_id"])
        if event["status"] in ("fired", "done") and card and card.get("element"):
            if card["card_id"] not in seen:
                seen.add(card["card_id"])
                out.append(card)
    return out


def _doc_ref(reply: dict[str, Any] | None, shared: dict[str, Any] | None) -> dict[str, Any] | None:
    """reply_to_doc {doc_id, version} → 파트 번호·주인을 붙인다(보낸 문서에서 찾음)."""
    if not reply:
        return None
    for doc in (shared or {}).get("documents", []):
        if doc["doc_id"] == reply.get("doc_id"):
            return {**reply, "part_no": doc["part_no"], "owner": doc["owner"]}
    return dict(reply)


async def classify_node(
    state: SessionState, runtime: Runtime[RunDeps]
) -> Command[Literal["negotiate", "respond", "__end__"]]:
    """수신자·kind 분류 → meta.classification 저장 → 지시·답글을 작업 기억에 → negotiate|respond."""
    deps = runtime.context
    state, resume = await resumed(deps, state)
    message = _candidate_message(state)
    if message is None:
        deps.outcome.fail("message_not_found")
        return Command(goto=END, update={**resume, "last_error": deps.outcome.error})
    _, shared = await board_and_shared(deps)
    reply = _doc_ref(message.get("reply_to_doc"), shared)
    result, fallback = await classify(
        deps.llm_for("observe"),
        message["content"],
        message["channel"],
        state["scenario"],
        usage=deps.usage,
        trace=deps.trace(state, "classify"),
        current_card=state.get("current_card"),
        fired_cards=_fired_cards(deps, state),
        reply_to_doc=reply,
        report_requested=bool(state.get("report_requested")),
        use_llm=not deps.exhausted(state),
    )
    deps.outcome.fallback_used |= fallback
    stored = saved(result)
    if reply:
        stored["reply_to_doc"] = {
            "document_id": reply.get("doc_id"),
            "version": reply.get("version"),
        }
    await deps.store.save_classification(
        uuid.UUID(state["session_id"]), uuid.UUID(message["id"]), stored
    )
    notes = _remember(state, message, result, reply)
    stimulus = {
        **state["stimulus"],
        "classification": result,
        "channel": message["channel"],
        "reply_to_doc": reply,
    }
    update = {**resume, "stimulus": stimulus, "work_notes": notes}
    to_colleague = result["recipient"] == "colleague"
    early = state.get("phase") in ("kickoff", "division")
    # 되묻기(ask)는 분업 이야기일 때만 negotiate로. 질문(문서·사실)은 respond가 근거와 함께 답한다
    asks_division = result["decision"] == "ask" and result["kind"] != "question"
    decides = result["decision"] == "decide" and bool(result.get("parts"))
    if to_colleague and early and (decides or asks_division):
        return Command(goto="negotiate", update=update)
    reporting = state.get("phase") == "reporting"  # 제출 뒤: 변경 도구 없이 respond가 답한다
    if (
        to_colleague
        and result["kind"] == "redivide"
        and result.get("parts")
        and not early
        and not reporting
    ):
        return Command(goto="negotiate", update=update)
    return Command(goto="respond", update=update)


def _remember(
    state: SessionState,
    message: dict[str, Any],
    result: dict[str, Any],
    reply: dict[str, Any] | None,
) -> dict[str, Any]:
    """동료에게 한 지시(파트별, 같은 메시지·파트는 한 번)와 동료 문서 답글을 작업 기억에 더한다."""
    notes = dict(state["work_notes"])
    if result["recipient"] != "colleague":
        return notes
    instructions = list(notes.get("instructions") or [])
    if result["kind"] in ("instruction", "redivide", "doc_feedback") or result["instructions"]:
        for item in result["instructions"]:
            key = (message["id"], item.get("part_no"))
            if any((i.get("source_message_id"), i.get("part_no")) == key for i in instructions):
                continue
            instructions.append(
                {
                    "t_min": message.get("t_min"),
                    "text": item["text"],
                    "keywords": item.get("keywords") or [],
                    "part_no": item.get("part_no"),
                    "source_message_id": message["id"],
                }
            )
    notes["instructions"] = instructions
    if reply and reply.get("owner") == "colleague":
        feedback = list(notes.get("feedback") or [])
        if all(f.get("source_message_id") != message["id"] for f in feedback):
            feedback.append(
                {
                    "document_id": reply.get("doc_id"),
                    "version": reply.get("version"),
                    "part_no": reply.get("part_no"),
                    "text": message["content"],
                    "source_message_id": message["id"],
                }
            )
        notes["feedback"] = feedback
    return notes


def _respond_messages(
    state: SessionState,
    persona: str,
    message: dict[str, Any],
    board: dict[str, Any] | None,
    shared: dict[str, Any] | None,
    search: dict[str, Any] | None,
    unreleased: list[str],
    notes: list[str],
) -> list[BaseMessage]:
    scenario = state["scenario"]
    blocks = [prompts.board_block(scenario, state.get("division"), board, shared, persona)]
    if persona == "colleague":
        blocks.append(prompts.work_notes_block(state["work_notes"]))
        blocks.append(prompts.rules_block(scenario, state.get("current_card")))
    blocks.append(prompts.search_block(search, unreleased))
    blocks.append(
        prompts.recent_block(state["recent_messages"], scenario, persona, state.get("summary", ""))
    )
    channel = prompts.CHANNEL_NAME.get(message["channel"], message["channel"])
    me = prompts.names(scenario)[persona]
    tail = f"주담당이 방금 {channel}으로 보낸 마지막 메시지에 {me}(으)로 답한다."
    if notes:
        tail += " " + " ".join(notes)
    blocks.append(tail)
    return [
        SystemMessage(prompts.system_prompt(scenario, persona)),
        HumanMessage("\n\n".join(blocks)),
    ]


@dataclass
class LoopResult:
    text: str  # 빈 문자열이면 폴백
    limit_hit: bool = False
    budget_hit: bool = False
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
        if deps.exhausted(state):  # 앞 호출(도구 선택)로 예산이 바닥났으면 더 부르지 않는다
            return LoopResult("", budget_hit=True, not_released=not_released)
        offer = specs if calls < MAX_TOOL_CALLS else None
        reply = await deps.llm_for(persona).ainvoke(
            messages, usage=deps.usage, trace=trace, tools=offer
        )
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


def _prefix(text: str, fixed: str, pattern: str) -> str:
    """고정 문장이 응답에 없으면 앞에 붙인다(모델 문구에 기대지 않음)."""
    return text if pattern in "".join(text.split()) else f"{fixed} {text}".strip()


async def _unreleased_asked(deps: RunDeps, state: SessionState, question: str) -> list[str]:
    """질문이 미공개 회사 문서(제목·별칭)를 가리키면 그 제목들. 내용은 어디에도 넣지 않는다."""
    listed = await deps.code.call("list_documents")
    if not listed.get("ok"):
        return []
    guard = guard_for(state["scenario"])
    hidden = {d["doc_id"] for d in listed["data"] if not d.get("released")}
    return [guard.titles.get(d, d) for d in guard.cited_docs(question) if d in hidden]


def _candidate_sent(shared: dict[str, Any] | None, part_no: int) -> bool:
    return any(
        d["owner"] == "candidate" and d["part_no"] == part_no and d["versions"]
        for d in (shared or {}).get("documents", [])
    )


def _batchim(word: str) -> bool:
    last = word[-1] if word else ""
    return "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0


def progress_text(fragments: dict[int, str]) -> str:
    """진행 답 템플릿. 같은 progress면 언제나 같은 문장이 된다."""
    body = ", ".join(f"{no}번은 {frag}" for no, frag in sorted(fragments.items()))
    last = list(fragments.values())[-1] if fragments else ""
    return f"지금 {body}{'이에요' if _batchim(last) else '예요'}."


async def _progress_reply(
    deps: RunDeps, state: SessionState, part_no: int | None
) -> tuple[str, dict[str, Any]]:
    """진행 질문: work_notes.progress만 근거로 답하고, 처음 말하는 파트는 그 답을 progress에
    남긴다."""
    notes = dict(state["work_notes"])
    mine = my_parts(state.get("division"))
    if not mine:
        return NO_DIVISION_PROGRESS, notes
    targets = [part_no] if part_no in mine else mine
    progress = dict(notes.get("progress") or {})
    missing = [p for p in targets if str(p) not in progress]
    if missing and deps.exhausted(state):
        made = {}  # 예산 소진: 진행 기록은 규칙 문구로
    elif missing:
        try:
            ask = (
                "[진행 기록]\n자기 파트의 지금 진행 상태를 명사구 하나로 적는다(예: '사례 후보 "
                "추리는 중'). "
                'JSON만 출력: {"progress": {"<파트 번호>": "<명사구>"}}. 파트: '
                + ", ".join(f"{p}번" for p in missing)
            )
            reply = await deps.llm_for("colleague").ainvoke(
                [
                    SystemMessage(prompts.system_prompt(state["scenario"], "colleague")),
                    HumanMessage(prompts.work_notes_block(notes) + "\n\n" + ask),
                ],
                usage=deps.usage,
                trace=deps.trace(state, "progress"),
                json_mode=True,
                temperature=0,
            )
            made = json.loads(str(reply.content)).get("progress") or {}
        except (LLMUnavailable, ValueError, AttributeError):
            made, deps.outcome.fallback_used = {}, True
    for p in missing:
        value = str(made.get(str(p)) or "").strip().rstrip(".") or DEFAULT_PROGRESS
        progress[str(p)] = value[:40]
    notes["progress"] = progress
    return progress_text({p: progress[str(p)] for p in targets}), notes


async def _revise(
    deps: RunDeps, state: SessionState, reply: dict[str, Any], shared: dict[str, Any] | None
) -> tuple[dict[str, Any], str | None]:
    """완성본(v2 이상)에 매단 고쳐 달라는 답글 → 다음 버전을 보낸다(v3). 보낸 설명 문장을
    돌려준다."""
    notes = dict(state["work_notes"])
    part_no = reply.get("part_no")
    sent = dict(notes.get("sent") or {})
    done = sent_this_run(state, part_no)
    if done:  # 보낸 뒤 끊긴 재실행: 다시 쓰지 않고 보낸 버전으로 기억을 맞춘다
        number = done["shared_doc"]["version"]
    else:
        if part_no not in my_parts(state.get("division")) or sent.get(str(part_no), 0) < 2:
            return notes, None
        content = await drafts.write_part(
            deps, {**state, "work_notes": notes}, part_no, sent[str(part_no)] + 1, shared=shared
        )
        if content is None:
            return notes, None
        ok, number = await drafts.send_part(deps, state, part_no, content, None)
        if not ok:
            return notes, None
    sent[str(part_no)] = number
    notes["sent"] = sent
    notes["progress"] = {**(notes.get("progress") or {}), str(part_no): f"v{number}까지 보낸 상태"}
    return notes, f"방금 답글을 반영한 {part_no}번 v{number}을 보냈다고 짧게 알린다."


LLM_FALLBACKS = (
    "llm_unavailable",
    "tool_call_limit",
)  # reply_fallback으로 세는 폴백(예산 안내 제외)


def fallback_key(message_id: str) -> str:
    """handled_stimuli에 남기는 표시: 이 메시지의 응답이 LLM 실패 폴백이었다."""
    return f"reply_fallback:{message_id}"


def _restore(
    deps: RunDeps, state: SessionState, saved: dict[str, Any], persona: str
) -> dict[str, Any]:
    """응답까지 저장된 뒤 체크포인트 전에 끊긴 재실행. 생성 없이 그 실행이 남겼어야 할 것을 맞춘다:
    답글 반영 버전(v3)의 sent·progress, 저장된 응답이 LLM 실패 폴백이었는지(llm_failures 집계)."""
    update: dict[str, Any] = {"seq": saved.get("slot") or seq.RESPOND}
    handled = [*state.get("handled_stimuli", []), state["stimulus"]["message_id"]]
    if saved.get("fallback") in LLM_FALLBACKS:
        deps.outcome.fallback_used = deps.outcome.reply_fallback = True
        handled.append(fallback_key(state["stimulus"]["message_id"]))
    update["handled_stimuli"] = handled
    reply = state["stimulus"].get("reply_to_doc") or {}
    done = sent_this_run(state, reply.get("part_no")) if persona == "colleague" else None
    if done:
        notes = dict(state["work_notes"])
        number, key = done["shared_doc"]["version"], str(reply["part_no"])
        notes["sent"] = {**(notes.get("sent") or {}), key: number}
        notes["progress"] = {**(notes.get("progress") or {}), key: f"v{number}까지 보낸 상태"}
        update["work_notes"] = notes
    return update


async def respond(state: SessionState, runtime: Runtime[RunDeps]) -> dict[str, Any]:
    """컨텍스트 조립 → rag 검색 → 응답 생성(도구 루프) → 코드 보장 문장 → guard → post_message.

    팀장(respond_manager)도 같은 노드다. 페르소나별 허용 도구·채널만 다르다.
    """
    deps = runtime.context
    state, resume = await resumed(deps, state)
    stimulus = state["stimulus"]
    message = _candidate_message(state)
    handled = [*state.get("handled_stimuli", []), stimulus["message_id"]]
    if message is None or "classification" not in stimulus:
        deps.outcome.fail(deps.outcome.error or "message_not_found")
        return {"last_error": deps.outcome.error}
    cls = stimulus["classification"]
    persona = cls["recipient"]
    # 멱등: 이 run_id의 응답이 이미 저장됐으면(체크포인트 전에 죽은 재실행) 생성 없이 끝낸다
    saved_reply = already(state, seq.RESPOND) or already(state, seq.FALLBACK)
    if saved_reply:
        return _restore(deps, state, saved_reply, persona)

    await deps.progress(persona, "respond", "started", None)
    used_before = deps.usage.tool_calls
    slot, error, update = seq.RESPOND, None, dict(resume)
    board, shared = await board_and_shared(deps)
    reply_doc = stimulus.get("reply_to_doc")
    notes: list[str] = []
    if deps.exhausted(state):
        text, slot, error = BUDGET_TEXT, seq.FALLBACK, "token_budget_exhausted"
    elif persona == "colleague" and cls["kind"] == "progress_query":
        text, work_notes = await _progress_reply(deps, state, cls.get("part_no"))
        update["work_notes"] = work_notes
    else:
        if persona == "colleague" and reply_doc and cls.get("wants_revision"):
            if state.get("phase") != "reporting":  # 제출 뒤에는 문서를 바꾸지 않는다(api 409)
                work_notes, note = await _revise(deps, state, reply_doc, shared)
                update["work_notes"] = work_notes
                if note:
                    notes.append(note)
                else:
                    notes.append("답글은 다음 버전(완성본)에 반영하겠다고 한다.")
        # 미공개 문서를 "묻는" 질문만(지연 소식을 전하는 말에 고정 문장을 붙이지 않는다)
        unreleased = (
            await _unreleased_asked(deps, state, message["content"])
            if cls["kind"] == "question"
            else []
        )
        await deps.progress(persona, "respond", "tool_start", "search_documents")
        search = await deps.code.call(
            "search_documents", {"query": message["content"], "top_k": SEARCH_TOP_K}
        )
        await deps.progress(persona, "respond", "tool_end", "search_documents")
        if cls["kind"] == "redivide" and state.get("phase") == "reporting":
            notes.append("이미 제출해서 분담은 바꾸지 않는다고 짧게 답한다.")
        if cls["kind"] == "report" and persona == "manager":
            notes.append(
                "주담당의 보고다. 받았다는 확인과 업무 코멘트 하나로 답하고 판정하지 않는다."
            )
        llm_messages = _respond_messages(
            {**state, **update}, persona, message, board, shared, search, unreleased, notes
        )
        try:
            loop = await _tool_loop(deps, state, persona, llm_messages)
        except LLMUnavailable:
            loop = LoopResult("")
        text = SPEAKER_PREFIX.sub("", loop.text).strip()
        if not text and loop.budget_hit:
            text, slot, error = BUDGET_TEXT, seq.FALLBACK, "token_budget_exhausted"
        elif not text:
            error = "tool_call_limit" if loop.limit_hit else "llm_unavailable"
            text, slot = FALLBACK_TEXT, seq.FALLBACK
            deps.outcome.fallback_used = deps.outcome.reply_fallback = True
        else:
            titles = guard_for(state["scenario"]).titles
            hidden = list(
                dict.fromkeys([*(titles.get(d, d) for d in loop.not_released), *unreleased])
            )
            if hidden:
                text = _prefix(
                    text, f"{', '.join(hidden)} 문서는 {NOT_RELEASED_TEXT}", "아직공유되지않은자료"
                )
            asked = cls.get("asks_my_part")
            if asked and not _candidate_sent(shared, asked):
                text = _prefix(text, UNSENT_TEXT, "아직못봤어요")
            if persona == "manager" and cls.get("judgment_request"):
                text = _prefix(text, REDIRECT_TEXT, "주담당님이정해")

    guard = guard_for(state["scenario"])
    guarded = guard.apply(text)
    usage = deps.usage
    meta = {
        "tokens_in": usage.tokens_in,
        "tokens_out": usage.tokens_out,
        "latency_ms": usage.latency_ms,
        "llm_calls": usage.llm_calls,
        "tool_calls": usage.tool_calls,
        "cited_docs": guard.cited_docs(guarded.text),
        "guard_hits": list(guarded.hits),
        "fallback": error,
    }
    ok = await post(
        deps,
        state,
        channel=message["channel"],
        sender=persona,
        content=guarded.text,
        slot=slot,
        node="respond",
        meta=meta,
    )
    if not ok:
        await deps.progress(persona, "respond", "failed", None)
        return {
            **update,
            "last_error": deps.outcome.error,
        }
    await deps.progress(persona, "respond", "finished", None)
    if error in LLM_FALLBACKS:
        handled.append(fallback_key(stimulus["message_id"]))
    return {
        **update,
        "handled_stimuli": handled,
        "seq": slot,
        "tool_calls_used": state.get("tool_calls_used", 0) + usage.tool_calls - used_before,
        "last_error": error,
    }


async def account(state: SessionState, runtime: Runtime[RunDeps]) -> dict[str, Any]:
    """실행 끝: 이번 실행의 모든 LLM 사용량(분류·페르소나·문서·관찰, 재시도 포함)을 세션 예산에서
    뺀다."""
    return {"token_budget_left": max(0, runtime.context.budget_left(state))}
