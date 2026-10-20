"""카드 실행(inject). 같은 due_at 묶음을 카드 순서로 실행하고, 카드마다 자기 event_id 메시지를
최소 1건 만든다(그래야 api가 그 행을 done으로 본다).

| 카드 | 하는 일 |
|---|---|
| kickoff | 팀장 브리프(team) + 동료 인사(dm) |
| planning_division·division | 분업을 묻는다(이미 확정이면 확인만). phase division |
| collab_help·responsibility_delay·adaptability_change | 카드 메시지 하나(system은 text 그대로) |
| planning_checkin·midpoint_draft | 동료 파트 초안 v1(같이 파트는 골격) send_document + 진행을 묻는
공유 메시지 |
| review | 완성본 v2 send_document + 보드 done + 공유 메시지 |
| collab_disagree | 대상 규칙으로 문장을 고르고 카탈로그 고정 의견을 그대로 전한다 |
| honesty_report·report_request | 팀장 보고 요청 + "제출하면 종료" 시스템 줄. report_requested=true
|

중간 카드·리뷰가 왔는데 분업이 미확정이면 기본안으로 먼저 확정한다(division.default_division).
문서를 끝내 못 보내면 공유 메시지를 올리지 않고 RunResult.error를 DOCUMENT_MISSING으로 남겨 카드
실패(최초 포함 3회) 규칙을 탄다.
"""

import logging
import re
from collections.abc import Callable
from typing import Any

from langgraph.runtime import Runtime

from app.agent.llm import LLMUnavailable
from app.agent.mcp_client import error_code
from app.agent.runner import DOCUMENT_MISSING
from app.agent.session import drafts, prompts, seq
from app.agent.session.common import (
    BudgetExhausted,
    RunDeps,
    already,
    board_and_shared,
    cards_by_id,
    compose,
    context_blocks,
    my_parts,
    post,
    resumed,
    sent_this_run,
)
from app.agent.session.division import confirm_division, default_division
from app.agent.session.state import SessionState

log = logging.getLogger(__name__)

MIDDLE = ("collab_help", "planning_checkin", "responsibility_delay", "adaptability_change")
DEFAULT_BEFORE = (*MIDDLE, "review", "collab_disagree")
PHASE_AFTER = {
    "collab_help": "work",
    "planning_checkin": "checkin",
    "midpoint_draft": "checkin",
    "responsibility_delay": "checkin",
    "adaptability_change": "checkin",
    "review": "review",
    "collab_disagree": "review",
}
# 반대 의견 대상 ①: 주담당 1번 문서에서 원인 가정을 말한 문장
CAUSE = re.compile(r"원인|가정|때문|놓쳐|놓치|어색|아는\s*사람|관계")
RELATIONSHIP = re.compile(r"관계|아는\s*사람|어색")
SENTENCE = re.compile(r"[^.!?。\n]+[.!?。]?")
MIN_TARGET_CHARS = 50


class CardFailed(Exception):
    """카드를 이번 시도에서 끝내지 못함. outcome에 이유가 남아 있다."""


async def inject(state: SessionState, runtime: Runtime[RunDeps]) -> dict[str, Any]:
    deps = runtime.context
    state, update = await resumed(deps, state)
    event_ids = list(state["stimulus"]["event_ids"])
    cards = cards_by_id(state)
    handled = list(state.get("handled_stimuli", []))
    injected: list[str] = []  # 이번 시도에서 카드 실행을 마친 행. 처리 완료 확정은 observe가 한다
    current = dict(state)
    for index, event_id in enumerate(event_ids):
        if event_id in handled:
            continue
        event = deps.event(event_id)
        card = cards.get(event["card_id"]) if event else None
        if card is None:
            deps.outcome.fail(f"card_not_found:{event_id}")
            continue
        current = {**current, **update}
        try:
            changes = await _run_card(deps, current, card, event, seq.INJECT + index)
        except CardFailed:
            await deps.progress(card.get("actor", "system"), "inject", "failed", None)
            break  # 같은 묶음의 뒤 카드(collab_disagree)는 앞 카드가 끝난 뒤에 실행한다
        update.update(changes)
        injected.append(event_id)
    return {
        **update,
        "stimulus": {**state["stimulus"], "injected": injected},
        "seq": seq.INJECT,
        "last_error": deps.outcome.error,
    }


