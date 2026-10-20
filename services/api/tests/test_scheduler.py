"""완료 기준: 6분 세션(L=6) 이벤트 ±10초 내 fired→done, 지연 공개와 "공개됨" 줄, 만료 → reporting →
보고 없이 제출+5분에 completed·큐 발행, 보고 메시지로 종료, 재시작 후 fired 이벤트 재실행, 미발행
재발행, 문서 제공 실패(최소 테스트 ⑤ api 쪽: 이벤트 failed·document_missing 저장).

시계는 tick(now)에 넘기는 값으로 흉내 낸다. 실행(FakeAgentRunner)은 drain()으로 기다린다.
"""

import uuid
from datetime import timedelta

import pytest
from app.agent.runner import DOCUMENT_MISSING, RunResult
from app.config import get_settings
from app.db import make_session_factory
from app.models import AgentRun, Message, SessionEvent
from app.queue import GENERATE
from app.scheduler import Scheduler, drain
from app.services.context import AppContext
from sqlalchemy import select

from tests.conftest import ALL_FIVE, FakeSocket


@pytest.fixture
def ctx(engine, hub, locks, publisher, runner) -> AppContext:
    return AppContext(
        settings=get_settings(),
        engine=engine,
        session_factory=make_session_factory(engine),
        hub=hub,
        locks=locks,
        publisher=publisher,
        runner=runner,
    )


async def events_of(db, session_id) -> dict[str, SessionEvent]:
    query = select(SessionEvent).where(SessionEvent.session_id == session_id)
    rows = (await db.execute(query.execution_options(populate_existing=True))).scalars()
    return {e.card_id: e for e in rows}


async def run_clock(ctx, start, seconds: range) -> None:
    scheduler = Scheduler(ctx)
    for second in seconds:
        await scheduler.tick(start + timedelta(seconds=second))
        await drain()


async def test_six_minute_session_fires_events_on_time(db, ctx, started_session, hub):
    session = await started_session(ALL_FIVE, 6)
    ws = FakeSocket()
    await hub.connect(session.id, ws)
    await run_clock(ctx, session.started_at, range(0, 5 * 60 + 25, 5))  # 보고 요청(5.5분) 전까지

    events = await events_of(db, session.id)
    assert len(events) == 9
    for card_id, event in events.items():
        if card_id == "honesty_report":
            assert event.status == "pending"
            continue
        assert event.status == "done", card_id
        assert abs((event.fired_at - event.due_at).total_seconds()) <= 10, card_id
    # 행마다 자기 event_id를 단 message.new가 나갔다(collab_disagree도 review와 같은 run에서 따로)
    announced = {f["payload"]["event_id"] for f in ws.frames if f["type"] == "message.new"}
    assert {str(e.id) for c, e in events.items() if c != "honesty_report"} <= announced
    assert events["review"].run_id == events["collab_disagree"].run_id
    # 시작 공개 4건은 start()가 바로 기록하고, 지연 공개(interview_summary, 3.5분)만 스케줄러가
    # 알린다
    released = [f["payload"]["doc_id"] for f in ws.frames if f["type"] == "document.released"]
    assert released == ["interview_summary"]
    notice = await db.scalar(
        select(Message)
        .where(Message.session_id == session.id, Message.channel == "notice")
        .order_by(Message.created_at.desc())
    )
    assert (notice.sender, notice.content) == ("system", "「사용자 인터뷰 요약」이 공개됐어요")


async def test_timeout_reports_then_completes_and_publishes(
    db, ctx, service, started_session, publisher, hub
):
    session = await started_session(["planning"], 6)
    ws = FakeSocket()
    await hub.connect(session.id, ws)

    await run_clock(
        ctx, session.ends_at, range(1, 2)
    )  # 만료 → 자동 제출 → 보고 요청 실행 → reporting
    waiting = await service.get(session.id)
    assert waiting.status == "reporting" and waiting.deadline_at is not None
    events = await events_of(db, session.id)
    assert events["report_request"].status == "done"
    assert publisher.published == []

    await run_clock(ctx, waiting.deadline_at, range(1, 2))  # 보고 없이 deadline_at 경과
    ended = await service.get(session.id)
    assert ended.status == "completed" and ended.completed_at == ended.deadline_at
    assert publisher.published == [(GENERATE, {"session_id": str(session.id), "attempt": 1})]
    assert ws.frames[-1] == {"type": "session.ended", "payload": {"reason": "timeout"}}


async def test_report_message_ends_reporting(db, ctx, service, started_session):
    session = await started_session(["honesty"], 6)
    await service.submit(session.id)
    reported = await service.get(session.id)
    assert await service.mark_reported(session.id, reported.submitted_at + timedelta(seconds=30))

    await run_clock(ctx, reported.submitted_at, range(35, 36))
    ended = await service.get(session.id)
    assert ended.status == "completed" and ended.completed_at == ended.reported_at


