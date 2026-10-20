"""완료 기준(M2 복구·미합의): api 재시작 후 fired 이벤트 재실행과 /state 이어하기(같은 run_id에
버전이
늘지 않음), 강제 LLM 실패 3회에 세션 failed(일반 응답은 폴백 seq 9), 문서 제공 실패(send 2회 실패 →
document_missing, 끝내 실패하면 카드 failed), 미합의 중 카드 도래(기본안 확정)와 반대 의견 대체
대상,
지시 반영 검사 1회 재생성.

검증 방식: FakeLLM(Brain) + 격리 DB + 실제 MCP 하위 프로세스. 시계는 script_driver로 당긴다.
"""

import uuid

import pytest
from app.agent.mcp_client import McpClient, fail
from app.agent.runner import DOCUMENT_MISSING, Stimulus
from app.agent.session import cards
from app.agent.session.graph import thread_id
from app.agent.session.nodes import FALLBACK_TEXT
from app.agent.session.runner import SessionAgentRunner
from app.agent.session.store import DbAgentStore
from app.db import make_session_factory
from app.models import (
    AgentRun,
    Document,
    DocumentVersion,
    Message,
    Observation,
    Session,
    SessionEvent,
)
from app.services.messages import accept_candidate_message
from app.services.runs import run_agent
from sqlalchemy import select

from tests.agent.brain import Brain, cls, instr
from tests.agent.script_driver import Driver, start
from tests.agent.test_session_scripts import rows, stack_scenario

PARTS = {"1": "candidate", "2": "candidate", "3": "both", "4": "colleague", "5": "colleague"}
BOARD = [{"part_no": int(no), "assignee": who} for no, who in PARTS.items()]


async def event(db, session_id, card_id) -> SessionEvent:
    return await db.scalar(
        select(SessionEvent)
        .where(SessionEvent.session_id == session_id, SessionEvent.card_id == card_id)
        .execution_options(populate_existing=True)
    )


async def versions(db, session_id) -> dict[int, list[int]]:
    docs = await rows(
        db, Document, Document.session_id == session_id, Document.owner == "colleague"
    )
    return {
        d.part_no: [
            v.version for v in await rows(db, DocumentVersion, DocumentVersion.doc_id == d.id)
        ]
        for d in docs
    }


class Crash(Exception):
    """프로세스가 죽은 것처럼 실행을 끊는다(그래프 밖으로 올라감)."""


REVISE = "4번 사례 하나만 후속 모임 제안 기능 있는 서비스로 바꿔 주세요."