async def _run_card(
    deps: RunDeps, state: SessionState, card: dict[str, Any], event: dict[str, Any], slot: int
) -> dict[str, Any]:
    card_id = card["card_id"]
    update: dict[str, Any] = {}
    if card_id in DEFAULT_BEFORE:
        update = await default_division(deps, state) or {}
        if not deps.outcome.ok:
            raise CardFailed
        state = {**state, **update}
    elif state.get("division") and not state["work_notes"].get("parts"):
        # 보드 확정 자극을 놓쳤어도 카드 전에 작업 기억을 맞춘다(메시지 없이)
        notes = await confirm_division(deps, state, state["division"])
        state = {**state, "work_notes": notes}
        update["work_notes"] = notes

    actor = card.get("actor", "system")
    await deps.progress(actor, "inject", "started", None)
    if card_id == "kickoff":
        changes = await _kickoff(deps, state, card, event)
    elif card_id in ("planning_division", "division"):
        changes = await _ask_division(deps, state, card, event, slot)
    elif card_id in ("planning_checkin", "midpoint_draft"):
        changes = await _checkin(deps, state, card, event, slot)
    elif card_id == "review":
        changes = await _review(deps, state, card, event, slot)
    elif card_id == "collab_disagree":
        changes = await _disagree(deps, state, card, event, slot)
    elif card_id in ("honesty_report", "report_request"):
        changes = await _request_report(deps, state, card, event, slot)
    else:
        await _message(deps, state, card, event, slot)
        changes = {}
    if card_id in PHASE_AFTER:
        changes.setdefault("phase", PHASE_AFTER[card_id])
    await deps.progress(actor, "inject", "finished", None)
    return {**update, **changes}


async def _text(
    deps: RunDeps,
    state: SessionState,
    card: dict[str, Any],
    persona: str,
    extra: list[str] | None = None,
    brief: str | None = None,
    rule: str | None = None,
) -> str:
    """카드 brief로 페르소나 문장 생성. 실패하면 카드 실패(빈 문장·지시문을 내보내지 않는다)."""
    scenario = state["scenario"]
    filled = prompts.fill_brief(brief or card.get("brief") or "", scenario, state.get("division"))
    try:
        blocks = await context_blocks(deps, state, persona, state.get("division"))
        return await compose(
            deps,
            state,
            persona,
            [*blocks, prompts.card_block(card, filled, extra)],
            node="inject",
        )
    except BudgetExhausted:
        # 세션 예산 소진: 카드는 brief 없이 규칙 문장으로 계속 발행한다(harness Agent Loop)
        return rule or rule_text(card, scenario, state.get("division"), filled)
    except LLMUnavailable as exc:
        deps.outcome.fail(f"llm_unavailable:{card['card_id']}")
        raise CardFailed from exc


QUOTED = re.compile(r"[\"“]([^\"”]{4,})[\"”]")


