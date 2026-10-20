"""분업: 확정 공통 함수(confirm_division), 기본안 확정, 채팅 분업(negotiate), 보드 확정
자극(division).

- 주담당이 정한다. 동료는 division_min(2번 주담당, 3번 동료·같이, 4·5 중 하나 동료 단독)을 어긴
  결정만 의존 관계를 이유로 1회 되돌리고, 되돌린 뒤에도 어기면 조건에 맞춘 안으로 확정한다.
- 보드 확정(stimulus=division)은 api가 이미 확정했으므로 set_division을 부르지 않는다.
- 업무 중 재분업은 적응성 카드 전 1회 + 뒤 1회. 담당을 그대로 둔 방향 재지시는 respond가 받는다.
"""

import uuid
from typing import Any

from langgraph.runtime import Runtime

from app.agent.llm import LLMUnavailable
from app.agent.mcp_client import error_code
from app.agent.session import prompts, seq
from app.agent.session.common import (
    RunDeps,
    already,
    compose,
    context_blocks,
    my_parts,
    post,
    resumed,
)
from app.agent.session.state import SessionState
from app.services.board import InvalidDivision, check_division

LIMIT_TEXT = "일정상 지금 더 바꾸긴 어렵겠어요. 지금 분담대로 마무리해 볼게요."
# 재분업 한도(적응성 카드 전 1회·뒤 1회)는 api(board.use_redivide)가 세션 redivisions로 센다
WHO = {"candidate": "주담당", "colleague": "도현", "both": "같이"}


def describe(parts: dict[str, str]) -> str:
    """{"1": "candidate", ...} → "1번 주담당, 2번 주담당, 3번 같이, …"."""
    return ", ".join(f"{no}번 {WHO.get(who, who)}" for no, who in sorted(parts.items()))


def violation(parts: dict[str, str], scenario: dict[str, Any]) -> str | None:
    try:
        check_division(parts, scenario)
    except InvalidDivision as exc:
        return str(exc)
    return None


def fix(parts: dict[str, str], scenario: dict[str, Any]) -> dict[str, str]:
    """주담당 안을 최소한만 바꿔 division_min에 맞춘 대안(빈 파트는 기본안으로)."""
    default = {str(k): v for k, v in scenario["default_division"].items()}
    fixed = {no: parts.get(no) or default[no] for no in scenario["parts"]}
    rule = scenario["division_min"]
    for no, allowed in rule.items():
        if no == "any_colleague_only":
            continue
        if fixed[no] not in allowed:
            fixed[no] = "both" if "both" in allowed else allowed[0]
    if not any(fixed[str(no)] == "colleague" for no in rule["any_colleague_only"]):
        fixed[str(rule["any_colleague_only"][0])] = "colleague"
    return fixed


def agreements(parts: dict[str, str]) -> list[str]:
    return [
        f"{no}번은 같이: 골격은 도현이 먼저 보내고 주담당이 최종본에서 고침"
        for no, who in sorted(parts.items())
        if who == "both"
    ]


async def confirm_division(
    deps: RunDeps, state: SessionState, parts: dict[str, str]
) -> dict[str, Any]:
    """확정 분업에 작업 기억과 보드를 맞춘다(주담당 결정·기본안·재분업 공통). work_notes를 돌려준다.

    담당이 바뀐 파트는 문서 주인이 바뀌지 않고, 동료가 새로 맡은 파트는 동료 문서를 새로 쓴다.
    """
    notes = dict(state["work_notes"])
    mine = my_parts(parts)
    notes["parts"] = mine
    notes["agreements"] = agreements(parts)
    notes["progress"] = {k: v for k, v in (notes.get("progress") or {}).items() if int(k) in mine}
    board = await deps.code.call("get_board")
    status = {t["part_no"]: t["status"] for t in (board.get("data") or {}).get("tasks", [])}
    for part_no in mine:
        if status.get(part_no) in ("doing", "done"):
            continue
        result = await deps.code.call(
            "update_task", {"part_no": part_no, "status": "doing", "run_id": state["run_id"]}
        )
        if not result.get("ok"):
            deps.outcome.fail(f"update_task:{error_code(result)}")
    return notes


