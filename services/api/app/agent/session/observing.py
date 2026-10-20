"""관찰 창 열고 닫기. 요소 카드가 실행되면 열린 창을 그 카드의 due_at에서 닫아 기록하고 새 창을
연다.

창 경계는 시나리오(이벤트 due_at)에서 정해지므로 재실행해도 같은 키 (card_id, window_start)가 된다.
planning_division만 세션 시작(0)부터다. 종료 자극은 마지막 창을 completed_at에서 닫고 collab_help의
promise_kept를 다시 세서 PATCH한다(같은 run_id 멱등).
"""

import logging
from typing import Any

from langgraph.runtime import Runtime

from app.agent import observe
from app.agent.mcp_client import error_code
from app.agent.session.common import RunDeps, cards_by_id, resumed
from app.agent.session.state import SessionState

log = logging.getLogger(__name__)

OBSERVE_PROMPT = "observe_labels.md"


def _window(deps: RunDeps, state: SessionState, card_id: str, start: float, end: float):
    card = cards_by_id(state)[card_id]
    events = [e for e in deps.events() if e["card_id"] == card_id]
    due = deps.minutes(events[0]["due_at"]) if events else card["at_min"]
    return observe.Window(
        card=card,
        start=start,
        end=end,
        due=due if due is not None else start,
        event_ids=[e["id"] for e in events],
    )


def _card_time(window: observe.Window, inputs: observe.Inputs) -> float | None:
    times = [m["t_min"] for m in inputs.messages if m.get("event_id") in window.event_ids]
    return min(times) if times else None


async def _inputs(deps: RunDeps, state: SessionState, session_id) -> observe.Inputs:
    delay = cards_by_id(state).get("responsibility_delay") or {}
    release = (delay.get("effects") or {}).get("release_document")
    return await deps.store.observe_inputs(session_id, release)


async def close_window(deps: RunDeps, state: SessionState, end: float) -> bool:
    """열린 창(current_card)을 end에서 닫고 record_observation. 실패하면 outcome에 남기고 False."""
    import uuid

    card_id, start = state.get("current_card"), state.get("window_start")
    if card_id is None or start is None:
        return True
    session_id = uuid.UUID(state["session_id"])
    # 저장 성공 직후 끊긴 재실행이면 다시 분류하지 않는다(최초 저장 결과가 정본)
    if any(
        o["card_id"] == card_id and o["window_start"] == round(start, 2)
        for o in await deps.store.observations(session_id)
    ):
        return True
    window = _window(deps, state, card_id, start, end)
    inputs = await _inputs(deps, state, session_id)
    window.card_t_min = _card_time(window, inputs)
    body = await observe.observe(
        window,
        inputs,
        None if deps.observe_exhausted(state) else deps.llm_for("observe"),
        state["scenario"]["prompts"][OBSERVE_PROMPT],
        usage=deps.usage,
        trace=deps.trace(state, "observe"),
    )
    result = await deps.code.call("record_observation", {**body, "run_id": state["run_id"]})
    if not result.get("ok"):
        deps.outcome.fail(f"record_observation:{error_code(result)}")
        return False
    return True


def opening_card(state: SessionState, card_ids: list[str]) -> str | None:
    """이 묶음에서 창을 여는 요소 카드(흐름 카드·texture는 창을 열지 않는다). 같은 시각이면 뒤의 것
    (review 흐름 + collab_disagree면 collab_disagree)."""
    cards = cards_by_id(state)
    found = [cid for cid in card_ids if cards[cid].get("element") and not cards[cid].get("texture")]
    return found[-1] if found else None


async def observe_node(state: SessionState, runtime: Runtime[RunDeps]) -> dict[str, Any]:
    """inject 뒤. 이번 묶음에 실행된 요소 카드가 있으면 직전 창을 닫고 그 카드의 창을 연다."""
    deps = runtime.context
    state, resume = await resumed(deps, state)
    injected = list(state["stimulus"].get("injected") or [])
    # 카드 실행과 창 전환(관찰 저장)이 모두 끝난 행만 처리 완료로 확정한다. 관찰 저장이 실패하면
    # 같은 run_id 재시도가 카드(멱등)부터 다시 돌아 창 전환을 마저 한다
    handled = {"handled_stimuli": [*state.get("handled_stimuli", []), *injected]}
    done = [(e["card_id"], e) for e in deps.events() if e["id"] in injected]
    card_id = opening_card(state, [cid for cid, _ in done])
    if card_id is None or card_id == state.get("current_card"):
        return {**resume, **handled}
    event = next(e for cid, e in done if cid == card_id)
    due = deps.minutes(event["due_at"])
    if not await close_window(deps, state, due):
        return {**resume, "last_error": deps.outcome.error}
    card = cards_by_id(state)[card_id]
    start = card.get("window_start_min", due) if card_id == "planning_division" else due
    return {**resume, **handled, "current_card": card_id, "window_start": start}


async def close(state: SessionState, runtime: Runtime[RunDeps]) -> dict[str, Any]:
    """종료 자극: 열린 창 닫기(window_end=completed_at) → collab_help promise_kept PATCH → done."""
    import uuid

    deps = runtime.context
    state, resume = await resumed(deps, state)
    session = deps.session
    end = deps.minutes(session.get("completed_at"), exact=True) or session.get("t_min_now") or 0.0
    if not await close_window(deps, state, end):
        return {**resume, "last_error": deps.outcome.error}
    session_id = uuid.UUID(state["session_id"])
    for row in await deps.store.observations(session_id):
        if row["card_id"] != "collab_help":
            continue
        window = _window(deps, state, "collab_help", row["window_start"], row["window_end"])
        inputs = await _inputs(deps, state, session_id)
        window.card_t_min = _card_time(window, inputs)
        value = observe.promise_kept(window, inputs, row["label"], row["aux"])
        result = await deps.code.call(
            "update_observation",
            {
                "card_id": "collab_help",
                "window_start": row["window_start"],
                "metrics_patch": {"promise_kept": value},
                "run_id": state["run_id"],
            },
        )
        if not result.get("ok"):
            deps.outcome.fail(f"update_observation:{error_code(result)}")
            return {**resume, "last_error": deps.outcome.error}
    handled = [*state.get("handled_stimuli", []), f"end:{state['run_id']}"]
    return {**resume, "handled_stimuli": handled, "phase": "done", "current_card": None}
