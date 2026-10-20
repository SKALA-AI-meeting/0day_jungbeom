"""완료 기준: SessionService 단위 테스트(전이 전부·멱등)."""

from datetime import UTC, datetime, timedelta

import pytest
from app.agent.runner import RunResult
from app.models import AgentRun, DocumentRelease, DocumentState, Invite, Session, SessionEvent
from app.queue import APPROVE, GENERATE, republish_pending
from app.services.session import SessionError, end_run_id
from sqlalchemy import func, select

from tests.conftest import FakeSocket

ALL_FOUR = ["cooperation", "responsibility", "flexibility", "respect"]


class FailedEndRunner:
    """종료 실행이 ok=False로 끝나는 runner."""

    async def run(self, session_id, stimulus, run_id):
        return RunResult(ok=False, error="end graph failed")


async def test_full_lifecycle_and_idempotency(db, service, make_position, publisher, hub):
    position = await make_position(ALL_FOUR)
    session, invite, raw = await service.create_for_invite(position.id, "지원자A", "a@example.com")
    assert session.status == "invited" and raw and invite.token_hash != raw

    with pytest.raises(SessionError) as exc:  # 동의 전 시작 불가
        await service.start(session.id)
    assert exc.value.code == "conflict"

    first = (await service.consent(session.id)).consented_at
    assert (await service.consent(session.id)).consented_at == first  # 동의 재호출 멱등

    started = await service.start(session.id)
    assert started.status == "in_progress"
    again = await service.start(session.id)  # 같은 값 멱등, 예약도 한 번만
    assert (again.started_at, again.ends_at) == (started.started_at, started.ends_at)
    assert (started.ends_at - started.started_at).total_seconds() == 120 * 60
    events = await db.scalar(select(func.count()).select_from(SessionEvent))
    releases = await db.scalar(select(func.count()).select_from(DocumentRelease))
    parts = (await db.execute(select(DocumentState.part_no, DocumentState.revision))).all()
    assert (events, releases) == (9, 5)
    assert sorted(parts) == [(n, 0) for n in range(1, 6)]  # 파트 행 5개, revision 0

    with pytest.raises(SessionError):  # 시작 후 동의는 409
        await service.consent(session.id)

    ws = FakeSocket()
    await hub.connect(session.id, ws)
    completed = await service.complete(session.id, "submitted")
    assert completed.status == "completed"
    assert completed.submitted_at is not None and completed.report_enqueued_at is not None
    end_run = await db.get(AgentRun, end_run_id(session.id), populate_existing=True)
    assert (end_run.stimulus, end_run.status) == ("end", "finished")
    assert ws.frames[-1] == {"type": "session.ended", "payload": {"reason": "submitted"}}
    await service.complete(session.id, "timeout")  # 재호출 멱등: 발행·종료 알림 반복 없음
    assert publisher.published == [(GENERATE, {"session_id": str(session.id), "attempt": 1})]
    assert ws.types().count("session.ended") == 1

    for step, status in (
        (service.mark_report_ready, "report_ready"),
        (service.approve, "approving"),
        (service.mark_reviewed, "reviewed"),
    ):
        assert (await step(session.id)).status == status
        assert (await step(session.id)).status == status
    assert [key for key, _ in publisher.published] == [GENERATE, APPROVE]
    assert (await service.get(session.id)).approve_enqueued_at is not None


async def test_cancel_and_fail_transitions(db, service, make_position, publisher):
    position = await make_position(["cooperation"])

    cancelled, _, _ = await service.create_for_invite(position.id, "B", "b@example.com")
    assert (await service.cancel(cancelled.id)).status == "cancelled"
    assert (await service.cancel(cancelled.id)).status == "cancelled"
    with pytest.raises(SessionError) as exc:
        await service.consent(cancelled.id)
    assert exc.value.code == "cancelled"

    running, _, _ = await service.create_for_invite(position.id, "C", "c@example.com")
    await service.consent(running.id)
    await service.start(running.id)
    with pytest.raises(SessionError):  # 시작 후 취소 불가
        await service.cancel(running.id)
    failed = await service.fail(running.id, "session", "llm_failures")
    assert (failed.status, failed.failed_stage) == ("failed", "session")
    assert (await service.fail(running.id, "session", "again")).failed_reason == "llm_failures"

    reported, _, _ = await service.create_for_invite(position.id, "D", "d@example.com")
    await service.consent(reported.id)
    await service.start(reported.id)
    await service.complete(reported.id)
    await service.mark_report_ready(reported.id)
    failed = await service.fail(reported.id, "report", "worker_dlq")
    assert (failed.status, failed.failed_stage) == ("failed", "report")

    expired, invite, _ = await service.create_for_invite(position.id, "E", "e@example.com")
    await service.consent(expired.id)
    stored = await db.get(Invite, invite.id)
    stored.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()
    with pytest.raises(SessionError) as exc:  # 동의 후 만료되면 시작 불가(410 expired)
        await service.start(expired.id)
    assert exc.value.code == "expired"

    # 종료 실행이 ok=False여도 completed로 진행하고 리포트를 발행한다(agent_runs는 failed)
    end_failed, _, _ = await service.create_for_invite(position.id, "F", "f@example.com")
    await service.consent(end_failed.id)
    await service.start(end_failed.id)
    service.runner = FailedEndRunner()
    done = await service.complete(end_failed.id)
    assert (done.status, done.report_enqueued_at is not None) == ("completed", True)
    end_run = await db.get(AgentRun, end_run_id(end_failed.id), populate_existing=True)
    assert end_run.status == "failed"

    # 발행이 확인되지 않으면 report_enqueued_at을 비워 두고, outbox 재탐색이 다시 발행한다
    unsent, _, _ = await service.create_for_invite(position.id, "G", "g@example.com")
    await service.consent(unsent.id)
    await service.start(unsent.id)
    publisher.fail = True
    assert (await service.complete(unsent.id)).report_enqueued_at is None
    publisher.fail = False
    assert await republish_pending(db, publisher) == 1
    assert (await service.get(unsent.id)).report_enqueued_at is not None

    statuses = (await db.execute(select(Session.status))).scalars().all()
    expected = ["cancelled", "completed", "completed", "failed", "failed", "invited"]
    assert sorted(statuses) == expected
