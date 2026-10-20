"""SessionService: 세션 상태 전이의 유일한 소유자.

invited ─consent·start→ in_progress ─submit→ reporting ─complete→ completed ─mark_report_ready→
report_ready ─approve→ approving ─mark_reviewed→ reviewed. cancel은
invited·in_progress·reporting에서, fail(stage="session")은 in_progress·reporting에서,
fail(stage="report")는 completed·report_ready·approving에서 허용한다. regenerate_report는
failed(report)를 completed로 되돌린다.

종료 규칙은 하나다(docs/api/design.md "제출 처리"). 제출(또는 만료) 때 보고 요청 카드가 아직이면
바로 실행하고, 보고 메시지(reported_at)가 있거나 deadline_at(submitted_at+5분)이 지나면
completed_at을 저장하고 종료한다. 모든 전이는 현재 상태를 검사하고 멱등이며, 허용되지 않는 전이는
SessionError(code="conflict")다.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import queue
from app.agent.runner import AgentRunner, Stimulus
from app.auth import INVITE_TTL, new_invite_token
from app.hub import Hub
from app.models import (
    ConnectionGap,
    DocumentRelease,
    Invite,
    Position,
    Report,
    RubricAdjustment,
    Session,
    SessionEvent,
    Task,
)
from app.services import board, documents, events
from app.services import scenario as scenario_service
from app.services.locks import SessionLocks
from app.services.runs import run_agent, start_run
from app.services.states import ORDER, SessionError

__all__ = ["ORDER", "SessionError", "SessionService", "end_run_id", "REPORT_GRACE"]

log = logging.getLogger(__name__)

REPORT_STAGE_FROM = {"completed", "report_ready", "approving"}
CANCELLABLE = {"invited", "in_progress", "reporting"}
REPORT_GRACE = timedelta(minutes=5)  # deadline_at = submitted_at + 5분

ReuseEstimator = Callable[[AsyncSession, uuid.UUID], Awaitable[None]]


def end_run_id(session_id: uuid.UUID) -> uuid.UUID:
    """종료 실행의 고정 run_id. complete()가 재실행돼도 같은 값이라 중복 저장이 없다."""
    return uuid.uuid5(session_id, "end")


class SessionService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        hub: Hub,
        runner: AgentRunner,
        publisher: queue.Publisher,
        locks: SessionLocks,
        reuse_estimator: ReuseEstimator | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.db = db
        self.hub = hub
        self.runner = runner
        self.publisher = publisher
        self.locks = locks
        self.reuse_estimator = reuse_estimator
        self.now = clock

    async def get(self, session_id: uuid.UUID) -> Session:
        session = await self.db.get(Session, session_id, populate_existing=True)
        if session is None:
            raise SessionError("not_found", "session not found")
        return session

    def _passed(self, session: Session, target: str) -> bool:
        return session.status in ORDER and ORDER.index(session.status) >= ORDER.index(target)

    def _conflict(self, session: Session, action: str) -> SessionError:
        return SessionError("conflict", f"cannot {action} from {session.status}")

    async def create_for_invite(
        self,
        position_id: uuid.UUID,
        alias: str,
        email: str,
        previous_session_id: uuid.UUID | None = None,
    ) -> tuple[Session, Invite, str]:
        """초대와 세션(invited)을 함께 만든다. 반환하는 토큰 원문은 링크에만 쓴다."""
        raw, token_hash = new_invite_token()
        invite = Invite(
            position_id=position_id,
            alias=alias,
            email=email,
            token_hash=token_hash,
            expires_at=self.now() + INVITE_TTL,
            previous_session_id=previous_session_id,
        )
        self.db.add(invite)
        await self.db.flush()
        session = Session(invite_id=invite.id, status="invited")
        self.db.add(session)
        await self.db.commit()
        return await self.get(session.id), invite, raw

    async def _invite(self, session: Session) -> Invite:
        return await self.db.get(Invite, session.invite_id, populate_existing=True)

    async def _position(self, session: Session) -> Position:
        invite = await self._invite(session)
        return await self.db.get(Position, invite.position_id)

    async def consent(self, session_id: uuid.UUID) -> Session:
        """시작 전까지 몇 번이든 허용(첫 시각만 남김). 시작 후에는 conflict."""
        session = await self.get(session_id)
        invite = await self._invite(session)
        if session.status == "cancelled":
            raise SessionError("cancelled", "invite cancelled")
        if session.status != "invited":
            raise self._conflict(session, "consent")
        if invite.expires_at <= self.now():
            raise SessionError("expired", "invite expired")
        if session.consented_at is None:
            session.consented_at = self.now()
            await self.db.commit()
        return session

    async def cancel(self, session_id: uuid.UUID) -> Session:
        """담당자 취소. 시작 후 취소는 중도 포기로 리포트를 만들지 않는다.

        submit·complete와 같은 세션 Lock 안에서 상태를 다시 읽는다. 진행 중이던 종료가 먼저 끝나면
        completed라 conflict이고, 취소가 먼저면 뒤이은 complete는 아무것도 하지 않는다.
        """
        async with self.locks(session_id):
            session = await self.get(session_id)
            if session.status == "cancelled":
                return session
            if session.status not in CANCELLABLE:
                raise self._conflict(session, "cancel")
            started = session.status != "invited"
            invite = await self._invite(session)
            session.status = "cancelled"
            invite.cancelled_at = self.now()
            await self.db.commit()
        if started:
            await self.hub.broadcast(session_id, "session.ended", {"reason": "cancelled"})
        return session

    async def start(self, session_id: uuid.UUID) -> Session:
        """in_progress로 바꾸고 이벤트·공개 예약·보드 5행(assignee null)·지원자 문서·최종본을
        만든다.

        이미 시작했으면 같은 값을 돌려준다. 시작 전 초대 만료(72시간)는 consent와 같은 expired.
        """
        session = await self.get(session_id)
        if self._passed(session, "in_progress"):
            return session
        if session.status != "invited" or session.consented_at is None:
            raise self._conflict(session, "start")
        invite = await self._invite(session)
        now = self.now()
        if invite.expires_at <= now:
            raise SessionError("expired", "invite expired")
        position = await self.db.get(Position, invite.position_id)
        scenario = position.scenario
        session.status = "in_progress"
        session.started_at = now
        session.ends_at = now + timedelta(minutes=scenario["session_minutes"])
        invite.used_at = now
        event_rows, releases = scenario_service.expand(scenario, session.id, now)
        # 시작 공개 문서는 시작 트랜잭션에서 바로 공개한다. 지연 공개만 스케줄러가 기록한다.
        for release in releases:
            release["released_at"] = now if release["release_at"] <= now else None
        await self.db.execute(
            insert(SessionEvent)
            .values(event_rows)
            .on_conflict_do_nothing(index_elements=["session_id", "card_id"])
        )
        await self.db.execute(
            insert(DocumentRelease)
            .values(releases)
            .on_conflict_do_nothing(index_elements=["session_id", "doc_id"])
        )
        await self.db.execute(
            insert(Task)
            .values(board.initial_tasks(session.id, scenario))
            .on_conflict_do_nothing(index_elements=["session_id", "part_no"])
        )
        await documents.create_session_documents(self.db, session.id, scenario)
        await self.db.commit()
        return session

    async def submit(self, session_id: uuid.UUID, reason: str = "submitted") -> Session:
        """제출 또는 만료. 세션 Lock 안에서 submitted_at·deadline_at 기록 → 보고 요청 카드가
        아직이면 due_at을 당겨 즉시 실행 → 이미 보고했으면 complete, 아니면
        reporting(session.reporting).

        멱등: 이미 reporting 이후면 그대로 돌려준다. 끝까지 못 갔으면(재시작) 다시 부르면 이어간다.
        """
        session = await self.get(session_id)
        if self._passed(session, "reporting"):
            return session
        if session.status != "in_progress":
            raise self._conflict(session, "submit")

        async with self.locks(session_id):
            session = await self.get(session_id)
            if session.status != "in_progress":
                return session
            if session.submitted_at is None:
                # 만료 자동 제출은 만료 시각이 제출 시각이다(스케줄러가 늦게 집어도 보고 대기 상한이
                # 같다)
                session.submitted_at = session.ends_at if reason == "timeout" else self.now()
                session.deadline_at = session.submitted_at + REPORT_GRACE
                # 제출본은 최종본 documents 행의 version으로 고정한다(리포트 submitted_version)
                await documents.freeze_final(self.db, session_id)
                await self.db.commit()
            await self._fire_report_request(session)
            session = await self.get(session_id)
            if session.status != "in_progress":  # 카드 실패로 failed가 됐을 수 있다
                return session
            session.status = "reporting"
            await self.db.commit()
        if session.reported_at is not None:
            # 요청 뒤 제출 전에 이미 보고했으면 바로 종료한다(complete가 Lock을 다시 잡는다)
            return await self.complete(session_id, "submitted")
        await self.hub.broadcast(
            session_id, "session.reporting", {"deadline_at": session.deadline_at.isoformat()}
        )
        return session

    async def _fire_report_request(self, session: Session) -> None:
        """or_on_submit 카드(honesty_report·report_request)가 아직 pending이면 그 자리에서 실행한다.
        이미 fired면(스케줄러가 실행 중이던 행) 같은 run_id로 마저 실행한다. Lock은 호출자가 잡고
        있다."""
        row = await self.db.scalar(
            select(SessionEvent)
            .where(SessionEvent.session_id == session.id, SessionEvent.or_on_submit.is_(True))
            .execution_options(populate_existing=True)
        )
        if row is None or row.status in ("done", "failed"):
            return
        if row.status == "pending":
            row.due_at = session.submitted_at
            row.status, row.fired_at, row.run_id = "fired", self.now(), uuid.uuid4()
            await self.db.commit()
        for _ in range(events.MAX_ATTEMPTS):
            if await events.attempt(self, row.run_id):
                return

    async def mark_reported(self, session_id: uuid.UUID, at: datetime) -> bool:
        """보고 메시지(kind=report)가 보고 요청 이후에 저장됐으면 reported_at을 남긴다(첫 값만)."""
        session = await self.get(session_id)
        if session.status not in ("in_progress", "reporting") or session.reported_at is not None:
            return False
        # 요청 카드는 다른 연결(앱·스케줄러)이 실행한다. 이 db 세션에 남은 옛 객체(fired_at 없음)를
        # 읽지 않도록 다시 채운다(간헐 실패 원인이었다)
        request = await self.db.scalar(
            select(SessionEvent)
            .where(SessionEvent.session_id == session_id, SessionEvent.or_on_submit.is_(True))
            .execution_options(populate_existing=True)
        )
        if request is None or request.fired_at is None or at < request.fired_at:
            return False
        session.reported_at = at
        await self.db.commit()
        return True

    async def complete(self, session_id: uuid.UUID, reason: str = "submitted") -> Session:
        """보고 종료. 세션 Lock 안에서: completed_at 확정(보고 시각 또는 deadline_at) → 종료
        실행(열린 창 닫기·약속 이행 확정) → 재사용 추정 → completed 커밋 → report.generate 발행 →
        session.ended.

        종료 실행이 ok=False여도 지원자 작업물을 잃지 않도록 completed로 진행하고 리포트를 발행한다
        (agent_runs는 failed로 남는다). 예외는 그대로 올리고, 다시 부르면 이어서 진행한다(종료
        run_id 고정, 발행 실패는 outbox가 보완).
        """
        session = await self.get(session_id)
        # 이미 끝났거나(취소·실패 포함) 먼저 확정된 전이는 뒤집지 않는다
        if self._passed(session, "completed") or session.status in ("cancelled", "failed"):
            return session
        if session.status != "reporting":
            raise self._conflict(session, "complete")

        async with self.locks(session_id):
            session = await self.get(session_id)
            if session.status != "reporting":
                return session
            if session.completed_at is None:
                # 보고했으면 보고 시각, 아니면 보고 대기 상한(스케줄러는 deadline_at이 지나야
                # 부른다)
                session.completed_at = session.reported_at or session.deadline_at
                await self.db.commit()

            run_id = end_run_id(session_id)
            end = Stimulus("end")
            await start_run(self.db, session_id, end, run_id)
            await self.db.commit()
            result = await run_agent(
                self.db, self.runner, self.locks, session_id, end, run_id, lock_held=True
            )
            if not result.ok:
                log.warning(
                    "end run failed for session %s (run %s): %s; completing anyway",
                    session_id,
                    run_id,
                    result.error,
                )
            if self.reuse_estimator is not None:
                await self.reuse_estimator(self.db, session_id)

            session = await self.get(session_id)
            if session.status != "reporting":  # 종료 실행 중 실패 처리로 이미 끝났으면 그대로 둔다
                return session
            session.status = "completed"
            # 끊긴 채 종료되면 그 구간의 끝은 종료 시각이다
            await self.db.execute(
                update(ConnectionGap)
                .where(
                    ConnectionGap.session_id == session_id, ConnectionGap.reconnected_at.is_(None)
                )
                .values(reconnected_at=session.completed_at)
            )
            await self.db.commit()
            await queue.publish_report(self.db, self.publisher, session, queue.GENERATE)
            await self.hub.broadcast(session_id, "session.ended", {"reason": reason})
            return session

    async def mark_report_ready(self, session_id: uuid.UUID) -> Session:
        session = await self.get(session_id)
        if self._passed(session, "report_ready"):
            return session
        if session.status != "completed":
            raise self._conflict(session, "mark_report_ready")
        session.status = "report_ready"
        await self.db.commit()
        return session

    async def approve(self, session_id: uuid.UUID) -> Session:
        """approving 커밋 → report.approve 발행 → approve_enqueued_at(실패하면 outbox가 재발행)."""
        session = await self.get(session_id)
        if self._passed(session, "approving"):
            return session
        if session.status != "report_ready":
            raise self._conflict(session, "approve")
        session.status = "approving"
        await self.db.commit()
        await queue.publish_report(self.db, self.publisher, session, queue.APPROVE)
        return session

    async def mark_reviewed(self, session_id: uuid.UUID) -> Session:
        session = await self.get(session_id)
        if self._passed(session, "reviewed"):
            return session
        if session.status != "approving":
            raise self._conflict(session, "mark_reviewed")
        session.status = "reviewed"
        await self.db.commit()
        return session

    async def fail(self, session_id: uuid.UUID, stage: str, reason: str) -> Session:
        """stage=session: 진행 중 중단(디브리핑만, 리포트 없음). stage=report: 리포트 생성 실패."""
        session = await self.get(session_id)
        if session.status == "failed":
            return session
        allowed = {"in_progress", "reporting"} if stage == "session" else REPORT_STAGE_FROM
        if stage not in ("session", "report") or session.status not in allowed:
            raise self._conflict(session, f"fail({stage})")
        session.status = "failed"
        session.failed_stage = stage
        session.failed_reason = reason
        if stage == "session":
            # 진행 중 중단은 그 시각이 세션 종료 시각이다(디브리핑 기한의 기준)
            session.ends_at = min(session.ends_at, self.now())
        await self.db.commit()
        if stage == "session":
            await self.hub.broadcast(session_id, "session.ended", {"reason": "failed"})
        return session

    async def regenerate_report(self, session_id: uuid.UUID) -> Session:
        """리포트 실패(failed_stage=report)만. completed로 되돌리고 report.generate를 attempt 1로
        다시 낸다.

        이전 draft·조정이 남아 있으면 새 draft가 저장되지 않으므로 지운다(세션 기록은 그대로).
        """
        session = await self.get(session_id)
        if session.status != "failed" or session.failed_stage != "report":
            raise self._conflict(session, "regenerate")
        await self.db.execute(
            delete(RubricAdjustment).where(RubricAdjustment.session_id == session_id)
        )
        await self.db.execute(delete(Report).where(Report.session_id == session_id))
        session.status = "completed"
        session.failed_stage = session.failed_reason = None
        session.report_enqueued_at = session.approve_enqueued_at = None
        await self.db.commit()
        await queue.publish_report(self.db, self.publisher, session, queue.GENERATE)
        return session
