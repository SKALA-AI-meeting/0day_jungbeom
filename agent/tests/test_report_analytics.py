"""Analytics through MCP (api-contract §5) from the agent's side: the ANALYTICS task, the quiet snapshot refresh after
START / TURN, and the report graph's analyze step (figures-grounded summaries, charts in the approval and the saved report).
Everything runs end to end through the in-process analytics-mcp and business-mcp against the fake Spring backend."""
import asyncio

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from app import runner
from app.harness import instructions, tools
from app.llm import figures_block
from mcp_servers.analytics import server as analytics_server
from tests.test_runner import evs, msg, start, turn

REPORT_CHARTS = ["timeline", "heatmap", "tki", "checkpoints"]


def _tool_events(sink, task_id: str) -> list[dict]:
    return [e["data"] for e in evs(sink, task_id) if e["type"] in ("TOOL_START", "TOOL_END")]


def _span_names(trace: dict) -> list[str]:
    return [s["name"] for s in trace["spans"] if s["kind"] == "tool"]


async def _completed_session(backend) -> str:
    """START -> TURN x 8 to the end of the persuade milestone (same script as test_runner's full session)."""
    sid, _ = await start(backend)
    for t in ["진행 상황을 공유드릴게요. 검토 범위가 어디까지인가요?", "오늘 안에 확인해서 알려드릴게요.",
              "두 분 의견을 나눠서 정리해 볼게요.", "검토팀에 부분 검토를 요청할게요."]:
        await turn(backend, sid, t)
    await turn(backend, sid, "일정은 미루고 고객사에 먼저 알릴게요.", choice="a")
    for t in ["일정 변경은 오늘 문서에 반영할게요.", "근거를 정리해서 공유할게요.", "정리하면 화요일 검토 후 출시예요."]:
        await turn(backend, sid, t)
    await runner.drain_background()
    assert backend.sessions[sid]["status"] == "completed"
    return sid


def test_analytics_task_stores_a_snapshot_and_spring_keeps_the_newest(wired):
    backend, sink = wired["backend"], wired["sink"]

    async def main():
        sid, _ = await start(backend, "conflict")
        await runner.drain_background()
        first = backend.analytics[sid]
        art = backend.sessions[sid]["artifacts"][0]
        backend.annotate(sid, art["id"], line_start=1, text="이 줄 근거가 궁금해요.")  # Spring bumps state_rev -> stale
        assert backend.analytics_status(sid) == "stale"
        m = msg("ANALYTICS", sid)
        await runner.execute(m)
        older = await tools.call("business", "save_analytics", {"session_id": sid, "analytics": first})
        return sid, m, first, older

    sid, m, first, older = asyncio.run(main())
    done = evs(sink, m["taskId"])[-1]
    assert done["type"] == "DONE" and done["data"]["stored"] is True
    snap = backend.analytics[sid]
    assert backend.analytics_status(sid) == "fresh" and snap["source"]["annotation_count"] == 1
    assert done["data"]["figures"] == snap["figures"] and snap["version"] == 1 and snap["session_id"] == sid
    assert older == {"stored": False} and backend.analytics_puts[-1] == (sid, first["source"]["state_rev"], False)
    assert snap["source"]["state_rev"] > first["source"]["state_rev"], "an older state_rev never replaces a newer snapshot"
    tools_seen = [e["tool"] for e in _tool_events(sink, m["taskId"]) if "args" in e]
    assert tools_seen == ["analytics.session_analytics", "business.save_analytics"]
    save_args = next(e["args"] for e in _tool_events(sink, m["taskId"]) if e.get("tool") == "business.save_analytics" and "args" in e)
    assert isinstance(save_args["analytics"], str) and save_args["analytics"].startswith("["), "the bundle is summarized by size in events"
    assert {"analytics.session_analytics", "business.save_analytics"} <= set(_span_names(done["data"]["trace"]))


def test_analytics_task_for_an_unknown_session_fails_without_retry(wired):
    sink = wired["sink"]
    m = msg("ANALYTICS", "0000deadbeef")
    with pytest.raises(runner.NonRetryable):
        asyncio.run(runner.execute(m, final_attempt=False))
    last = evs(sink, m["taskId"])[-1]
    assert last["type"] == "FAILED" and "404" in last["data"]["error"]