def rule_text(
    card: dict[str, Any], scenario: dict[str, Any], division: dict | None, brief: str
) -> str:
    """LLM 없이 카드를 전하는 규칙 문장. brief 안의 따옴표 문장(카드가 그대로 전할 말)을 잇고,
    없으면 카드 종류별 최소 문장. 미션 내용은 카탈로그 값에서만 가져온다."""
    card_id = card["card_id"]
    quotes = QUOTED.findall(brief)
    if card_id == "kickoff":
        length = (scenario.get("final_template") or {}).get("length", "")
        colleague = prompts.names(scenario)["colleague"]
        return (
            f"{scenario.get('name', '이번 과제')}를 시작합니다. 결과물은 최종본 하나({length})이고 "
            f"마감은 세션 끝이에요. 오늘 합류하신 분이 주담당으로 {colleague}님과 함께 정리해 "
            f"주세요."
        )
    if card_id in ("planning_division", "division"):
        if division:
            return "정해 주신 대로 진행할게요."
        hint = f" {quotes[0]}" if quotes else ""
        return f"기획안 파트를 어떻게 나눌지 정해 주세요.{hint}"
    if card_id in ("honesty_report", "report_request"):
        return "주담당님, 팀 결과(누가 무엇을 맡았고 어디까지 됐는지)를 보고해 주세요. " + (
            quotes[0] if quotes else ""
        )
    if quotes:
        return " ".join(quotes)
    return "확인 부탁드려요."


async def _card_post(
    deps: RunDeps,
    state: SessionState,
    card: dict[str, Any],
    event: dict[str, Any],
    slot: int,
    persona: str,
    *,
    channel: str | None = None,
    extra: list[str] | None = None,
    brief: str | None = None,
    text: str | None = None,
    rule: str | None = None,
) -> None:
    if already(state, slot):
        return
    if text is None:
        text = await _text(deps, state, card, persona, extra, brief, rule)
    ok = await post(
        deps,
        state,
        channel=channel or card.get("channel", "team"),
        sender=persona,
        content=text,
        slot=slot,
        node="inject",
        event_id=event["id"],
        meta={"card_id": card["card_id"]},
    )
    if not ok:
        raise CardFailed


async def _message(
    deps: RunDeps, state: SessionState, card: dict[str, Any], event: dict[str, Any], slot: int
) -> None:
    actor = card.get("actor", "system")
    if actor == "system":
        text = prompts.fill_brief(card.get("text") or "", state["scenario"], state.get("division"))
        await _card_post(deps, state, card, event, slot, "system", text=text)
        return
    await _card_post(deps, state, card, event, slot, actor)


async def _kickoff(deps, state, card, event) -> dict[str, Any]:
    await _card_post(deps, state, card, event, seq.KICKOFF_MANAGER, "manager")
    greeting = card.get("colleague_greeting")
    if greeting:
        await _card_post(
            deps,
            state,
            card,
            event,
            seq.KICKOFF_GREETING,
            "colleague",
            channel="dm",
            brief=greeting,
            rule="안녕하세요, 이번 건 잘 부탁드려요. 파트는 조금 뒤에 여쭐게요.",
        )
    return {"phase": "kickoff"}


async def _ask_division(deps, state, card, event, slot) -> dict[str, Any]:
    division = state.get("division")
    extra = [f"확정된 분업: {division}" if division else "분업: 아직 정하지 않음"]
    await _card_post(deps, state, card, event, slot, "colleague", extra=extra)
    changes: dict[str, Any] = {"phase": "work" if division else "division", "negotiate_round": 0}
    return changes


