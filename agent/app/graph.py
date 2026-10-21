"""LangGraph for one candidate turn in the 3-party chat.

        START ──► observe ──┐         (silent evidence collector, parallel)
          │                 ▼
          └────► plan ───► react ──► gate ──┬─ stay ──► END
                (director)  (personas)       ├─ next ──► beat ──► END      (deliver next milestone's fixed situation)
                                             └─ finish ► closing ► END

Session state comes from Spring Boot (via business-mcp) and the result goes back the same way (runner.py);
the graph itself never touches a database. Persona lines stream as TOKEN events through the harness.
"""
import logging
import operator
import re
import time
from typing import Annotated, Any, TypedDict

from functools import wraps

from langgraph.graph import END, START, StateGraph

from .harness import instructions, runtime
from .llm import BaseLLM
from .dilemmas import persuade_beat
from .scenarios import MILESTONE_KEYS, MIN_TURNS_PER_MILESTONE, get_scenario

MAX_TURNS_WAITING_CHOICE = 4  # dilemma: wait up to this many turns for a choice before moving on

log = logging.getLogger("dayzero.graph")


def traced(fn):
    """Observability: one span per node, under the task's trace id."""

    @wraps(fn)
    async def run(state, config):
        ctx = runtime.current()
        if ctx is None:
            return await fn(state, config) if _is_async(fn) else fn(state, config)
        async with ctx.tracer.span("node", fn.__name__):
            return await fn(state, config) if _is_async(fn) else fn(state, config)

    return run


def _is_async(fn) -> bool:
    import inspect

    return inspect.iscoroutinefunction(fn)


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
    scn = {**get_scenario(sess["scenario_id"]), "condition": sess.get("condition")}
    names = {"user": sess["alias"], **{pid: p["name"] for pid, p in scn["personas"].items()}}
    return llm, scn, names


def _history(state: TurnState) -> list[dict]:
    """Persisted messages + this turn's user message + messages produced so far in this turn."""
    sess = state["session"]
    user = {"idx": state["user_idx"], "speaker": "user", "text": state["user_text"]}
    return [*sess["messages"], user, *state.get("new_messages", [])]


def _next_idx(state: TurnState) -> int:
    return state["user_idx"] + 1 + len(state.get("new_messages", []))


def _msg(idx: int, speaker: str, reply: dict, milestone_idx: int) -> dict:
    return {
        "idx": idx,
        "speaker": speaker,
        "text": reply["text"],
        "sources": reply.get("sources") or [],
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
        ctx = runtime.current()
        if ctx:
            ctx.tracer.note("observer_failed")
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
    local: list[dict] = []
    mi = state["milestone_idx"]
    for item in state["plan"]:
        pid = item["persona"]
        hist = [*_history(state), *local]
        directive = instructions.render("directive_react", intent=item["intent"])
        if local:  # second speaker answers the first persona too, so it reads as a 3-way chat
            directive += instructions.render("directive_react_second", prev=names[local[-1]["speaker"]])
        idx = state["user_idx"] + 1 + len(local)
        reply = await llm.speak(scn, pid, hist, names, directive, meta={"idx": idx, "milestone": MILESTONE_KEYS[mi]})
        local.append(_msg(idx, pid, reply, mi))
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
    nxt = state["milestone_idx_after"]
    key = MILESTONE_KEYS[nxt]
    b = scn["beats"][key]
    if scn.get("kind") == "dilemma" and key == "persuade":
        b = persuade_beat(scn, state["session"].get("choice"))
    # MockLLM returns the BEAT text verbatim; real models paraphrase it in persona voice.
    directive = instructions.render("directive_beat", must_convey=b["must_convey"])
    idx = _next_idx(state)
    reply = await llm.speak(scn, b["speaker"], _history(state), names, directive, meta={"idx": idx, "milestone": key})
    return {"new_messages": [_msg(idx, b["speaker"], reply, nxt)]}


async def closing(state: TurnState, config) -> dict:
    llm, scn, names = _ctx(state, config)
    fallback = "좋아요, 오늘 이야기한 내용으로 정리해서 진행할게요. 고마워요!"
    directive = instructions.render("directive_closing", fallback=fallback)
    idx = _next_idx(state)
    reply = await llm.speak(scn, "lead", _history(state), names, directive, meta={"idx": idx, "milestone": MILESTONE_KEYS[state["milestone_idx"]]})
    return {"new_messages": [_msg(idx, "lead", reply, state["milestone_idx"])], "completed": True}


def build_graph(checkpointer=None):
    g = StateGraph(TurnState)
    g.add_node("observe", traced(observe))
    g.add_node("plan", traced(plan))
    g.add_node("react", traced(react))
    g.add_node("gate", traced(gate))
    g.add_node("beat", traced(beat))
    g.add_node("closing", traced(closing))
    g.add_edge(START, "observe")
    g.add_edge(START, "plan")
    g.add_edge(["observe", "plan"], "react")
    g.add_edge("react", "gate")
    g.add_conditional_edges("gate", route, {"stay": END, "next": "beat", "finish": "closing"})
    g.add_edge("beat", END)
    g.add_edge("closing", END)
    return g.compile(checkpointer=checkpointer)
