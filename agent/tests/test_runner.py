"""Agent task execution end to end: START -> TURN x N -> REPORT (approval interrupt -> resume)."""
import asyncio
import uuid

import pytest

from app import runner
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
        assert backend.sessions[sid]["report"] is None  # guardrail: nothing saved before approval
        resume = msg("REPORT", sid, mode="RESUME", thread=run["threadId"], resume={"approved": True, "by": "admin:1"})
        resume["taskId"] = run["taskId"]
        await runner.execute(resume)
        return sid, run

    sid, run = asyncio.run(main())
    s = backend.sessions[sid]
    assert s["report"]["status"] == "ready" and s["report"]["approved_by"] == "admin:1"
    assert evs(sink, run["taskId"])[-1]["type"] == "DONE"
    users = [m["idx"] for m in s["messages"] if m["speaker"] == "user"]
    assert set(users) <= {int(k) for k in s["detections"]}, "every candidate message judged by detector-mcp"
    assert s["observations"], "observer evidence stored through business-mcp"
    assert [e["key"] for e in s["milestone_log"]] == ["communicate", "coordinate", "compromise", "persuade"]


def test_rejected_report_is_not_saved_and_finished_session_fails_turn(wired):
    backend, sink = wired["backend"], wired["sink"]

    async def main():
        sid, _ = await start(backend, "delay")
        backend.sessions[sid]["status"] = "completed"
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


def test_change_tool_needs_approval_even_when_called_directly():
    with pytest.raises(guardrails.ApprovalRequired):
        asyncio.run(tools.call("business", "save_report", {"session_id": "abc", "report": {}}))
