"""LangGraph for one candidate turn in the 3-party chat.

        START ──► observe ──┐         (silent evidence collector, parallel)
          │                 ▼
          └────► plan ───► react ──► gate ──┬─ stay ──► END
                (director)  (personas)       ├─ next ──► beat ──► END      (deliver next milestone's fixed situation)
                                             └─ finish ► closing ► END

State is exchanged per turn; the persisted session document lives in store.py (see service.py).
"""
import logging
import operator
import re
import time
from typing import Annotated, Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from .llm import BaseLLM
from .dilemmas import persuade_beat
from .scenarios import MILESTONE_KEYS, MIN_TURNS_PER_MILESTONE, get_scenario

MAX_TURNS_WAITING_CHOICE = 4  # dilemma: wait up to this many turns for a choice before moving on

log = logging.getLogger("dayzero.graph")
FALLBACK_LINE = "잠깐 연결이 불안정했어요. 방금 내용 한 번만 다시 말씀해 주실래요?"


class TurnState(TypedDict, total=False):
    session: dict
    user_text: str
    user_idx: int
    milestone_idx: int  # milestone at the time the candidate spoke
    plan: list[dict]
    observations: Annotated[list, operator.add]
    new_messages: Annotated[list, operator.add]
    decision: str  # stay | next | finish
    milestone_idx_after: int
    turns_after: int
    completed: bool


def _ctx(state: TurnState, config) -> tuple[BaseLLM, dict, dict]:
    llm: BaseLLM = config["configurable"]["llm"]
    sess = state["session"]
    scn = get_scenario(sess["scenario_id"])
    names = {"user": sess["alias"], **{pid: p["name"] for pid, p in scn["personas"].items()}}
    return llm, scn, names


def _history(state: TurnState) -> list[dict]:
    """Persisted messages + this turn's user message + messages produced so far in this turn."""
    sess = state["session"]
    user = {"idx": state["user_idx"], "speaker": "user", "text": state["user_text"]}
    return [*sess["messages"], user, *state.get("new_messages", [])]


def _msg(state: TurnState, speaker: str, text: str, milestone_idx: int) -> dict:
    return {
        "idx": state["user_idx"] + 1 + len(state.get("new_messages", [])),
        "speaker": speaker,
        "text": text,
        "ts": time.time(),
        "milestone": MILESTONE_KEYS[milestone_idx],
    }


def _verified(quote: str, user_text: str) -> bool:
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    return bool(norm(quote)) and norm(quote) in norm(user_text)


async def observe(state: TurnState, config) -> dict:
    llm, scn, names = _ctx(state, config)
    mkey = MILESTONE_KEYS[state["milestone_idx"]]
    try:
        items = await llm.observe(scn, mkey, _history(state), names, state["user_text"])
    except Exception:  # observation failure must never break the conversation
        log.exception("observer failed")
        return {"observations": []}
    out = []
    for n, it in enumerate(items):
        if not _verified(it.quote, state["user_text"]):
            continue  # drop hallucinated evidence (success metric: 근거 정확도)
        out.append(
            {
                "id": f"o{state['user_idx']}_{n}",
                "competency": it.competency,
                "milestone": mkey,
                "behavior": it.behavior,
                "quote": it.quote.strip(),
                "signal": it.signal,
                "msg_idx": state["user_idx"],
            }
        )
    return {"observations": out}


async def plan(state: TurnState, config) -> dict:
    llm, scn, names = _ctx(state, config)
    mkey = MILESTONE_KEYS[state["milestone_idx"]]
    try:
        tp = await llm.plan(scn, mkey, _history(state), names, state["user_text"])
        items = [{"persona": i.persona, "intent": i.intent} for i in tp.speakers[:2]]
    except Exception:
        log.exception("director failed")
        items = []
    if not items:
        beat_pid = scn["beats"][mkey]["speaker"]
        items = [{"persona": "peer" if beat_pid == "lead" else "lead", "intent": "지원자 발화에 자연스럽게 반응한다"}]
    return {"plan": items}