async def _send_parts(
    deps: RunDeps,
    state: SessionState,
    card: dict[str, Any],
    event: dict[str, Any],
    version: int,
    *,
    required: bool,
) -> tuple[dict[str, Any], list[str]]:
    """동료 파트 전부를 쓰고 보낸다. (work_notes, 보낸 문서 설명). 같이 파트는 v1이 골격이다.

    v1은 지시 반영 검사를 통과하지 못하면 그 파트를 건너뛰고(진행 질문만), v2(required)는 카드 실패.
    """
    notes = dict(state["work_notes"])
    sent = dict(notes.get("sent") or {})
    progress = dict(notes.get("progress") or {})
    division = state.get("division") or {}
    _, shared = await board_and_shared(deps)
    lines: list[str] = []
    for part_no in my_parts(division):
        key = str(part_no)
        target = max(version, sent.get(key, 0) + 1) if version > 1 else version
        done = sent_this_run(state, part_no)
        if done:
            # 보낸 뒤 체크포인트 전에 끊긴 재실행: 실제 보낸 버전으로 작업 기억을 복원한다
            number = done["shared_doc"]["version"]
            sent[key], progress[key] = number, f"v{number}까지 보낸 상태"
            lines.append(f"{part_no}번 v{number} 보냄")
            continue
        skeleton = version == 1 and division.get(key) == "both"
        content = await drafts.write_part(
            deps, state, part_no, target, shared=shared, skeleton=skeleton
        )
        if content is None:
            if required:
                deps.outcome.fail(f"draft_check_failed:{part_no}")
                raise CardFailed
            lines.append(f"{part_no}번은 아직 정리 중이라 보내지 않음")
            continue
        ok, number = await drafts.send_part(deps, state, part_no, content, event["id"])
        if not ok:
            deps.outcome.fail(f"{DOCUMENT_MISSING}: send_document failed for part {part_no}")
            raise CardFailed
        sent[key] = number
        progress[key] = f"v{number}까지 보낸 상태"
        lines.append(f"{part_no}번 {'골격 ' if skeleton else ''}v{number} 보냄")
    notes["sent"], notes["progress"] = sent, progress
    return notes, lines


async def _checkin(deps, state, card, event, slot) -> dict[str, Any]:
    if state.get("division") is None:  # texture에서 분업이 없으면 묻는 메시지만
        await _card_post(
            deps,
            state,
            card,
            event,
            slot,
            "colleague",
            extra=["분업이 아직 정해지지 않아 초안은 쓰지 않았다. 쓴 것처럼 말하지 않는다"],
        )
        return {}
    notes, lines = await _send_parts(deps, state, card, event, 1, required=False)
    state = {**state, "work_notes": notes}
    await _card_post(
        deps, state, card, event, slot, "colleague", extra=[f"보낸 문서: {', '.join(lines)}"]
    )
    return {"work_notes": notes}


async def _review(deps, state, card, event, slot) -> dict[str, Any]:
    notes, lines = await _send_parts(deps, state, card, event, 2, required=True)
    for part_no in my_parts(state.get("division")):
        result = await deps.code.call(
            "update_task", {"part_no": part_no, "status": "done", "run_id": state["run_id"]}
        )
        if not result.get("ok"):
            deps.outcome.fail(f"update_task:{error_code(result)}")
            raise CardFailed
    state = {**state, "work_notes": notes}
    await _card_post(
        deps, state, card, event, slot, "colleague", extra=[f"보낸 문서: {', '.join(lines)}"]
    )
    return {"work_notes": notes}


def disagree_target(
    state: SessionState,
    shared: dict[str, Any] | None,
    until_min: float | None,
    minutes: Callable[[str | None], float | None] = lambda iso: None,
) -> dict[str, Any]:
    """대상 규칙(카탈로그 target_rule): ① 3L/4(카드 due_at)까지 주담당이 보낸 1번 문서(50자 이상)
    최신 버전의 원인 가정 문장 ② 분업 때 정한 방향(agreements·instructions) ③ 킥오프 기본 가정.
    발행이 늦거나 재시도 중에 뒤늦게 보낸 버전은 쓰지 않는다."""
    for doc in (shared or {}).get("documents", []):
        if doc["owner"] != "candidate" or doc["part_no"] != 1:
            continue
        versions = [
            v
            for v in doc["versions"]
            if until_min is None or (minutes(v.get("created_at")) or 0) <= until_min
        ]
        if not versions:
            continue
        latest = versions[-1]
        content = (latest.get("content") or "").strip()
        if len(content) < MIN_TARGET_CHARS:
            continue
        for sentence in (s.strip() for s in SENTENCE.findall(content)):
            if sentence and CAUSE.search(sentence):
                return {
                    "document_id": doc["doc_id"],
                    "version": latest["version"],
                    "sentence": sentence,
                }
    notes = state["work_notes"]
    direction = [i["text"] for i in notes.get("instructions") or []] + list(
        notes.get("agreements") or []
    )
    if direction:
        return {"fallback": "board", "text": direction[-1]}
    return {"fallback": "kickoff", "text": state["scenario"].get("kickoff_assumption", "")}


