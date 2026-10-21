"""LangGraph for one candidate turn in the 3-party chat.

        START ──► observe ──┐                 (silent evidence collector, parallel)
          ├────► ledger ────┤                 (dialogue notes: fold the last turn + this line in, parallel)
          └────► plan ──────┴──► react ──► gate ──┬─ stay ──► END
                (director +      (personas)       ├─ next ──► beat ──► END      (deliver next milestone's fixed situation)
                 speaker policy)                  └─ finish ► closing ► END

Session state comes from Spring Boot (via business-mcp) and the result goes back the same way (runner.py);
the graph itself never touches a database. Persona lines stream as TOKEN events through the harness.

Dialogue harness (harness/dialogue.py, DIALOGUE_HARNESS=1 by default): the director proposes a move per speaker,
code enforces the speaker policy, each persona gets an assembled context + move card and a repetition guard,
and the final state carries `dialogue` (the session's notes) for runner._turn -> append_turn(dialogue=...).
DIALOGUE_HARNESS=0: the ledger node is a no-op and plan/react/beat/closing run the previous prompts and flow.
"""
import logging
import operator
import re
import time
from typing import Annotated, Any, TypedDict

from functools import wraps

from langgraph.graph import END, START, StateGraph

from . import artifacts
from .harness import dialogue, instructions, runtime
from .llm import BaseLLM, persona_mode
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
    dialogue: dict  # dialogue harness: the session's notes after this turn (api-contract §2)
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


def _note(key: str) -> None:
    ctx = runtime.current()
    if ctx:
        ctx.tracer.note(key)


def _decide(sess: dict, idx: int) -> tuple[str, int, int]:
    """Milestone gate as a pure function (the director needs to know whether a beat/closing line follows)."""
    turns = sess["turns_in_milestone"] + 1
    waiting_choice = (
        get_scenario(sess["scenario_id"]).get("kind") == "dilemma"
        and MILESTONE_KEYS[idx] == "compromise"
        and not sess.get("choice")
        and turns < MAX_TURNS_WAITING_CHOICE
    )
    if turns < MIN_TURNS_PER_MILESTONE or waiting_choice:
        return "stay", turns, idx
    if idx >= len(MILESTONE_KEYS) - 1:
        return "finish", turns, idx
    return "next", 0, idx + 1


def _beat_for(scn: dict, sess: dict, key: str) -> dict:
    b = scn["beats"][key]
    if scn.get("kind") == "dilemma" and key == "persuade":
        b = persuade_beat(scn, sess.get("choice"))
    return b


def _modes(scn: dict) -> dict:
    return {pid: persona_mode(scn, pid) for pid in ("lead", "peer")}


def _card(scn, pid, item, hist, names, led, sess, marks, prev, user_text, kind="react") -> dict:
    """Dialogue harness: what llm.speak needs besides the directive (assembled context, artifact session, guard)."""
    docs = dialogue.known_docs(hist, led)
    mode = persona_mode(scn, pid)
    mk = next((a for a in marks if str(a["id"]) == str(item.get("markup_id"))), None) if item.get("markup_id") else None
    return {
        "context": dialogue.persona_context(pid=pid, names=names, ledger=led, history=hist, session=sess, marks=marks, prev=prev),
        "session": sess, "move": item.get("move"), "markup": mk, "anchor": dialogue.anchor_label(mk) if mk else None,
        "guard": lambda text, sources: dialogue.check(text, pid, history=hist, ledger=led, user_text=user_text, sources=sources,
                                                      docs=docs, mode=mode, kind=kind),
    }


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


async def ledger(state: TurnState, config) -> dict:
    """Dialogue notes (structured note-taking + compaction): fold the previous turn's persona lines and this candidate line in."""
    if not dialogue.enabled():
        return {}
    llm, scn, names = _ctx(state, config)
    led = dialogue.load(state["session"])
    pend = dialogue.pending(led, _history(state))
    if not pend:
        return {"dialogue": led}
    try:
        upd = await llm.update_ledger(scn, led, pend, names)
        return {"dialogue": dialogue.apply_update(led, upd.model_dump(), pend)}
    except Exception:  # like the observer: a failed note never breaks the conversation
        log.exception("ledger update failed")
        _note("ledger_failed")
        return {"dialogue": dialogue.fallback_update(led, pend, names)}


async def plan(state: TurnState, config) -> dict:
    if dialogue.enabled():
        return await _plan_dialogue(state, config)
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


async def _plan_dialogue(state: TurnState, config) -> dict:
    """Director v3 (moves) + speaker policy in code. Reads the notes as of the last turn (the ledger node runs in parallel)."""
    llm, scn, names = _ctx(state, config)
    sess, mkey = state["session"], MILESTONE_KEYS[state["milestone_idx"]]
    led = dialogue.load(sess)
    marks = dialogue.new_markups(sess, led)
    decision, _, after = _decide(sess, state["milestone_idx"])
    nxt = {"next": _beat_for(scn, sess, MILESTONE_KEYS[after])["speaker"], "finish": "lead"}.get(decision)
    max_lines = 2 if decision == "stay" else 1  # a fixed beat/closing line follows: at most 2 persona lines per turn
    modes = _modes(scn)
    h = dialogue.hints(scn, modes, state["user_text"], names, marks, max_lines, nxt, sess)
    try:
        dp = await llm.direct(scn, mkey, _history(state), names, state["user_text"], brief=dialogue.ledger_brief(led, names), hints=h,
                              artifacts_block=artifacts.context_block(sess, new_ids={str(a["id"]) for a in marks}) if marks else "")
        moves, tension = [m.model_dump() for m in dp.moves], dp.tension
    except Exception:
        log.exception("director failed")
        _note("director_failed")
        beat_pid = scn["beats"][mkey]["speaker"]
        moves, tension = [{"persona": "peer" if beat_pid == "lead" else "lead", "move": "answer"}], mkey != "communicate"
    items = dialogue.select(moves, scn=scn, modes=modes, user_text=state["user_text"], ledger=led, session=sess, marks=marks,
                            max_lines=max_lines, next_speaker=nxt, tension=tension)
    return {"plan": items}


