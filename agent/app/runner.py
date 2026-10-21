"""Task execution (one agent job = one trace). START | TURN | REPORT (RUN or RESUME after approval).

Data in and out goes through business-mcp (Spring /internal/**); the agent never writes the business DB.
Retry: the caller (HTTP background loop or RabbitMQ consumer) retries retryable failures; only the final
attempt reports FAILED. TOKEN events carry `attempt` and a `reset` flag, so a retry replaces partial text.
"""
from __future__ import annotations

import asyncio
import logging
import time

from langgraph.types import Command

from . import detector
from .graph import build_graph
from .harness import guardrails, instructions, memory, runtime, tools
from .harness.events import EventPublisher, Sink, spring_sink
from .harness.loop import LimitExceeded
from .harness.observability import Tracer
from .harness.runtime import TaskContext
from .llm import get_llm
from .personas import allocate
from .report_graph import build_report_graph
from .scenarios import MILESTONE_KEYS, get_scenario

log = logging.getLogger("dayzero.runner")
MAX_ATTEMPTS = 3
_graphs: dict = {}
_llm = None
_sink: Sink | None = None
_bg: set[asyncio.Task] = set()


class NonRetryable(RuntimeError):
    pass


def set_sink(sink: Sink | None) -> None:
    global _sink
    _sink = sink


def set_llm(llm) -> None:
    global _llm
    _llm = llm


def llm():
    global _llm
    if _llm is None:
        _llm = get_llm()
    return _llm


async def graphs() -> dict:
    if not _graphs:
        saver = await memory.open_checkpointer()
        _graphs["turn"] = build_graph(saver)
        _graphs["report"] = build_report_graph(saver)
    return _graphs


def reset_graphs() -> None:
    _graphs.clear()


def retryable(e: Exception) -> bool:
    if isinstance(e, (NonRetryable, LimitExceeded, guardrails.ApprovalRequired)):
        return False
    text = str(e)
    return not any(code in text for code in ("400", "403", "404", "409", "410"))


async def execute(msg: dict, final_attempt: bool = True) -> None:
    attempt = int(msg.get("attempt", 1))
    sink = _sink or spring_sink()
    ctx = TaskContext(msg["taskId"], msg.get("sessionId"), attempt, EventPublisher(msg["taskId"], sink), Tracer(msg["taskId"]))
    token = runtime.bind(ctx)
    try:
        result = await asyncio.wait_for(_run(msg, ctx), timeout=ctx.limits.task_timeout_s)
        if "_interrupt" in result:
            await ctx.events.emit("APPROVAL_REQUIRED", {**result["_interrupt"], "attempt": attempt, "trace": ctx.tracer.summary()})
        else:
            await ctx.events.emit("DONE", {**result, "attempt": attempt, "trace": ctx.tracer.summary()})
    except Exception as e:
        log.exception("task %s failed (attempt %d)", msg["taskId"], attempt)
        if final_attempt or not retryable(e):
            await ctx.events.emit("FAILED", {"error": f"{type(e).__name__}: {str(e)[:300]}", "attempt": attempt, "trace": ctx.tracer.summary()})
            if not final_attempt:
                raise NonRetryable(str(e)) from e
        else:
            raise
    finally:
        await ctx.events.close()
        runtime.unbind(token)


