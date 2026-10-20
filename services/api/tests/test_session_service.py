"""완료 기준: SessionService 전이 전부·멱등(reporting·completed_at·시작 후 취소·regenerate 포함),
시작 시 tasks 5행 null·지원자 문서 5개·최종본 생성."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from app.agent.runner import RunResult
from app.models import (
    AgentRun,
    Document,
    DocumentRelease,
    FinalDocument,
    Invite,
    Message,
    Report,
    SessionEvent,
    Task,
)
from app.queue import APPROVE, GENERATE, republish_pending
from app.services.session import REPORT_GRACE, SessionError, end_run_id
from sqlalchemy import func, select

from tests.conftest import ALL_FIVE, FakeSocket, to_completed


class FailedEndRunner:
    """종료 실행이 ok=False로 끝나는 runner."""

    async def run(self, session_id, stimulus, run_id):
        return RunResult(ok=False, error="end graph failed")


async def test_full_lifecycle_and_idempotency(db, service, make_position, publisher, hub):
    position = await make_position(ALL_FIVE)
    session, invite, raw = await service.create_for_invite(position.id, "지원자A", "a@example.com")
    assert session.status == "invited" and raw and invite.token_hash != raw

    with pytest.raises(SessionError) as exc:  # 동의 전 시작 불가
        await service.start(session.id)
    assert exc.value.code == "conflict"

    first = (await service.consent(session.id)).consented_at
    assert (await service.consent(session.id)).consented_at == first  # 동의 재호출 멱등

    started = await service.start(session.id)
    again = await service.start(session.id)  # 같은 값 멱등, 예약·문서·보드도 한 번만
    assert started.status == "in_progress"
    assert (again.started_at, again.ends_at) == (started.started_at, started.ends_at)
    assert (started.ends_at - started.started_at).total_seconds() == 120 * 60
    events = await db.scalar(select(func.count()).select_from(SessionEvent))
    releases = await db.scalar(select(func.count()).select_from(DocumentRelease))
    assert (events, releases) == (9, 5)
    tasks = (await db.execute(select(Task).order_by(Task.part_no))).scalars().all()
    assert [(t.part_no, t.assignee, t.order, t.depends_on) for t in tasks] == [
        (1, None, 1, []),
        (2, None, 2, []),
        (3, None, 3, [2]),
        (4, None, 4, []),
        (5, None, 5, []),
    ]
    docs = (await db.execute(select(Document.owner, Document.part_no, Document.final))).all()
    assert sorted(docs, key=lambda d: (d[2], d[1] or 0)) == [
        *[("candidate", n, False) for n in range(1, 6)],
        ("candidate", None, True),
    ]
    final = await db.get(FinalDocument, session.id)
    assert [s["part_no"] for s in final.sections] == [1, 2, 3, 4, 5]
    assert all(s["content"] == "" and s["source_doc_id"] is None for s in final.sections)

    with pytest.raises(SessionError):  # 시작 후 동의는 409
        await service.consent(session.id)

    # 제출: 보고 요청 카드(honesty_report)를 바로 실행하고 reporting(deadline_at = 제출 + 5분)
    ws = FakeSocket()
    await hub.connect(session.id, ws)
    reporting = await service.submit(session.id)
    assert reporting.status == "reporting"
    assert reporting.deadline_at - reporting.submitted_at == REPORT_GRACE
    request = await db.scalar(
        select(SessionEvent).where(
            SessionEvent.session_id == session.id, SessionEvent.card_id == "honesty_report"
        )
    )
    assert request.status == "done" and request.due_at == reporting.submitted_at
    assert ws.types()[-1] == "session.reporting"
    assert (await service.submit(session.id)).status == "reporting"  # 재제출 멱등

    # 보고 메시지(요청 이후) → reported_at → completed_at은 보고 시각
    reported_at = datetime.now(UTC)
    assert await service.mark_reported(session.id, reported_at) is True
    completed = await service.complete(session.id, "submitted")
    assert completed.status == "completed" and completed.completed_at == reported_at
    assert completed.report_enqueued_at is not None
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


async def test_report_before_submit_completes_at_once(db, service, started_session):
    """보고 요청(11L/12) 뒤 제출 전에 이미 보고했으면 제출 즉시 completed."""
    session = await started_session(ALL_FIVE)
    request = await db.scalar(
        select(SessionEvent).where(
            SessionEvent.session_id == session.id, SessionEvent.card_id == "honesty_report"
        )
    )
    request.status, request.fired_at = "done", datetime.now(UTC)
    await db.commit()
    assert await service.mark_reported(session.id, datetime.now(UTC)) is True
    done = await service.submit(session.id)
    assert done.status == "completed" and done.completed_at == done.reported_at


async def test_cancel_fail_and_regenerate(db, service, started_session, make_position, publisher):
    position = await make_position(["planning"])

    cancelled, _, _ = await service.create_for_invite(position.id, "B", "b@example.com")
    assert (await service.cancel(cancelled.id)).status == "cancelled"
    assert (await service.cancel(cancelled.id)).status == "cancelled"
    with pytest.raises(SessionError) as exc:
        await service.consent(cancelled.id)
    assert exc.value.code == "cancelled"

    # 시작 후 취소(중도 포기)는 in_progress·reporting 모두 허용
    running = await started_session(["planning"])
    assert (await service.cancel(running.id)).status == "cancelled"
    waiting = await started_session(["planning"])
    await service.submit(waiting.id)
    assert (await service.cancel(waiting.id)).status == "cancelled"

    failed = await started_session(["planning"])
    out = await service.fail(failed.id, "session", "llm_failures")
    assert (out.status, out.failed_stage) == ("failed", "session")
    assert (await service.fail(failed.id, "session", "again")).failed_reason == "llm_failures"

    # 리포트 실패 → regenerate: completed로 되돌리고 남은 draft를 지운 뒤 report.generate 재발행
    broken = await started_session(["planning"])
    await to_completed(service, broken.id)
    await service.mark_report_ready(broken.id)
    db.add(Report(session_id=broken.id, stage="draft", content={}, content_hash="h"))
    await db.commit()
    await service.fail(broken.id, "report", "worker_dlq")
    with pytest.raises(SessionError):  # 세션 실패는 재생성 대상이 아니다
        await service.regenerate_report(failed.id)
    publisher.published.clear()
    again = await service.regenerate_report(broken.id)
    assert (again.status, again.failed_stage) == ("completed", None)
    assert await db.get(Report, broken.id, populate_existing=True) is None
    assert publisher.published == [(GENERATE, {"session_id": str(broken.id), "attempt": 1})]

    expired, invite, _ = await service.create_for_invite(position.id, "E", "e@example.com")
    await service.consent(expired.id)
    stored = await db.get(Invite, invite.id)
    stored.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()
    with pytest.raises(SessionError) as exc:  # 동의 후 만료되면 시작 불가(410 expired)
        await service.start(expired.id)
    assert exc.value.code == "expired"

    # 종료 실행이 ok=False여도 completed로 진행하고 리포트를 발행한다(agent_runs는 failed)
    end_failed = await started_session(["planning"])
    await service.submit(end_failed.id)
    runner, service.runner = service.runner, FailedEndRunner()
    done = await service.complete(end_failed.id)
    service.runner = runner
    assert (done.status, done.report_enqueued_at is not None) == ("completed", True)
    end_run = await db.get(AgentRun, end_run_id(end_failed.id), populate_existing=True)
    assert end_run.status == "failed"

    # 발행이 확인되지 않으면 report_enqueued_at을 비워 두고, outbox 재탐색이 다시 발행한다
    unsent = await started_session(["planning"])
    await service.submit(unsent.id)
    publisher.fail = True
    assert (await service.complete(unsent.id)).report_enqueued_at is None
    publisher.fail = False
    assert await republish_pending(db, publisher) == 1
    assert (await service.get(unsent.id)).report_enqueued_at is not None
    # 보고 요청 카드는 제출 직후 실행돼 메시지를 남겼다(정직 미선택이면 흐름 카드)
    request_message = await db.scalar(
        select(func.count()).select_from(Message).where(Message.session_id == unsent.id)
    )
    assert request_message >= 1


class BlockedEndRunner:
    """종료 실행을 release()까지 붙잡아 두는 runner(취소와 종료의 경쟁을 만든다)."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self, session_id, stimulus, run_id):
        if stimulus.type == "end":
            self.entered.set()
            await self.release.wait()
        return await self.inner.run(session_id, stimulus, run_id)


async def test_cancel_after_start_never_makes_a_report(service, started_session, publisher, hub):
    """data-model: 시작 후 취소는 리포트를 만들지 않는다. 취소가 먼저면 뒤이은 complete가 아무것도
    하지 않고, 종료가 이미 돌고 있으면 취소는 같은 Lock을 기다렸다가 completed를 보고 conflict다."""
    first = await started_session(["planning"])
    await service.submit(first.id)
    assert (await service.cancel(first.id)).status == "cancelled"
    assert (await service.complete(first.id)).status == "cancelled"
    assert publisher.published == []

    second = await started_session(["planning"])
    await service.submit(second.id)
    blocked = BlockedEndRunner(service.runner)
    service.runner = blocked
    ending = asyncio.create_task(service.complete(second.id))
    await blocked.entered.wait()
    cancelling = asyncio.create_task(service.cancel(second.id))
    await asyncio.sleep(0.05)
    assert not cancelling.done()  # 같은 세션 Lock을 기다린다
    blocked.release.set()
    assert (await ending).status == "completed"
    with pytest.raises(SessionError) as exc:
        await cancelling
    assert exc.value.code == "conflict"
    assert [body["session_id"] for _, body in publisher.published] == [str(second.id)]