async def react(state: TurnState, config) -> dict:
    llm, scn, names = _ctx(state, config)
    write = get_stream_writer()
    local: list[dict] = []
    for item in state["plan"]:
        pid = item["persona"]
        write({"type": "typing", "speaker": pid})
        hist = [*_history(state), *local]
        directive = (
            f"지원자의 마지막 말에 반응한다. 의도: {item['intent']}. "
            "아직 다음 안건을 먼저 꺼내지 말고 지금 대화에만 반응한다."
        )
        if local:  # second speaker answers the first persona too, so it reads as a 3-way chat
            prev = names[local[-1]["speaker"]]
            directive += f" 바로 앞에서 {prev}이 한 말에 직접 반응(동의·보완·반박)하고, 지원자에게도 한 마디 건넨다."
        try:
            text = await llm.speak(scn, pid, hist, names, directive)
        except Exception:
            log.exception("persona failed")
            text = FALLBACK_LINE
        m = {
            "idx": state["user_idx"] + 1 + len(local),
            "speaker": pid,
            "text": text,
            "ts": time.time(),
            "milestone": MILESTONE_KEYS[state["milestone_idx"]],
        }
        local.append(m)
        write({"type": "message", "message": m})
    return {"new_messages": local}


def gate(state: TurnState, config) -> dict:
    sess = state["session"]
    turns = sess["turns_in_milestone"] + 1
    idx = state["milestone_idx"]
    waiting_choice = (
        get_scenario(sess["scenario_id"]).get("kind") == "dilemma"
        and MILESTONE_KEYS[idx] == "compromise"
        and not sess.get("choice")
        and turns < MAX_TURNS_WAITING_CHOICE
    )
    if turns < MIN_TURNS_PER_MILESTONE or waiting_choice:
        return {"decision": "stay", "turns_after": turns, "milestone_idx_after": idx}
    if idx >= len(MILESTONE_KEYS) - 1:
        return {"decision": "finish", "turns_after": turns, "milestone_idx_after": idx}
    return {"decision": "next", "turns_after": 0, "milestone_idx_after": idx + 1}


def route(state: TurnState) -> str:
    return state["decision"]


async def beat(state: TurnState, config) -> dict:
    llm, scn, names = _ctx(state, config)
    write = get_stream_writer()
    nxt = state["milestone_idx_after"]
    key = MILESTONE_KEYS[nxt]
    b = scn["beats"][key]
    if scn.get("kind") == "dilemma" and key == "persuade":
        b = persuade_beat(scn, state["session"].get("choice"))
    write({"type": "milestone", "index": nxt, "key": key})
    write({"type": "typing", "speaker": b["speaker"]})
    directive = (
        "새 안건을 자연스럽게 꺼낸다. 아래 내용을 빠짐없이 전달하되 말투는 네 성격에 맞게 바꾼다. "
        f"BEAT: {b['must_convey']}"
    )
    # MockLLM returns the BEAT text verbatim; real LLMs paraphrase it in persona voice.
    try:
        text = await llm.speak(scn, b["speaker"], _history(state), names, directive)
    except Exception:
        text = b["must_convey"]
    m = _msg(state, b["speaker"], text, nxt)
    write({"type": "message", "message": m})
    return {"new_messages": [m]}


async def closing(state: TurnState, config) -> dict:
    llm, scn, names = _ctx(state, config)
    write = get_stream_writer()
    write({"type": "typing", "speaker": "lead"})
    fallback = "좋아요, 오늘 이야기한 내용으로 정리해서 진행할게요. 고마워요!"
    directive = (
        "대화를 마무리한다. 오늘 논의된 내용을 한 줄로 정리하고 고맙다고 말한다. 평가나 결과 이야기는 하지 않는다. "
        f"BEAT: {fallback}"
    )
    try:
        text = await llm.speak(scn, "lead", _history(state), names, directive)
    except Exception:
        text = fallback
    m = _msg(state, "lead", text, state["milestone_idx"])
    write({"type": "message", "message": m})
    return {"new_messages": [m], "completed": True}


def build_graph():
    g = StateGraph(TurnState)
    g.add_node("observe", observe)
    g.add_node("plan", plan)
    g.add_node("react", react)
    g.add_node("gate", gate)
    g.add_node("beat", beat)
    g.add_node("closing", closing)
    g.add_edge(START, "observe")
    g.add_edge(START, "plan")
    g.add_edge(["observe", "plan"], "react")
    g.add_edge("react", "gate")
    g.add_conditional_edges("gate", route, {"stay": END, "next": "beat", "finish": "closing"})
    g.add_edge("beat", END)
    g.add_edge("closing", END)
    return g.compile()


GRAPH = build_graph()