async def test_restart_reruns_fired_card_without_duplicates(
    stack, service, make_position, db, monkeypatch
):
    stack.llm.default = Brain({REVISE: cls("doc_feedback", part_no=4, wants_revision=True)})
    driver = await start(stack, service, make_position, ["planning"], 6)
    await driver.advance_to(0.2)
    await driver.do({"board": BOARD}, 0)
    await driver.advance_to(1.4)
    sid = driver.session_id

    # 재시작 직전: 중간 점검(1.5분)을 fired로 집고 문서 3개를 보낸 뒤 공유 메시지 전에 죽음
    checkin = await event(db, sid, "planning_checkin")
    run_id = uuid.uuid4()
    checkin.status, checkin.fired_at, checkin.run_id, checkin.attempts = (
        "fired",
        checkin.due_at,
        run_id,
        1,
    )
    db.add(AgentRun(run_id=run_id, session_id=sid, stimulus="event", ref_ids=[checkin.id]))
    await db.commit()
    await driver.advance_to(1.5)

    original = cards.post

    async def crash_on_share(deps, state, **kwargs):
        if kwargs.get("event_id") and kwargs.get("node") == "inject":
            raise Crash
        return await original(deps, state, **kwargs)

    monkeypatch.setattr(cards, "post", crash_on_share)
    with pytest.raises(Crash):
        await stack.runner.run(sid, Stimulus("event", event_ids=(checkin.id,)), run_id)
    monkeypatch.setattr(cards, "post", original)
    assert await versions(db, sid) == {3: [1], 4: [1], 5: [1]}

    # 재시작: 새 러너(새 체크포인터 연결), 60초 뒤 스케줄러가 같은 run_id로 다시 실행
    await stack.runner.aclose()
    stack.ctx.runner = SessionAgentRunner(
        llm=stack.llm,
        mcp_urls=stack.servers.mcp_urls,
        store=DbAgentStore(make_session_factory(stack.ctx.engine)),
        database_url=str(stack.ctx.engine.url.render_as_string(hide_password=False)),
        broadcast=stack.hub.broadcast,
    )
    stack.runner = stack.ctx.runner
    await driver.shift(1.1)
    await driver.settle()

    checkin = await event(db, sid, "planning_checkin")
    assert (checkin.status, checkin.run_id, checkin.attempts) == ("done", run_id, 2)
    assert await versions(db, sid) == {
        3: [1],
        4: [1],
        5: [1],
    }  # 같은 run_id 재실행에 버전이 늘지 않음
    posted = await rows(db, Message, Message.session_id == sid, Message.run_id == run_id)
    assert sorted(m.seq for m in posted) == [1, 30, 40, 50]
    async with driver.client() as http:
        state = await http.get(f"/sessions/{sid}/state")
    assert state.status_code == 200
    assert [m["event_id"] for m in state.json()["messages"]].count(str(checkin.id)) == 4

    # 작업 기억도 실제 보낸 버전으로 복원돼(R2) 리뷰 v2 → 답글 v3까지 이어진다
    graph = await stack.runner.graph()
    notes = (await graph.aget_state({"configurable": {"thread_id": thread_id(sid)}})).values[
        "work_notes"
    ]
    assert notes["sent"] == {"3": 1, "4": 1, "5": 1}
    assert notes["progress"] == {p: "v1까지 보낸 상태" for p in ("3", "4", "5")}
    await driver.advance_to(4.6)
    async with driver.client() as http:
        reply = {"channel": "dm", "content": REVISE, "reply_to_doc": {"part_no": 4, "version": 2}}
        await driver.say(reply, "r1", http)
    assert await versions(db, sid) == {3: [1, 2], 4: [1, 2, 3], 5: [1, 2]}


def always_fail(messages):
    raise RuntimeError("forced llm failure")


async def test_llm_failing_three_times_fails_session(stack, service, make_position, db):
    stack.llm.default = always_fail
    position = await make_position(["collaboration"], 6)
    session, _, _ = await service.create_for_invite(position.id, "A", "a@example.com")
    await service.consent(session.id)
    await service.start(session.id)
    async with stack.ctx.session_factory() as session_db:
        message, run_id, _ = await accept_candidate_message(
            session_db, stack.hub, session.id, "c-1", "dm", "도현님 안녕하세요"
        )
    async with stack.ctx.session_factory() as session_db:
        result = await run_agent(
            session_db,
            stack.runner,
            stack.ctx.locks,
            session.id,
            Stimulus("message", message.id),
            run_id,
        )
    assert result.ok and result.fallback_used
    [reply] = await rows(
        db, Message, Message.session_id == session.id, Message.sender == "colleague"
    )
    assert (reply.content, reply.seq) == (FALLBACK_TEXT, 9)

    driver = Driver(stack, session.id, "", 6)
    await (
        driver.settle()
    )  # 킥오프 카드: 재시도 2회(1·3초는 FakeLLM에서 0초) 뒤 실패, 같은 run_id로 3회
    ended = await db.get(Session, session.id, populate_existing=True)
    kickoff = await event(db, session.id, "kickoff")
    assert (kickoff.status, kickoff.attempts) == ("failed", 3)
    assert ended.status == "failed" and ended.failed_reason == "card_failed:kickoff"
    run = await db.get(AgentRun, kickoff.run_id, populate_existing=True)
    assert run.status == "failed" and run.usage["retries"] >= 2