async def set_division(
    deps: RunDeps, state: SessionState, parts: dict[str, str], decided_by: str
) -> bool:
    result = await deps.code.call(
        "set_division", {"parts": parts, "decided_by": decided_by, "run_id": state["run_id"]}
    )
    if not result.get("ok"):
        deps.outcome.fail(f"set_division:{error_code(result)}")
        return False
    return True


async def default_division(deps: RunDeps, state: SessionState) -> dict[str, Any] | None:
    """다음 요소 카드가 왔는데 미확정이면 기본안으로 확정하고 알린다(PRD F-21, colleague_default).

    State 갱신값을 돌려준다. 이미 확정돼 있으면 None.
    """
    if state.get("division") is not None:
        return None
    scenario = state["scenario"]
    parts = {str(k): v for k, v in scenario["default_division"].items()}
    if not await set_division(deps, state, parts, "colleague_default"):
        return {}
    notes = await confirm_division(deps, state, parts)
    if not already(state, seq.DEFAULT_DIVISION):
        mine = "·".join(str(p) for p in my_parts(parts))
        text = (
            f"아직 분업이 안 정해져서 일단 {describe(parts)}로 진행할게요. 저는 {mine}번 맡을게요."
        )
        await post(
            deps,
            state,
            channel="dm",
            sender="colleague",
            content=text,
            slot=seq.DEFAULT_DIVISION,
            node="default_division",
        )
    return {"division": parts, "work_notes": notes, "phase": _work_phase(state)}


def _work_phase(state: SessionState) -> str:
    return "work" if state.get("phase") in ("kickoff", "division") else state["phase"]


async def _say(
    deps: RunDeps,
    state: SessionState,
    division: dict[str, str] | None,
    instruction: str,
    fallback: str,
    channel: str,
) -> bool:
    """분업 수락·되돌림·참고안 말하기. LLM이 실패하면 고정 문장."""
    if already(state, seq.RESPOND):
        return True
    try:
        blocks = await context_blocks(deps, state, "colleague", division)
        text = await compose(
            deps, state, "colleague", [*blocks, prompts.say_block(instruction)], node="negotiate"
        )
    except LLMUnavailable:
        text, deps.outcome.fallback_used = fallback, True
    return await post(
        deps,
        state,
        channel=channel,
        sender="colleague",
        content=text,
        slot=seq.RESPOND,
        node="negotiate",
    )


