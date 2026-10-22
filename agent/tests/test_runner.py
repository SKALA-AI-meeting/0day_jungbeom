"""Agent task execution end to end: START -> TURN x N -> REPORT (approval interrupt -> resume), plus the handler registry."""
import asyncio
import time
import uuid

import pytest

from app import runner
from app.handlers import Handler, Registry
from app.harness import guardrails, tools


def evs(sink, tid):
    return [e for t, e in sink.events if t == tid]


def msg(type_, sid, payload=None, mode="RUN", thread=None, resume=None):
    tid = str(uuid.uuid4())
    m = {"taskId": tid, "type": type_, "sessionId": sid, "threadId": thread or f"{type_.lower()}:{tid}", "mode": mode, "payload": payload or {}}
    if resume is not None:
        m["resume"] = resume
    return m


async def start(backend, scenario="dl.pm.fintech"):
    sid = uuid.uuid4().hex[:12]
    backend.create(sid, scenario)
    m = msg("START", sid)
    await runner.execute(m)
    return sid, m


async def turn(backend, sid, text, choice=None):
    idx = backend.user_message(sid, text, choice)
    m = msg("TURN", sid, {"text": text, "user_idx": idx, "choice_id": choice or ""})
    await runner.execute(m)
    return m


def test_start_allocates_condition_and_streams_opening(wired):
    backend, sink = wired["backend"], wired["sink"]

    async def main():
        sid, m = await start(backend)
        await runner.drain_background()
        return sid, m

    sid, m = asyncio.run(main())
    s = backend.sessions[sid]
    assert s["condition"]["lead"] != s["condition"]["peer"] and s["condition"]["stratum"] == "V2"
    types = [e["type"] for e in evs(sink, m["taskId"])]
    assert "TOKEN" in types and types[-1] == "DONE"
    assert "TOOL_START" in types  # business + rag tools are announced
    done = evs(sink, m["taskId"])[-1]["data"]
    assert done["trace"]["trace_id"] == m["taskId"] and "directive_opening" in done["trace"]["prompt_versions"]
    assert s["messages"][0]["sources"], "opening line is grounded on a company document (rag-mcp)"
    assert backend.analytics_status(sid) == "fresh", "START refreshes the admin snapshot in the background"
    assert not any(str(e["data"].get("tool", "")).startswith("analytics.") or e["data"].get("tool") == "business.save_analytics"
                   for e in evs(sink, m["taskId"])), "the refresh is quiet: nothing about it reaches the candidate's stream"


def test_full_session_choice_and_report_approval(wired):
    backend, sink = wired["backend"], wired["sink"]

    async def main():
        sid, _ = await start(backend)
        for t in ["진행 상황을 공유드릴게요. 검토 범위가 어디까지인가요?", "오늘 안에 확인해서 알려드릴게요."]:
            await turn(backend, sid, t)
        for t in ["두 분 의견을 나눠서 정리해 볼게요.", "검토팀에 부분 검토를 요청할게요."]:
            await turn(backend, sid, t)
        assert backend.sessions[sid]["milestone_idx"] == 2
        await turn(backend, sid, "일정은 미루고 고객사에 먼저 알릴게요.", choice="a")
        await turn(backend, sid, "일정 변경은 오늘 문서에 반영할게요.")
        assert backend.sessions[sid]["milestone_idx"] == 3
        persuade = [m for m in backend.sessions[sid]["messages"] if m["milestone"] == "persuade"][0]
        assert persuade["speaker"] == "peer"  # chose pole a (원칙) -> 파격 persona pushes back
        for t in ["근거를 정리해서 공유할게요.", "정리하면 화요일 검토 후 출시예요."]:
            await turn(backend, sid, t)
        await runner.drain_background()
        assert backend.sessions[sid]["status"] == "completed"

        run = msg("REPORT", sid)
        await runner.execute(run)
        last = evs(sink, run["taskId"])[-1]
        assert last["type"] == "APPROVAL_REQUIRED" and last["data"]["tool"] == "business.save_report"
        assert last["data"]["figures"] and [c["chart_id"] for c in last["data"]["charts"]] == ["timeline", "heatmap", "tki", "checkpoints"]
        assert backend.sessions[sid]["report"] is None  # guardrail: nothing saved before approval
        resume = msg("REPORT", sid, mode="RESUME", thread=run["threadId"], resume={"approved": True, "by": "admin:1"})
        resume["taskId"] = run["taskId"]
        await runner.execute(resume)
        return sid, run

    sid, run = asyncio.run(main())
    s = backend.sessions[sid]
    assert s["report"]["status"] == "ready" and s["report"]["approved_by"] == "admin:1"
    assert len(s["report"]["charts"]) == 4 and backend.analytics_status(sid) == "fresh"
    assert evs(sink, run["taskId"])[-1]["type"] == "DONE"
    users = [m["idx"] for m in s["messages"] if m["speaker"] == "user"]
    assert set(users) <= {int(k) for k in s["detections"]}, "every candidate message judged by detector-mcp"
    assert s["observations"], "observer evidence stored through business-mcp"
    assert [e["key"] for e in s["milestone_log"]] == ["communicate", "coordinate", "compromise", "persuade"]