async def test_document_send_failure_marks_document_missing(
    stack, service, make_position, db, monkeypatch
):
    stack.llm.default = Brain()
    driver = await start(stack, service, make_position, ["planning"], 6)
    await driver.advance_to(0.2)
    await driver.do({"board": BOARD}, 0)
    sid = driver.session_id

    calls, results = {"send": 0}, []
    original_call = McpClient._call

    async def flaky(self, name, args):
        if name == "send_document":
            calls["send"] += 1
            if calls["send"] <= 2:  # 첫 시도의 보내기와 같은 run_id 재시도가 모두 실패
                return fail("upstream_unavailable", "api down", True)
        return await original_call(self, name, args)

    original_run = stack.runner.run

    async def record(*args):
        result = await original_run(*args)
        results.append(result)
        return result

    monkeypatch.setattr(McpClient, "_call", flaky)
    monkeypatch.setattr(stack.runner, "run", record)
    await driver.advance_to(1.6)

    first = next(r for r in results if r.error)
    assert not first.ok and first.error.startswith(DOCUMENT_MISSING)
    checkin = await event(db, sid, "planning_checkin")
    # 다음 시도(같은 run_id)에서 보내지면 done이고 문서 미제공 표시가 풀린다
    assert (checkin.status, checkin.attempts, checkin.document_missing) == ("done", 2, False)
    assert await versions(db, sid) == {3: [1], 4: [1], 5: [1]}

    # 끝내 못 보내면(3회 모두 실패) 카드 failed + document_missing → 세션 failed
    calls["send"] = -100
    driver2 = await start(stack, service, make_position, ["planning"], 6)
    await driver2.advance_to(0.2)
    await driver2.do({"board": BOARD}, 0)
    await driver2.advance_to(1.6)
    checkin = await event(db, driver2.session_id, "planning_checkin")
    assert (checkin.status, checkin.document_missing) == ("failed", True)
    assert (await db.get(Session, driver2.session_id, populate_existing=True)).status == "failed"


async def test_undecided_division_uses_default_and_disagree_falls_back(
    stack, service, make_position, db
):
    """미합의 중 카드 도래: 기본안 확정(colleague_default) 후 카드 실행. 주담당이 1번을 보내지 않은
    세션의 반대 의견은 분업 때 정한 방향을 가리키고 의견 본문은 카탈로그 고정 문장 그대로다.
    지시 핵심어가 빠진 완성본은 1회 다시 쓴다."""
    brain = Brain(
        {
            "도현님 4번은 재참여 기능 있는 서비스 위주로 봐 주세요.": cls(
                "instruction", instructions=[instr(4, "4번은 재참여 기능 위주", "재참여")]
            )
        }
    )
    stack.llm.default = brain
    driver = await start(stack, service, make_position, ["collaboration"], 6)
    sid = driver.session_id
    await driver.advance_to(1.6)  # division(0.5) 미응답 → collab_help(1.5)에서 기본안

    session = await db.get(Session, sid, populate_existing=True)
    assert session.division["decided_by"] == "colleague_default"
    assert session.division["parts"] == PARTS
    notice = [
        m.content
        for m in await rows(db, Message, Message.session_id == sid, Message.sender == "colleague")
        if m.content.startswith("아직 분업이 안 정해져서")
    ]
    assert len(notice) == 1

    await driver.do(
        {
            "say": {
                "channel": "dm",
                "content": "도현님 4번은 재참여 기능 있는 서비스 위주로 봐 주세요.",
            }
        },
        1,
    )
    await driver.advance_to(3.1)  # 계획성 미선택이라 L/2에 texture(초안 v1)
    brain.omit = {4: 1}
    await driver.advance_to(4.6)
    review = [h for kind, h in brain.calls if kind == "draft" and "4번 비슷한 서비스 사례 v2" in h]
    assert len(review) == 2 and "앞 초안에 빠진 핵심어: 재참여" in review[1]

    disagree_event = await event(db, sid, "collab_disagree")
    [message] = await rows(db, Message, Message.event_id == disagree_event.id)
    scenario = await stack_scenario(db, sid)
    card = next(c for c in scenario["cards"] if c["card_id"] == "collab_disagree")
    scenario_opinion = card["fixed_opinions"][0]["opinion"].strip()
    assert "처음 정한 방향" in message.content and message.content.endswith(scenario_opinion)
    assert "보내" not in message.content.split("처음 정한 방향")[0]


