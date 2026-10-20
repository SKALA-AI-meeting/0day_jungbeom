"""SessionService: 세션 상태 전이의 유일한 소유자.

invited ─consent·start→ in_progress ─complete→ completed ─mark_report_ready→ report_ready
        ─approve→ approving ─mark_reviewed→ reviewed. invited ─cancel→ cancelled.
fail(stage="session")은 in_progress에서,
fail(stage="report")는 completed·report_ready·approving에서.

모든 전이는 현재 상태를 검사하고 멱등이다.
이미 목표 상태(또는 그 뒤)면 아무것도 바꾸지 않고 돌려준다.
허용되지 않는 전이는 SessionError(code="conflict")로 올리며 라우터가 409로 바꾼다.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import queue
from app.agent.runner import AgentRunner, Stimulus
from app.auth import INVITE_TTL, new_invite_token
from app.hub import Hub
from app.models import DocumentRelease, DocumentState, Invite, Position, Session, SessionEvent
from app.services import scenario as scenario_service
from app.services.locks import SessionLocks
from app.services.runs import run_agent, start_run

log = logging.getLogger(__name__)

# 진행 순서. 멱등 판단("이미 지났다")에 쓴다. cancelled·failed는 끝 상태라 따로 다룬다.
ORDER = ["invited", "in_progress", "completed", "report_ready", "approving", "reviewed"]
REPORT_STAGE_FROM = {"completed", "report_ready", "approving"}

ReuseEstimator = Callable[[AsyncSession, uuid.UUID], Awaitable[None]]


class SessionError(Exception):
    """code: not_found(404), conflict(409), expired·cancelled(410), session_ending(409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


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
        session = await self.get(session_id)
        if session.status == "cancelled":
            return session
        if session.status != "invited":
            raise self._conflict(session, "cancel")
        invite = await self._invite(session)
        session.status = "cancelled"
        invite.cancelled_at = self.now()
        await self.db.commit()
        return session

    async def start(self, session_id: uuid.UUID) -> Session:
        """in_progress로 바꾸고 이벤트·공개 예약·문서 파트 행을 만든다.

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
        session.status = "in_progress"
        session.started_at = now
        session.ends_at = now + timedelta(minutes=position.scenario["session_minutes"])
        invite.used_at = now
        events, releases = scenario_service.expand(position.scenario, session.id, now)
        # 시작 공개 문서는 시작 트랜잭션에서 바로 공개한다. 지연 공개만 스케줄러가 기록한다.
        for release in releases:
            release["released_at"] = now if release["release_at"] <= now else None
        await self.db.execute(
            insert(SessionEvent)
            .values(events)
            .on_conflict_do_nothing(index_elements=["session_id", "card_id"])
        )
        await self.db.execute(
            insert(DocumentRelease)
            .values(releases)
            .on_conflict_do_nothing(index_elements=["session_id", "doc_id"])
        )
        # 기획안 파트는 시나리오 parts 수만큼 빈 본문·revision 0으로 시작한다.
        # tasks는 분업 확정 때 만든다(api-candidate).
        parts = [
            {"session_id": session.id, "part_no": int(no)} for no in position.scenario["parts"]
        ]
        await self.db.execute(
            insert(DocumentState)
            .values(parts)
            .on_conflict_do_nothing(index_elements=["session_id", "part_no"])
        )
        await self.db.commit()
        return session

    async def complete(self, session_id: uuid.UUID, reason: str = "submitted") -> Session:
        """제출·만료.

        세션 Lock 안에서: 상태 재검증 → submitted_at 커밋 → 종료 실행 → 재사용 추정
        → completed 커밋 → report.generate 발행 → session.ended.
        동시에 두 번 불려도 Lock 안에서 다시 읽은 상태가 in_progress가 아니면 아무것도 하지
        않는다. 종료 실행이 ok=False여도 지원자 작업물을 잃지 않도록 completed로 진행하고
        리포트를 발행한다(agent_runs는 failed로 남고 경고 로그를 찍는다). 예외는 그대로
        올리고, 다시 부르면 이어서 진행한다(종료 run_id 고정, 발행 실패는 outbox가 보완).
        """
        session = await self.get(session_id)
        if self._passed(session, "completed"):
            return session
        if session.status != "in_progress":
            raise self._conflict(session, "complete")

        async with self.locks(session_id):
            session = await self.get(session_id)
            if session.status != "in_progress":
                return session
            if session.submitted_at is None:
                session.submitted_at = self.now()
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
            session.status = "completed"
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
        allowed = {"in_progress"} if stage == "session" else REPORT_STAGE_FROM
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