def test_turn_refreshes_the_snapshot_after_its_detection(wired):
    backend, sink = wired["backend"], wired["sink"]

    async def main():
        sid, _ = await start(backend)
        t = await turn(backend, sid, "진행 상황을 공유드릴게요. 검토 범위가 어디까지인가요?")
        await runner.drain_background()
        return sid, t

    sid, t = asyncio.run(main())
    s, snap = backend.sessions[sid], backend.analytics[sid]
    user_idx = next(m["idx"] for m in s["messages"] if m["speaker"] == "user")
    assert str(user_idx) in s["detections"], "background detection ran"
    assert snap["source"]["state_rev"] == s["state_rev"] and snap["source"]["detection_count"] == 1, "refreshed after the detection, so fresh"
    assert snap["source"]["message_count"] == len(s["messages"]) and snap["figures"]["candidate_messages"] == 1
    assert not any(str(e.get("tool", "")).startswith("analytics.") or e.get("tool") == "business.save_analytics"
                   for e in _tool_events(sink, t["taskId"])), "the candidate's TURN stream never shows the analytics refresh"
    assert evs(sink, t["taskId"])[-1]["type"] == "DONE"


def test_snapshot_failure_never_blocks_the_turn(wired):
    backend, sink = wired["backend"], wired["sink"]
    broken = FastMCP("analytics-down")

    @broken.tool
    async def session_analytics(session_id: str) -> dict:
        raise ToolError("503 analytics-mcp unreachable")

    async def main():
        sid, _ = await start(backend)
        await runner.drain_background()
        before = backend.analytics[sid]
        original = tools._override["analytics"]
        tools.use_in_process("analytics", broken)
        try:
            t = await turn(backend, sid, "오늘 안에 확인해서 알려드릴게요.")
            await runner.drain_background()
        finally:
            tools.use_in_process("analytics", original)
        return sid, t, before

    sid, t, before = asyncio.run(main())
    assert evs(sink, t["taskId"])[-1]["type"] == "DONE" and len(backend.sessions[sid]["messages"]) >= 3
    assert backend.analytics[sid] is before and backend.analytics_status(sid) == "stale", "failure only logged; the admin sees a stale snapshot"


def test_report_is_grounded_in_analytics_and_publishes_its_charts(wired):
    backend, sink = wired["backend"], wired["sink"]

    async def main():
        sid = await _completed_session(backend)
        run = msg("REPORT", sid)
        await runner.execute(run)
        ask = evs(sink, run["taskId"])[-1]
        resume = msg("REPORT", sid, mode="RESUME", thread=run["threadId"], resume={"approved": True, "by": "admin:7"})
        resume["taskId"] = run["taskId"]
        await runner.execute(resume)
        return sid, run, ask

    sid, run, ask = asyncio.run(main())
    assert ask["type"] == "APPROVAL_REQUIRED"
    data = ask["data"]
    assert [c["chart_id"] for c in data["charts"]] == REPORT_CHARTS
    assert all(set(c) == {"chart_id", "title", "svg"} and c["svg"].lstrip().startswith("<svg") and c["title"] for c in data["charts"])
    figs = data["figures"]
    obs = backend.sessions[sid]["observations"]
    assert figs["observations"] == len(obs) and figs["milestones_reached"] == "4/4"
    grounded = [d["summary"] for d in data["draft"].values() if d["count"]]
    assert grounded and all(f"세션 관찰 {len(obs)}건" in x for x in grounded), "summaries quote the bundle's figures"
    names = _span_names(data["trace"])
    assert names.count("analytics.session_analytics") == 1 and names.count("analytics.render_charts") == 1, "one call draws all report charts"
    assert "analytics.render_chart" not in names

    s = backend.sessions[sid]
    rep = s["report"]
    assert rep["approved_by"] == "admin:7" and rep["figures"] == figs and rep["charts"] == data["charts"]
    assert isinstance(rep["analytics_rev"], int) and rep["analytics_rev"] < s["state_rev"]
    done = evs(sink, run["taskId"])[-1]
    assert done["type"] == "DONE" and done["data"]["saved"] is True
    assert "business.save_analytics" in _span_names(done["data"]["trace"])
    assert backend.analytics_status(sid) == "fresh", "the snapshot is recomputed after save_report bumped state_rev"