async def test_observation_failure_retries_window_switch(
    stack, service, make_position, db, monkeypatch
):
    """R1: 카드 메시지는 나갔는데 관찰 저장이 실패하면 처리 완료로 확정하지 않는다. 같은 run_id
    재시도가 카드(멱등)부터 다시 돌아 직전 창을 기록하고 새 창을 연다."""
    stack.llm.default = Brain()
    driver = await start(stack, service, make_position, ["planning"], 6)
    await driver.advance_to(0.2)
    await driver.do({"board": BOARD}, 0)
    sid = driver.session_id
    calls = {"record": 0}
    original_call = McpClient._call

    async def flaky(self, name, args):
        if name == "record_observation":
            calls["record"] += 1
            if calls["record"] == 1:
                return fail("upstream_unavailable", "api down", True)
        return await original_call(self, name, args)

    monkeypatch.setattr(McpClient, "_call", flaky)
    await driver.advance_to(1.6)  # 중간 점검(1.5): 계획성 분업 창(0~1.5)을 닫아야 한다

    checkin = await event(db, sid, "planning_checkin")
    assert (checkin.status, checkin.attempts) == ("done", 2)
    observed = await rows(db, Observation, Observation.session_id == sid)
    assert [o.card_id for o in observed] == ["planning_division"]
    posted = await rows(db, Message, Message.event_id == checkin.id)
    assert sorted(m.seq for m in posted) == [1, 30, 40, 50]  # 재시도에 카드 메시지는 한 벌
    graph = await stack.runner.graph()
    state = (await graph.aget_state({"configurable": {"thread_id": thread_id(sid)}})).values
    assert (
        state["current_card"] == "planning_checkin" and str(checkin.id) in state["handled_stimuli"]
    )


async def test_reply_saved_before_checkpoint_restores_v3_memory(
    stack, service, make_position, db, monkeypatch
):
    """RC1: v3와 응답을 다 저장한 뒤 체크포인트 전에 끊긴 재실행도 sent·progress를 v3로 맞춘다."""
    from app import scheduler
    from app.agent.session import nodes

    stack.llm.default = Brain({REVISE: cls("doc_feedback", part_no=4, wants_revision=True)})
    driver = await start(stack, service, make_position, ["planning"], 6)
    await driver.advance_to(0.2)
    await driver.do({"board": BOARD}, 0)
    await driver.advance_to(4.6)  # 리뷰 v2
    sid = driver.session_id
    async with driver.client() as http:
        doc_id = await driver.received_doc(http, 4)
    async with stack.ctx.session_factory() as session_db:
        message, run_id, _ = await accept_candidate_message(
            session_db, stack.hub, sid, "v3", "dm", REVISE, {"doc_id": doc_id, "version": 2}
        )
    original = nodes.post

    async def crash_after_reply(deps, state, **kwargs):
        ok = await original(deps, state, **kwargs)
        if kwargs.get("node") == "respond":
            raise Crash
        return ok

    monkeypatch.setattr(nodes, "post", crash_after_reply)
    stimulus = Stimulus("message", message_id=message.id)
    with pytest.raises(Crash):
        await scheduler.run_stimulus(stack.ctx, sid, stimulus, run_id)
    monkeypatch.setattr(nodes, "post", original)
    assert (await versions(db, sid))[4] == [1, 2, 3]

    await scheduler.run_stimulus(stack.ctx, sid, stimulus, run_id)  # 같은 run_id 복구
    graph = await stack.runner.graph()
    notes = (await graph.aget_state({"configurable": {"thread_id": thread_id(sid)}})).values[
        "work_notes"
    ]
    assert notes["sent"]["4"] == 3 and notes["progress"]["4"] == "v3까지 보낸 상태"
    assert (await versions(db, sid))[4] == [1, 2, 3]
    replies = await rows(db, Message, Message.run_id == run_id, Message.sender == "colleague")
    assert [m.seq for m in replies if m.seq == 1] == [1]