async def react(state: TurnState, config) -> dict:
    if dialogue.enabled():
        return await _react_dialogue(state, config)
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


async def _react_dialogue(state: TurnState, config) -> dict:
    llm, scn, names = _ctx(state, config)
    sess, mi = state["session"], state["milestone_idx"]
    led = state.get("dialogue") or dialogue.load(sess)
    marks = dialogue.new_markups(sess, led)
    local: list[dict] = []
    for item in state["plan"]:
        pid = item["persona"]
        hist = [*_history(state), *local]
        prev = local[-1] if local else None
        directive = instructions.render("dialogue_move", **dialogue.move_values(item, names, session=sess, marks=marks, prev=prev, ledger=led, history=hist))
        idx = state["user_idx"] + 1 + len(local)
        card = _card(scn, pid, item, hist, names, led, sess, marks, prev, state["user_text"])
        reply = await llm.speak(scn, pid, hist, names, directive, meta={"idx": idx, "milestone": MILESTONE_KEYS[mi]}, card=card)
        local.append(_msg(idx, pid, reply, mi))
    led = dialogue.rule_update(led, local, plan=state["plan"], known_docs=dialogue.known_docs(_history(state), led))
    return {"new_messages": local, "dialogue": dialogue.mark_seen(led, marks, dialogue.answered_markups(state["plan"]))}


def gate(state: TurnState, config) -> dict:
    decision, turns, after = _decide(state["session"], state["milestone_idx"])
    return {"decision": decision, "turns_after": turns, "milestone_idx_after": after}


def route(state: TurnState) -> str:
    return state["decision"]


async def beat(state: TurnState, config) -> dict:
    llm, scn, names = _ctx(state, config)
    nxt = state["milestone_idx_after"]
    key = MILESTONE_KEYS[nxt]
    b = _beat_for(scn, state["session"], key)
    # MockLLM returns the BEAT text verbatim; real models paraphrase it in persona voice.
    directive = instructions.render("directive_beat", must_convey=b["must_convey"])
    idx = _next_idx(state)
    meta = {"idx": idx, "milestone": key}
    if not dialogue.enabled():
        reply = await llm.speak(scn, b["speaker"], _history(state), names, directive, meta=meta)
        return {"new_messages": [_msg(idx, b["speaker"], reply, nxt)]}
    hist, led = _history(state), state.get("dialogue") or dialogue.load(state["session"])
    card = _card(scn, b["speaker"], {"move": "propose"}, hist, names, led, state["session"], [], None, state["user_text"], kind="beat")
    m = _msg(idx, b["speaker"], await llm.speak(scn, b["speaker"], hist, names, directive, meta=meta, card=card), nxt)
    return {"new_messages": [m], "dialogue": dialogue.rule_update(led, [m], known_docs=dialogue.known_docs(hist, led))}


async def closing(state: TurnState, config) -> dict:
    llm, scn, names = _ctx(state, config)
    fallback = "좋아요, 오늘 이야기한 내용으로 정리해서 진행할게요. 고마워요!"
    idx = _next_idx(state)
    meta = {"idx": idx, "milestone": MILESTONE_KEYS[state["milestone_idx"]]}
    if not dialogue.enabled():
        directive = instructions.render("directive_closing", fallback=fallback)
        reply = await llm.speak(scn, "lead", _history(state), names, directive, meta=meta)
        return {"new_messages": [_msg(idx, "lead", reply, state["milestone_idx"])], "completed": True}
    hist, led = _history(state), state.get("dialogue") or dialogue.load(state["session"])
    directive = instructions.render("directive_closing_dialogue", fallback=fallback, commitments=dialogue.commitments_text(led, names))
    card = _card(scn, "lead", {"move": "summarize"}, hist, names, led, state["session"], [], None, state["user_text"], kind="beat")
    m = _msg(idx, "lead", await llm.speak(scn, "lead", hist, names, directive, meta=meta, card=card), state["milestone_idx"])
    return {"new_messages": [m], "completed": True, "dialogue": dialogue.rule_update(led, [m], known_docs=dialogue.known_docs(hist, led))}


def build_graph(checkpointer=None):
    g = StateGraph(TurnState)
    g.add_node("observe", traced(observe))
    g.add_node("ledger", traced(ledger))
    g.add_node("plan", traced(plan))
    g.add_node("react", traced(react))
    g.add_node("gate", traced(gate))
    g.add_node("beat", traced(beat))
    g.add_node("closing", traced(closing))
    g.add_edge(START, "observe")
    g.add_edge(START, "ledger")
    g.add_edge(START, "plan")
    g.add_edge(["observe", "ledger", "plan"], "react")
    g.add_edge("react", "gate")
    g.add_conditional_edges("gate", route, {"stay": END, "next": "beat", "finish": "closing"})
    g.add_edge("beat", END)
    g.add_edge("closing", END)
    return g.compile(checkpointer=checkpointer)
