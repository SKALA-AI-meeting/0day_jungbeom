"""Report graph with a human approval gate (PDF flow 2: change tool -> save state -> APPROVAL_REQUIRED -> resume).

    START -> load -> backfill -> summarize -> approval (interrupt) -> save -> END

`save` calls business.save_report, a change tool the Guardrails only allow after a person approved it.
The checkpointer keeps the paused state, so approval resumes on the same thread id.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from . import detector
from .graph import traced
from .harness import tools
from .report import build_report
from .scenarios import get_scenario


class ReportState(TypedDict, total=False):
    session_id: str
    state: dict
    report: dict
    decision: dict
    saved: bool


async def load(s: ReportState, config) -> dict:
    return {"state": await tools.call("business", "get_session_state", {"session_id": s["session_id"]})}


async def backfill(s: ReportState, config) -> dict:
    """Judge any candidate message the background detector missed, so the report has full coverage."""
    st = dict(s["state"])
    det = dict(st.get("detections") or {})
    msgs = st.get("messages") or []
    for i, m in enumerate(msgs):
        if m["speaker"] != "user" or (det.get(str(m["idx"])) or {}).get("final"):
            continue
        ctx_text = "\n".join(f"[{x['speaker']}] {x['text']}" for x in msgs[max(0, i - 8):i])
        d = await detector.detect(s["session_id"], m["idx"], m["text"], ctx_text, m["milestone"])
        if d and d.get("final"):
            await tools.call("business", "save_detection", {"session_id": s["session_id"], "msg_idx": m["idx"], "detection": d})
            det[str(m["idx"])] = d
    st["detections"] = det
    return {"state": st}


async def summarize(s: ReportState, config) -> dict:
    st = s["state"]
    llm = config["configurable"]["llm"]
    scn = get_scenario(st["scenario_id"])
    summary = await llm.summarize(scn, st["observations"], st.get("notes") or "")
    return {"report": build_report(st, summary.model_dump())}


def approval(s: ReportState, config) -> dict:
    draft = {c["id"]: {"name": c["name"], "summary": c["summary"], "count": c["count"]} for c in s["report"]["competencies"]}
    decision = interrupt({
        "tool": "business.save_report",
        "args": {"session_id": s["session_id"]},
        "reason": "리포트를 기업에 공개하기 전에 사람이 확인해야 해요.",
        "draft": draft,
    })
    return {"decision": decision if isinstance(decision, dict) else {"approved": bool(decision)}}


async def save(s: ReportState, config) -> dict:
    if not s["decision"].get("approved"):
        return {"saved": False}
    report = {**s["report"], "approved_by": s["decision"].get("by"), "approval_comment": s["decision"].get("comment", "")}
    await tools.call("business", "save_report", {"session_id": s["session_id"], "report": report}, approved=True)
    return {"saved": True}


def build_report_graph(checkpointer=None):
    g = StateGraph(ReportState)
    for name, fn in (("load", load), ("backfill", backfill), ("summarize", summarize), ("save", save)):
        g.add_node(name, traced(fn))
    g.add_node("approval", approval)  # interrupt() must run in the node itself (not wrapped)
    g.add_edge(START, "load")
    g.add_edge("load", "backfill")
    g.add_edge("backfill", "summarize")
    g.add_edge("summarize", "approval")
    g.add_edge("approval", "save")
    g.add_edge("save", END)
    return g.compile(checkpointer=checkpointer)