async def negotiate(state: SessionState, runtime: Runtime[RunDeps]) -> dict[str, Any]:
    """채팅 분업: decide면 최소 조건 검사 후 수락(set_division·보드 doing) 또는 대안(되돌림 1회),
    ask면 기본안을 참고로만 말하고 결정을 돌린다. 업무 중 재분업(redivide)은 한도 안에서 수락."""
    deps = runtime.context
    state, resume = await resumed(deps, state)
    stimulus = state["stimulus"]
    cls = stimulus["classification"]
    channel = stimulus["channel"]
    scenario = state["scenario"]
    division = state.get("division")
    handled = [*state.get("handled_stimuli", []), stimulus["message_id"]]
    update: dict[str, Any] = {**resume, "handled_stimuli": handled, "seq": seq.RESPOND}

    if cls.get("decision") == "ask" and division is None:
        default = {str(k): v for k, v in scenario["default_division"].items()}
        ok = await _say(
            deps,
            state,
            division,
            f"주담당이 어떻게 나눌지 되물었다. 참고로만 '{describe(default)}'도 가능하다고 말하고 "
            "결정은 주담당에게 돌린다. 순서·시점은 정하지 않는다.",
            "참고로 1·2번 주담당님, 3번 같이, 4·5번 제가 맡는 식도 가능해요. 정해 주시면 그대로 "
            "갈게요.",
            channel,
        )
        return update if ok else {"last_error": deps.outcome.error}

    parts = {**(division or {}), **(cls.get("parts") or {})}
    if parts == division:
        ok = await _say(
            deps,
            state,
            division,
            "이미 정해진 분업 그대로라는 것을 확인하는 한 문장.",
            "네, 정해 주신 대로 진행할게요.",
            channel,
        )
        return update if ok else {"last_error": deps.outcome.error}

    reassign = division is not None
    # 재분업 한도는 api가 보드 PUT과 함께 세션에 기록한다(같은 한도를 두 경로가 공유)
    if reassign and not await deps.store.redivide_allowed(uuid.UUID(state["session_id"])):
        # 한도 안내는 고정 문장(모델이 받아들이는 말로 바꾸지 않게)
        ok = already(state, seq.RESPOND) or await post(
            deps,
            state,
            channel=channel,
            sender="colleague",
            content=LIMIT_TEXT,
            slot=seq.RESPOND,
            node="negotiate",
        )
        return update if ok else {"last_error": deps.outcome.error}

    problem = violation(parts, scenario)
    round_ = state.get("negotiate_round", 0)
    if problem is not None and round_ < 1 and not reassign:
        proposal = fix(parts, scenario)
        notes = {**state["work_notes"], "proposal": proposal}
        ok = await _say(
            deps,
            state,
            division,
            f"주담당 안이 팀 일정에 안 맞는다. 이유: {problem} 조건에 맞춘 안 "
            f"'{describe(proposal)}'을 "
            "한 번만 제안하고 주담당이 다시 정해 달라고 한다. 평가·시스템 사정을 이유로 들지 "
            "않는다.",
            f"{problem} 그래서 {describe(proposal)}로 가면 어떨까요? 정해 주시면 그대로 갈게요.",
            channel,
        )
        if not ok:
            return {"last_error": deps.outcome.error}
        return {**update, "negotiate_round": round_ + 1, "work_notes": notes}
    if problem is not None:
        parts = fix(parts, scenario)  # 되돌림은 1회. 다시 어기면 조건에 맞춘 안으로 확정

    if not await set_division(deps, state, parts, "candidate"):
        return {"last_error": deps.outcome.error}
    notes = await confirm_division(deps, state, parts)
    notes["proposal"] = None
    text = "알겠어요, 그렇게 바꿀게요." if reassign else "네, 그렇게 할게요."
    state = {**state, "work_notes": notes}
    ok = await _say(
        deps,
        state,
        parts,
        f"주담당이 정한 분업({describe(parts)})을 그대로 받아들인다는 확인 한두 문장. "
        "보드에 담당이 반영됐다고 덧붙여도 된다.",
        text,
        channel,
    )
    if not ok:
        return {"last_error": deps.outcome.error}
    return {
        **update,
        "division": parts,
        "work_notes": notes,
        "phase": _work_phase(state),
        "negotiate_round": round_,
    }


async def division_node(state: SessionState, runtime: Runtime[RunDeps]) -> dict[str, Any]:
    """보드 확정·재배정 자극. api가 이미 확정했으므로 작업 기억·보드 doing을 맞추고 수락만
    말한다."""
    deps = runtime.context
    state, resume = await resumed(deps, state)
    division = (deps.session.get("division") or {}).get("parts")
    handled = [*state.get("handled_stimuli", []), f"division:{state['run_id']}"]
    if not division:
        return {**resume, "handled_stimuli": handled}
    first = state.get("division") is None
    notes = await confirm_division(deps, state, division)
    state = {**state, "work_notes": notes, "division": division}
    instruction = (
        "주담당이 보드에 정한 분업을 봤고 그대로 하겠다는 짧은 확인."
        if first
        else "주담당이 보드에서 담당을 바꾼 것을 봤고 그렇게 맞추겠다는 짧은 확인."
    )
    fallback = "보드 봤어요, 그렇게 할게요." if first else "보드 바뀐 거 봤어요, 그렇게 맞출게요."
    ok = await _say(deps, state, division, instruction, fallback, "dm")
    update = {**resume, "division": division, "work_notes": notes, "phase": _work_phase(state)}
    if not ok:
        return {**update, "last_error": deps.outcome.error}
    return {**update, "handled_stimuli": handled, "seq": seq.RESPOND}
