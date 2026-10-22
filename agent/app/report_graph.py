"""Report graph with a human approval gate (PDF flow 2: change tool -> save state -> APPROVAL_REQUIRED -> resume).

    START -> load -> backfill -> analyze -> summarize -> approval (interrupt) -> save -> END

`analyze` asks analytics-mcp for the session's numbers (analytics.session_analytics) and renders the report charts in
one call (analytics.render_charts: timeline, heatmap, tki, checkpoints; a chart the bundle marks unavailable is skipped),
so the same-tool cap holds. If analytics-mcp is down the draft goes on without figures and charts.
`summarize` gets the bundle's `figures` as context, and the approval payload carries the same figures and charts,
so the person approves exactly what will be published.
`save` calls business.save_report, a change tool the Guardrails only allow after a person approved it, then stores the
admin snapshot (business.save_analytics). The snapshot is derived data: its failure is logged, never fails the report.
The checkpointer keeps the paused state, so approval resumes on the same thread id.
"""
from __future__ import annotations

import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from . import detector
from .graph import traced
from .harness import runtime, tools
from .report import build_report
from .scenarios import get_scenario

log = logging.getLogger("dayzero.report")
REPORT_CHARTS = ("timeline", "heatmap", "tki", "checkpoints")  # in report order; `agreement` stays on the admin screen


class ReportState(TypedDict, total=False):
    session_id: str
    state: dict
    analytics: dict  # analytics bundle v1 (api-contract §5)
    charts: list[dict]  # [{chart_id, title, svg}]
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


async def analyze(s: ReportState, config) -> dict:
    """Numbers and charts come from analytics-mcp (after backfill, so the detector panels include every judgement).

    Two calls: session_analytics (figures) and render_charts (all report charts drawn from one state read). Each reads
    Spring's state on its own, so a late detection landing in between would give charts newer than the figures; the
    pair is then read once more (both carry source.state_rev). analytics-mcp down -> the draft goes on without figures
    and charts (the approval card and the report handle null / []), noted in the trace: the report needs the LLM and
    business-mcp, the analytics are its illustration.
    """
    sid = s["session_id"]
    try:
        for attempt in (1, 2):
            bundle = await tools.call("analytics", "session_analytics", {"session_id": sid})
            rev = (bundle.get("source") or {}).get("state_rev")
            wanted = [c.get("id") for c in bundle.get("charts") or [] if c.get("available") and c.get("id") in REPORT_CHARTS]
            if not wanted:
                return {"analytics": bundle, "charts": []}
            drawn = await tools.call("analytics", "render_charts", {"session_id": sid, "chart_ids": [c for c in REPORT_CHARTS if c in wanted]})
            if drawn.get("state_rev") == rev:
                break
            log.info("report %s: charts drawn at state_rev %s, figures at %s (attempt %d)", sid, drawn.get("state_rev"), rev, attempt)
        else:
            _note("analytics_rev_mismatch")  # still moving after a second read: keep the latest pair, provenance = the figures' rev
    except tools.ToolFailure:
        log.warning("analytics-mcp unavailable for the report of %s; drafting without figures and charts", sid, exc_info=True)
        _note("analytics_unavailable")
        _note("fallback")  # counted in the trace summary: the task history shows the report recovered from a failure
        return {"analytics": None, "charts": []}
    charts = [{"chart_id": c.get("chart_id"), "title": c.get("title") or "", "svg": c["svg"]}
              for c in drawn.get("charts") or [] if c.get("available") and c.get("svg")]
    return {"analytics": bundle, "charts": charts}


def _note(key: str) -> None:
    ctx = runtime.current()
    if ctx:
        ctx.tracer.note(key)


async def summarize(s: ReportState, config) -> dict:
    st = s["state"]
    llm = config["configurable"]["llm"]
    scn = get_scenario(st["scenario_id"])
    bundle = s.get("analytics") or {}
    figures = bundle.get("figures")
    summary = await llm.summarize(scn, st["observations"], st.get("notes") or "", figures=figures)
    rev = (bundle.get("source") or {}).get("state_rev")
    return {"report": build_report(st, summary.model_dump(), figures=figures, charts=s.get("charts") or [], analytics_rev=rev)}


def approval(s: ReportState, config) -> dict:
    draft = {c["id"]: {"name": c["name"], "summary": c["summary"], "count": c["count"]} for c in s["report"]["competencies"]}
    decision = interrupt({
        "tool": "business.save_report",
        "args": {"session_id": s["session_id"]},
        "reason": "리포트를 기업에 공개하기 전에 사람이 확인해야 해요.",
        "draft": draft,
        "figures": s["report"].get("figures"),
        "charts": s["report"].get("charts") or [],
    })
    return {"decision": decision if isinstance(decision, dict) else {"approved": bool(decision)}}


async def save(s: ReportState, config) -> dict:
    saved = False
    if s["decision"].get("approved"):
        report = {**s["report"], "approved_by": s["decision"].get("by"), "approval_comment": s["decision"].get("comment", "")}
        await tools.call("business", "save_report", {"session_id": s["session_id"], "report": report}, approved=True)
        saved = True
    # Saving the report bumps Spring's state_rev, so the bundle is recomputed to land fresh; a rejected draft keeps the analyze one.
    await _store_snapshot(s["session_id"], s.get("analytics"), recompute=saved)
    return {"saved": saved}


async def _store_snapshot(sid: str, bundle: dict | None, *, recompute: bool) -> None:
    try:
        if recompute or not bundle:
            try:
                bundle = await tools.call("analytics", "session_analytics", {"session_id": sid})
            except Exception:
                log.warning("analytics recompute failed for %s; storing the report's bundle (stale beats missing)", sid, exc_info=True)
        if bundle:
            await tools.call("business", "save_analytics", {"session_id": sid, "analytics": bundle})
    except Exception:
        log.exception("analytics snapshot after the report failed for %s", sid)
        _note("analytics_snapshot_failed")


def build_report_graph(checkpointer=None):
    g = StateGraph(ReportState)
    for name, fn in (("load", load), ("backfill", backfill), ("analyze", analyze), ("summarize", summarize), ("save", save)):
        g.add_node(name, traced(fn))
    g.add_node("approval", approval)  # interrupt() must run in the node itself (not wrapped)
    g.add_edge(START, "load")
    g.add_edge("load", "backfill")
    g.add_edge("backfill", "analyze")
    g.add_edge("analyze", "summarize")
    g.add_edge("summarize", "approval")
    g.add_edge("approval", "save")
    g.add_edge("save", END)
    return g.compile(checkpointer=checkpointer)