def test_rejected_report_is_not_saved_and_finished_session_fails_turn(wired):
    backend, sink = wired["backend"], wired["sink"]

    async def main():
        sid, _ = await start(backend, "delay")
        backend.set_status(sid, "completed")
        run = msg("REPORT", sid)
        await runner.execute(run)
        resume = msg("REPORT", sid, mode="RESUME", thread=run["threadId"], resume={"approved": False})
        resume["taskId"] = run["taskId"]
        await runner.execute(resume)
        t = await turn(backend, sid, "더 말해도 되나요?")
        return sid, run, t

    sid, run, t = asyncio.run(main())
    assert backend.sessions[sid]["report"] is None
    assert evs(sink, run["taskId"])[-1]["data"]["approved"] is False
    assert evs(sink, t["taskId"])[-1]["type"] == "FAILED"
    assert backend.analytics[sid]["source"]["state_rev"] >= 1, "a rejected draft still leaves the admin snapshot"


def test_change_tool_needs_approval_even_when_called_directly():
    with pytest.raises(guardrails.ApprovalRequired):
        asyncio.run(tools.call("business", "save_report", {"session_id": "abc", "report": {}}))


def test_unknown_type_and_resume_of_a_run_only_type_fail_without_retry(wired):
    sink = wired["sink"]
    unknown, start_resume = msg("NOPE", "abc"), msg("START", "abc", mode="RESUME")
    asyncio.run(runner.execute(unknown))
    with pytest.raises(runner.NonRetryable):
        asyncio.run(runner.execute(start_resume, final_attempt=False))
    assert evs(sink, unknown["taskId"])[-1]["type"] == "FAILED" and "unknown task type" in evs(sink, unknown["taskId"])[-1]["data"]["error"]
    assert evs(sink, start_resume["taskId"])[-1]["type"] == "FAILED"


def test_handlers_registry():
    assert list(runner.HANDLERS) == ["START", "TURN", "REPORT", "ACCOUNT_REVIEW", "ANALYTICS"]
    assert {h["type"]: h["resumable"] for h in runner.HANDLERS.describe()} == {"START": False, "TURN": False, "REPORT": True, "ACCOUNT_REVIEW": True,
                                                                              "ANALYTICS": False}
    assert all(h["description"] for h in runner.HANDLERS.describe())
    with pytest.raises(ValueError):
        Registry([Handler("START", runner.HANDLERS["START"].run), Handler("START", runner.HANDLERS["START"].run)])
    with pytest.raises(ValueError):
        Registry([Handler("start", runner.HANDLERS["START"].run)])


class _StubTurnGraph:
    """Stands in for the turn graph to check what runner._turn sends to append_turn (the real graph is tested elsewhere)."""

    def __init__(self) -> None:
        self.final_extra: dict = {}
        self.seen: list[dict] = []

    async def ainvoke(self, state, config):
        self.seen.append(state["session"])
        m = {"idx": state["user_idx"] + 1, "speaker": "lead", "text": "네, 그렇게 정리해 볼게요.", "milestone": "communicate", "ts": time.time()}
        return {"new_messages": [m], "observations": [], "milestone_idx_after": state["milestone_idx"], "turns_after": 1, **self.final_extra}


def test_turn_passes_the_dialogue_ledger_only_when_present(wired):
    backend = wired["backend"]
    stub = _StubTurnGraph()
    ledger = {"version": 1, "summary": "", "issues": [{"id": "i1", "title": "검토 범위", "status": "open", "raised_by": "user", "last_idx": 1}],
              "commitments": [], "positions": {}, "turns": {"lead": {"last_idx": 2, "count": 1}}, "markups_seen": [], "cited": []}

    async def main():
        gs = await runner.graphs()
        original, gs["turn"] = gs["turn"], stub
        try:
            sid, _ = await start(backend)
            stub.final_extra = {"dialogue": ledger}
            first = await turn(backend, sid, "검토 범위가 어디까지인가요?")
            after_first = backend.sessions[sid]["dialogue"]
            stub.final_extra = {}
            await turn(backend, sid, "오늘 안에 정리해서 공유할게요.")
            await runner.drain_background()
            return sid, after_first, first
        finally:
            gs["turn"] = original

    sid, after_first, first = asyncio.run(main())
    assert after_first == ledger and backend.sessions[sid]["dialogue"] == ledger, "no dialogue in the final state keeps the stored one"
    streamed = [e["data"].get("args") or {} for e in evs(wired["sink"], first["taskId"])]
    assert not any("dialogue" in a or "observations" in a for a in streamed), "the candidate's TURN stream never carries the ledger or evidence"
    assert stub.seen[1]["dialogue"] == ledger and len(stub.seen[0]["artifacts"]) == 3, "the graph sees ledger + artifacts from Spring"