def test_report_saved_even_if_analytics_is_down_at_approval(wired):
    backend, sink = wired["backend"], wired["sink"]
    broken = FastMCP("analytics-down")

    @broken.tool
    async def session_analytics(session_id: str) -> dict:
        raise ToolError("503 analytics-mcp unreachable")

    async def main():
        sid, _ = await start(backend, "delay")
        await runner.drain_background()
        backend.set_status(sid, "completed")
        run = msg("REPORT", sid)
        await runner.execute(run)
        original = tools._override["analytics"]
        tools.use_in_process("analytics", broken)
        try:
            resume = msg("REPORT", sid, mode="RESUME", thread=run["threadId"], resume={"approved": True, "by": "admin:2"})
            resume["taskId"] = run["taskId"]
            await runner.execute(resume)
        finally:
            tools.use_in_process("analytics", original)
        return sid, run

    sid, run = asyncio.run(main())
    s = backend.sessions[sid]
    assert evs(sink, run["taskId"])[-1]["type"] == "DONE" and s["report"]["approved_by"] == "admin:2"
    assert backend.analytics[sid]["source"]["state_rev"] == s["report"]["analytics_rev"], "kept the report's own bundle"
    assert backend.analytics_status(sid) == "stale"


def test_report_is_drafted_without_analytics_when_analytics_mcp_is_down(wired):
    """analytics-mcp is not a single point of failure for the report: the draft goes on without figures and charts."""
    backend, sink = wired["backend"], wired["sink"]
    broken = FastMCP("analytics-down")

    @broken.tool
    async def session_analytics(session_id: str) -> dict:
        raise ToolError("503 analytics-mcp unreachable")

    @broken.tool
    async def render_charts(session_id: str, chart_ids: list[str]) -> dict:
        raise ToolError("503 analytics-mcp unreachable")

    async def main():
        sid, _ = await start(backend, "delay")
        await turn(backend, sid, "진행 상황을 공유드릴게요. 검토 범위가 어디까지인가요?")
        await runner.drain_background()
        backend.set_status(sid, "completed")
        original = tools._override["analytics"]
        tools.use_in_process("analytics", broken)
        try:
            run = msg("REPORT", sid)
            await runner.execute(run)
        finally:
            tools.use_in_process("analytics", original)
        ask = evs(sink, run["taskId"])[-1]
        resume = msg("REPORT", sid, mode="RESUME", thread=run["threadId"], resume={"approved": True, "by": "admin:3"})
        resume["taskId"] = run["taskId"]
        await runner.execute(resume)
        return sid, run, ask

    sid, run, ask = asyncio.run(main())
    assert ask["type"] == "APPROVAL_REQUIRED", ask
    assert ask["data"]["figures"] is None and ask["data"]["charts"] == [] and ask["data"]["draft"]
    assert ask["data"]["trace"]["fallbacks"] >= 1, "the task history shows the report recovered"
    rep = backend.sessions[sid]["report"]
    assert evs(sink, run["taskId"])[-1]["type"] == "DONE" and rep["approved_by"] == "admin:3"
    assert rep["figures"] is None and rep["charts"] == [] and rep["analytics_rev"] is None
    assert backend.analytics_status(sid) == "fresh", "analytics-mcp is back at approval: the snapshot is stored after the save"


