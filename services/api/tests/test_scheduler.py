"""완료 기준: 6분 세션(L=6) 이벤트 ±10초 내 fired→done, 만료 시 큐 발행,
재시작 후 fired 이벤트 재실행, 미발행 세션 재발행.

시계는 tick(now)에 넘기는 값으로 흉내 낸다. 실행(FakeAgentRunner)은 drain()으로 기다린다.
"""

import uuid
from datetime import timedelta

import pytest
from app.config import get_settings
from app.db import make_session_factory
from app.models import AgentRun, Message, Session, SessionEvent
from app.queue import GENERATE
from app.scheduler import Scheduler, drain
from app.services.context import AppContext
from sqlalchemy import select

from tests.conftest import FakeSocket

ALL_FOUR = ["cooperation", "responsibility", "flexibility", "respect"]


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


async def started(service, make_position, elements, minutes=120) -> Session:
    position = await make_position(elements, minutes)
    session, _, _ = await service.create_for_invite(position.id, "A", "a@example.com")
    await service.consent(session.id)
    return await service.start(session.id)


async def events_of(db, session_id) -> list[SessionEvent]:
    query = select(SessionEvent).where(SessionEvent.session_id == session_id)
    return list((await db.execute(query.execution_options(populate_existing=True))).scalars())


async def test_six_minute_session_fires_events_on_time(db, ctx, service, make_position, hub):
    session = await started(service, make_position, ALL_FOUR, minutes=6)
    ws = FakeSocket()
    await hub.connect(session.id, ws)
    scheduler = Scheduler(ctx)
    for second in range(0, 6 * 60, 5):  # 종료 직전까지 5초 간격
        await scheduler.tick(session.started_at + timedelta(seconds=second))
        await drain()

    events = await events_of(db, session.id)
    assert len(events) == 9
    for event in events:
        assert event.status == "done", event.card_id
        assert abs((event.fired_at - event.due_at).total_seconds()) <= 10, event.card_id
    # 행마다 자기 event_id를 단 message.new가 나갔다(respect도 review와 같은 run에서 따로)
    announced = {f["payload"]["event_id"] for f in ws.frames if f["type"] == "message.new"}
    assert announced == {str(e.id) for e in events}
    review, respect = (next(e for e in events if e.card_id == c) for c in ("review", "respect"))
    assert review.run_id == respect.run_id
    # 시작 공개 4건은 start()가 바로 기록하고, 지연 공개(interview_summary)만 스케줄러가 알린다
    released = [f["payload"]["doc_id"] for f in ws.frames if f["type"] == "document.released"]
    assert released == ["interview_summary"]


async def test_timeout_completes_and_publishes(db, ctx, service, make_position, publisher, hub):
    session = await started(service, make_position, ["cooperation"], minutes=6)
    ws = FakeSocket()
    await hub.connect(session.id, ws)

    await Scheduler(ctx).tick(session.ends_at + timedelta(seconds=1))
    await drain()

    ended = await service.get(session.id)
    assert ended.status == "completed" and ended.report_enqueued_at is not None
    assert publisher.published == [(GENERATE, {"session_id": str(session.id), "attempt": 1})]
    assert ws.frames[-1] == {"type": "session.ended", "payload": {"reason": "timeout"}}


async def test_fired_event_reruns_after_restart(db, ctx, service, make_position):
    session = await started(service, make_position, ["cooperation"])
    # 재시작 직전 상태: kickoff를 fired로 집고 실행을 시작했지만 done을 남기지 못하고 죽음.
    # 재시작했을 때는 division(10분)도 이미 due다. kickoff가 먼저 끝나야 division이 나간다.
    run_id = uuid.uuid4()
    events = {e.card_id: e for e in await events_of(db, session.id)}
    kickoff = events["kickoff"]
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

    await Scheduler(ctx).tick(restarted_at)
    await drain()
    events = {e.card_id: e for e in await events_of(db, session.id)}
    assert (events["kickoff"].status, events["division"].status) == ("done", "pending")

    for second in (5, 10):  # 새 프로세스의 스케줄러가 더 돌아도 kickoff는 한 벌만
        await Scheduler(ctx).tick(restarted_at + timedelta(seconds=second))
        await drain()

    events = {e.card_id: e for e in await events_of(db, session.id)}
    kickoff, division = events["kickoff"], events["division"]
    assert (kickoff.status, kickoff.run_id, kickoff.attempts) == ("done", run_id, 2)
    assert division.status == "done" and division.run_id != run_id
    posted = (
        (
            await db.execute(
                select(Message)
                .where(Message.session_id == session.id, Message.event_id.is_not(None))
                .order_by(Message.created_at)
            )
        )
        .scalars()
        .all()
    )
    assert [(m.event_id, m.run_id) for m in posted] == [
        (kickoff.id, run_id),
        (division.id, division.run_id),
    ]
    run = await db.get(AgentRun, run_id, populate_existing=True)
    assert run.status == "finished"


async def test_unpublished_session_is_republished(db, ctx, service, make_position, publisher):
    session = await started(service, make_position, ["cooperation"])
    publisher.fail = True
    assert (await service.complete(session.id)).report_enqueued_at is None
    publisher.fail = False

    await Scheduler(ctx).tick()
    await drain()

    assert publisher.published == [(GENERATE, {"session_id": str(session.id), "attempt": 1})]
    assert (await service.get(session.id)).report_enqueued_at is not None