async def test_fired_event_reruns_after_restart(db, ctx, started_session):
    session = await started_session(["collaboration"])
    # 재시작 직전 상태: kickoff를 fired로 집고 실행을 시작했지만 done을 남기지 못하고 죽음.
    # 재시작했을 때는 division(10분)도 이미 due다. kickoff가 먼저 끝나야 division이 나간다.
    run_id = uuid.uuid4()
    kickoff = (await events_of(db, session.id))["kickoff"]
    kickoff.status, kickoff.fired_at, kickoff.run_id, kickoff.attempts = (
        "fired",
        session.started_at,
        run_id,
        1,
    )
    db.add(
        AgentRun(
            run_id=run_id,
            session_id=session.id,
            stimulus="event",
            ref_ids=[kickoff.id],
            started_at=session.started_at,
        )
    )
    await db.commit()
    restarted_at = session.started_at + timedelta(minutes=11)

    await run_clock(ctx, restarted_at, range(0, 1))
    events = await events_of(db, session.id)
    assert (events["kickoff"].status, events["division"].status) == ("done", "pending")

    await run_clock(ctx, restarted_at, range(5, 11, 5))  # 더 돌아도 kickoff는 한 벌만
    events = await events_of(db, session.id)
    kickoff, division = events["kickoff"], events["division"]
    assert (kickoff.status, kickoff.run_id, kickoff.attempts) == ("done", run_id, 2)
    assert division.status == "done" and division.run_id != run_id
    posted = (
        await db.execute(
            select(Message.event_id, Message.run_id)
            .where(Message.session_id == session.id, Message.event_id.is_not(None))
            .order_by(Message.created_at)
        )
    ).all()
    assert posted == [(kickoff.id, run_id), (division.id, division.run_id)]
    run = await db.get(AgentRun, run_id, populate_existing=True)
    assert run.status == "finished"


async def test_unpublished_session_is_republished(db, ctx, service, started_session, publisher):
    session = await started_session(["planning"])
    await service.submit(session.id)
    publisher.fail = True
    assert (await service.complete(session.id)).report_enqueued_at is None
    publisher.fail = False

    await Scheduler(ctx).tick()
    await drain()

    assert publisher.published == [(GENERATE, {"session_id": str(session.id), "attempt": 1})]
    assert (await service.get(session.id)).report_enqueued_at is not None


class SendFailsRunner:
    """planning_checkin에서 send_document가 재시도 뒤에도 실패한 그래프를 fail_times번 흉내 낸다.
    나머지는 원래 러너다.
    """

    def __init__(self, inner, factory, fail_times: int = 99) -> None:
        self.inner, self.factory, self.left = inner, factory, fail_times

    async def run(self, session_id, stimulus, run_id):
        if stimulus.type == "event":
            async with self.factory() as db:
                cards = (
                    await db.execute(
                        select(SessionEvent.card_id).where(SessionEvent.id.in_(stimulus.event_ids))
                    )
                ).scalars()
                if "planning_checkin" in set(cards) and self.left > 0:
                    self.left -= 1
                    return RunResult(ok=False, error=f"{DOCUMENT_MISSING}: send_document failed")
        return await self.inner.run(session_id, stimulus, run_id)


async def test_document_send_failure_marks_event(db, ctx, service, started_session, monkeypatch):
    """최소 테스트 ⑤ 문서 제공 실패(api 쪽): 카드 실행이 document_missing으로 끝나면 이벤트 행에
    남기고, 같은 run_id로 총 3회 실패하면 카드 failed·세션 failed. 워커는 이 행으로 사유
    document_missing을 단다."""
    monkeypatch.setattr("app.scheduler.RETRY_DELAY", 0)
    session = await started_session(["planning"], 6)
    ctx.runner = SendFailsRunner(ctx.runner, ctx.session_factory)
    await run_clock(ctx, session.started_at, range(0, 95, 5))  # planning_checkin = 1.5분

    checkin = (await events_of(db, session.id))["planning_checkin"]
    assert (checkin.status, checkin.attempts, checkin.document_missing) == ("failed", 3, True)
    failed = await service.get(session.id)
    assert (failed.status, failed.failed_stage) == ("failed", "session")
    assert failed.failed_reason == "card_failed:planning_checkin"


async def test_document_send_recovers_on_retry(db, ctx, started_session, monkeypatch):
    """G2-A3: 첫 시도에서 문서 전송이 실패해도 재시도에서 성공하면 done이고
    document_missing은 풀린다.
    """
    monkeypatch.setattr("app.scheduler.RETRY_DELAY", 0)
    session = await started_session(["planning"], 6)
    ctx.runner = SendFailsRunner(ctx.runner, ctx.session_factory, fail_times=1)
    await run_clock(ctx, session.started_at, range(0, 95, 5))

    checkin = (await events_of(db, session.id))["planning_checkin"]
    assert (checkin.status, checkin.attempts, checkin.document_missing) == ("done", 2, False)