def test_report_rereads_when_its_charts_come_from_a_newer_state(wired):
    """figures and charts are two state reads; a change landing in between (a late detection) makes analyze read the pair again."""
    backend, sink = wired["backend"], wired["sink"]
    flaky = FastMCP("analytics-flaky")
    renders = []

    async def real(tool: str, args: dict) -> dict:
        async with Client(analytics_server.mcp) as c:
            return (await c.call_tool(tool, args)).data

    @flaky.tool
    async def session_analytics(session_id: str) -> dict:
        return await real("session_analytics", {"session_id": session_id})

    @flaky.tool
    async def render_charts(session_id: str, chart_ids: list[str]) -> dict:
        renders.append(session_id)
        if len(renders) == 1:
            backend._bump(backend.sessions[session_id])  # something that affects analytics lands between the two reads
        return await real("render_charts", {"session_id": session_id, "chart_ids": chart_ids})

    async def main():
        sid = await _completed_session(backend)
        original = tools._override["analytics"]
        tools.use_in_process("analytics", flaky)
        try:
            run = msg("REPORT", sid)
            await runner.execute(run)
        finally:
            tools.use_in_process("analytics", original)
        return sid, evs(sink, run["taskId"])[-1]

    sid, ask = asyncio.run(main())
    assert ask["type"] == "APPROVAL_REQUIRED" and len(renders) == 2
    names = _span_names(ask["data"]["trace"])
    assert names.count("analytics.session_analytics") == 2 and names.count("analytics.render_charts") == 2
    assert [c["chart_id"] for c in ask["data"]["charts"]] == REPORT_CHARTS


def test_analytics_tools_are_held_to_the_same_tool_cap(wired):
    """No exemption: a runaway loop over analytics.* stops at the cap like any other read-only tool."""
    from app.harness import runtime
    from app.harness.events import EventPublisher, MemorySink
    from app.harness.loop import LimitExceeded
    from app.harness.observability import Tracer
    from app.harness.runtime import TaskContext

    async def main():
        ctx = TaskContext("cap", None, 1, EventPublisher("cap", MemorySink()), Tracer("cap"))
        token = runtime.bind(ctx)
        try:
            for _ in range(ctx.limits.max_same_tool):
                await tools.call("analytics", "describe_charts", {})
            with pytest.raises(LimitExceeded):
                await tools.call("analytics", "describe_charts", {})
        finally:
            runtime.unbind(token)

    asyncio.run(main())


def test_save_analytics_validates_the_bundle(wired):
    backend = wired["backend"]
    sid = "a1b2c3d4e5f6"
    backend.create(sid, "delay")

    async def call(bundle):
        return await tools.call("business", "save_analytics", {"session_id": sid, "analytics": bundle})

    full = {"version": 1, "session_id": sid, "source": {"state_rev": 0}, "row": {}, "heatmap": {"cells": []}, "figures": {"messages": 0},
            "timeline": [{"key": "communicate"}], "charts": [{"id": "timeline", "available": False}]}
    partial = [{"version": 2}, {"version": True}, {"source": None}, {"source": {"state_rev": "0"}}, {"source": {"state_rev": 0.0}},
               {"session_id": "other"}, {"session_id": None}, {"row": None}, {"figures": []}, {"timeline": []}, {"charts": None}]
    for change in partial:
        with pytest.raises(tools.ToolFailure, match="400"):
            asyncio.run(call({**full, **change}))
    with pytest.raises(tools.ToolFailure, match="400"):
        asyncio.run(call({"version": 1, "session_id": sid, "source": {"state_rev": 0}}))  # only a rev: never a fresh snapshot
    assert asyncio.run(call(full)) == {"stored": True}


def test_figures_prompt_block_quotes_values_verbatim():
    figs = {"messages": 17, "candidate_messages": 8, "observations": 9, "by_signal": {"positive": 5, "neutral": 3, "risk": 1},
            "pooled_kappa": 0.31, "tki_estimate": "compromising", "checkpoints": None, "milestones_reached": "3/4"}
    block = figures_block(figs)
    assert "- 관찰 근거: 9" in block and "긍정 5 · 중립 3 · 확인 필요 1" in block and "타협형 (compromising)" in block
    assert "- 관찰자-디텍터 일치도(κ): 0.31" in block and "- 같이 본 과제의 확인 지점 표시: 없음" in block
    assert figures_block(None) == "(없음)"
    human = instructions.render("summarize_input", figures=block, rows="- C01 …", notes="(없음)")
    assert "$" not in human and "도달한 단계: 3/4" in human
    assert "$" not in instructions.render("summarize", competencies="- C01")