def pick_opinion(card: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """주담당 방향이 이미 "관계"면 두 번째 의견, 아니면(일정·미정) 첫 번째 의견."""
    opinions = {o["id"]: o for o in card.get("fixed_opinions") or []}
    text = target.get("sentence") or target.get("text") or ""
    if "sentence" in target and RELATIONSHIP.search(text) and "schedule_first" in opinions:
        return opinions["schedule_first"]
    return opinions.get("relationship_first") or next(iter(opinions.values()))


async def _disagree(deps, state, card, event, slot) -> dict[str, Any]:
    """의견 본문은 카탈로그 고정 문장 그대로, 대상 문장 인용은 코드가 붙이고 말투(앞 문장)만
    생성."""
    _, shared = await board_and_shared(deps)
    # 재실행이면 처음 고른 대상을 그대로 쓴다(세션에 반대 의견 카드는 하나)
    target = state["work_notes"].get("disagree_target") or disagree_target(
        state,
        shared,
        deps.minutes(event["due_at"], exact=True),
        lambda iso: deps.minutes(iso, exact=True),
    )
    opinion = pick_opinion(card, target)
    if "sentence" in target:
        quote = f"1번에 “{target['sentence']}”라고 쓰신 부분이요."
    elif target["fallback"] == "board":
        quote = f"처음 정한 방향(“{target['text']}”) 기준으로 보면요."
    else:
        quote = "킥오프 때 출발 가정으로 둔 원인에 대해서요."
    if not already(state, slot):
        try:
            blocks = await context_blocks(deps, state, "colleague", state.get("division"))
            lead = await compose(
                deps,
                state,
                "colleague",
                [
                    *blocks,
                    prompts.say_block(
                        "리뷰 공유 뒤 주담당 파트에 대해 한 가지 의견을 내도 되는지 한 문장으로 "
                        "청한다. "
                        "의견 내용·근거는 말하지 않는다(뒤에 붙는다). 문서를 보내 달라고 하지 "
                        "않는다."
                    ),
                ],
                node="inject",
            )
        except LLMUnavailable:
            lead = "주담당 파트 확인해 봐도 될까요?"
        if "보내" in lead:  # 보내지 않은 주담당을 재촉하지 않는다
            lead = "주담당 파트 확인해 봐도 될까요?"
        text = f"{lead} {quote} {opinion['opinion'].strip()}"
        await _card_post(deps, state, card, event, slot, "colleague", text=text)
    notes = {**state["work_notes"], "disagree_target": {**target, "opinion_id": opinion["id"]}}
    return {"work_notes": notes}


async def _request_report(deps, state, card, event, slot) -> dict[str, Any]:
    session = deps.session
    submitted = session.get("submitted_at") is not None
    # 만료 자동 제출(submitted_at = ends_at)이면 "한 줄이면 됩니다"를 덧붙인다
    timeout = submitted and session.get("submitted_at") == session.get("ends_at")
    extra = (
        [f"덧붙일 말: {card['after_timeout_note']}"]
        if timeout and card.get("after_timeout_note")
        else []
    )
    await _card_post(deps, state, card, event, slot, "manager", extra=extra)
    if card.get("system_text") and not already(state, seq.CARD_NOTE):
        ok = await post(
            deps,
            state,
            channel="notice",
            sender="system",
            content=card["system_text"],
            slot=seq.CARD_NOTE,
            node="inject",
            event_id=event["id"],
            meta={"card_id": card["card_id"]},
        )
        if not ok:
            raise CardFailed
    return {"report_requested": True, "phase": "reporting" if submitted else "submit"}