async def run_with_retries(msg: dict) -> None:
    """HTTP dispatch mode: retry in-process with backoff (RabbitMQ mode retries through the queue instead)."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            await execute({**msg, "attempt": attempt}, final_attempt=attempt == MAX_ATTEMPTS)
            return
        except NonRetryable:
            return
        except Exception:
            await asyncio.sleep(1.5 * attempt)


async def _run(msg: dict, ctx: TaskContext) -> dict:
    kind, mode = msg["type"], msg.get("mode", "RUN")
    if kind == "START":
        return await _start(msg)
    if kind == "TURN":
        return await _turn(msg, ctx)
    if kind == "REPORT":
        return await (_report_resume(msg) if mode == "RESUME" else _report_run(msg))
    raise NonRetryable(f"unknown task type {kind}")


def _names(st: dict, scn: dict) -> dict:
    return {"user": st["alias"], **{pid: p["name"] for pid, p in scn["personas"].items()}}


async def _start(msg: dict) -> dict:
    sid = msg["sessionId"]
    st = await tools.call("business", "get_session_state", {"session_id": sid})
    if st.get("messages"):  # idempotent on retry
        return {"messages": st["messages"], "milestone_idx": st["milestone_idx"], "skipped": True}
    scn = get_scenario(st["scenario_id"])
    history = await tools.call("business", "list_conditions", {})
    condition = allocate(scn.get("axis") or st["scenario_id"], history or [], seed=int(sid, 16))
    scn_c = {**scn, "condition": condition}
    beat = scn["beats"]["communicate"]
    directive = instructions.render("directive_opening", must_convey=beat["must_convey"])
    reply = await llm().speak(scn_c, beat["speaker"], [], _names(st, scn), directive, meta={"idx": 0, "milestone": MILESTONE_KEYS[0]})
    m0 = {"idx": 0, "speaker": beat["speaker"], "text": reply["text"], "sources": reply.get("sources") or [], "milestone": MILESTONE_KEYS[0], "ts": time.time()}
    await tools.call("business", "init_session", {"session_id": sid, "condition": condition, "message": m0})
    return {"messages": [m0], "milestone_idx": 0}


async def _turn(msg: dict, ctx: TaskContext) -> dict:
    sid, p = msg["sessionId"], msg["payload"]
    st = await tools.call("business", "get_session_state", {"session_id": sid})
    if st["status"] != "active":
        raise NonRetryable("session is not active")
    user_idx = int(p["user_idx"])
    if any(m["idx"] > user_idx for m in st["messages"]):  # already applied by an earlier attempt
        return {"new_messages": [m for m in st["messages"] if m["idx"] > user_idx], "milestone_idx": st["milestone_idx"], "status": st["status"], "skipped": True}
    prior = [m for m in st["messages"] if m["idx"] < user_idx]
    state = {"session": {**st, "messages": prior}, "user_text": p["text"], "user_idx": user_idx,
             "milestone_idx": st["milestone_idx"], "observations": [], "new_messages": []}
    g = (await graphs())["turn"]
    cfg = {"configurable": {"llm": llm(), "thread_id": f"{msg['threadId']}:{msg.get('attempt', 1)}"},
           "recursion_limit": ctx.limits.max_graph_steps, **ctx.tracer.run_config("turn")}
    final = await g.ainvoke(state, config=cfg)
    after, new = final["milestone_idx_after"], final["new_messages"]
    entry = {"key": MILESTONE_KEYS[after], "entered_idx": new[-1]["idx"], "ts": new[-1]["ts"]} if after != st["milestone_idx"] else None
    res = await tools.call("business", "append_turn", {
        "session_id": sid, "new_messages": new, "observations": final.get("observations", []),
        "milestone_idx_after": after, "turns_after": final["turns_after"], "milestone_log_entry": entry,
        "completed": bool(final.get("completed")),
    })
    user_msg = next(m for m in st["messages"] if m["idx"] == user_idx)
    _spawn(_detect_background(sid, user_msg, prior))
    return {"new_messages": new, "milestone_idx": after, "status": res.get("status"), "completed": bool(final.get("completed"))}


async def _detect_background(sid: str, user_msg: dict, prior: list[dict]) -> None:
    try:
        ctx_text = "\n".join(f"[{m['speaker']}] {m['text']}" for m in prior[-8:])
        d = await detector.detect(sid, user_msg["idx"], user_msg["text"], ctx_text, user_msg["milestone"])
        if d and d.get("final"):
            await tools.call("business", "save_detection", {"session_id": sid, "msg_idx": user_msg["idx"], "detection": d}, quiet=True)
    except Exception:
        log.exception("background detection failed")


def _spawn(coro) -> None:
    t = asyncio.create_task(coro)
    _bg.add(t)
    t.add_done_callback(_bg.discard)


async def drain_background() -> None:
    if _bg:
        await asyncio.gather(*list(_bg), return_exceptions=True)


def _report_cfg(msg: dict, ctx_name: str) -> dict:
    ctx = runtime.current()
    return {"configurable": {"llm": llm(), "thread_id": msg["threadId"]}, "recursion_limit": 12, **(ctx.tracer.run_config(ctx_name) if ctx else {})}


async def _report_run(msg: dict) -> dict:
    g = (await graphs())["report"]
    out = await g.ainvoke({"session_id": msg["sessionId"]}, config=_report_cfg(msg, "report"))
    if out.get("__interrupt__"):
        return {"_interrupt": out["__interrupt__"][0].value}
    return {"saved": bool(out.get("saved"))}


async def _report_resume(msg: dict) -> dict:
    g = (await graphs())["report"]
    decision = msg.get("resume") or {"approved": False}
    out = await g.ainvoke(Command(resume=decision), config=_report_cfg(msg, "report.resume"))
    return {"approved": bool(decision.get("approved")), "saved": bool(out.get("saved"))}
