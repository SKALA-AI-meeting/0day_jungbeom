"""SessionService: 생명주기 전이(docs/architecture/session-lifecycle.md 세션 상태 머신). 모든 전이는
현재 상태를
검사하고
멱등이다.

단계 전환(advance_phase)은 phases.py, 칸 확정은 debate.py가 같은 트랜잭션에서 부른다.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import queue
from app.auth import INVITE_TTL, new_invite_token
from app.models import EvaluationRun, Invite, Position, Proposal, Report, Session, Slot
from app.services import scenario as sc
from app.services.clock import Clock
from app.services.common import ENDED_STATUSES, Effects, conflict, empty_sections, iso
from app.services.phases import enter_phase


async def create_for_invite(
    db: AsyncSession,
    position: Position,
    *,
    alias: str,
    email: str,
    now: datetime,
    previous_session_id: uuid.UUID | None = None,
) -> tuple[Session, Invite, str]:
    raw, token_hash = new_invite_token()
    invite = Invite(
        position_id=position.id,
        alias=alias,
        email=email,
        token_hash=token_hash,
        expires_at=now + INVITE_TTL,
        previous_session_id=previous_session_id,
        created_at=now,
    )
    db.add(invite)
    await db.flush()
    session = Session(invite_id=invite.id, status="invited", created_at=now)
    db.add(session)
    await db.flush()
    return session, invite, raw


def reissue(invite: Invite, session: Session, now: datetime) -> str:
    """같은 세션·같은 별칭, 토큰 해시와 만료만 교체(옛 링크는 404)."""
    if session.status != "invited":
        raise conflict("conflict", "only invited sessions can be reissued")
    raw, token_hash = new_invite_token()
    invite.token_hash = token_hash
    invite.expires_at = now + INVITE_TTL
    invite.reissued_at = now
    return raw


def consent(session: Session, display_name: str, now: datetime) -> None:
    if session.status != "invited":
        raise conflict("conflict", "already started")
    session.display_name = display_name
    session.consented_at = now


async def start(
    db: AsyncSession, session: Session, position: Position, clock: Clock, fx: Effects
) -> None:
    """in_progress·phase=keyword, 시각 확정, 칸 3행·기획안 초안, 첫 시스템 안내, phase_started."""
    if session.status == "in_progress":
        return
    if session.status != "invited":
        raise conflict("conflict", f"cannot start from {session.status}")
    now = clock.now()
    session.status = "in_progress"
    session.started_at = now
    session.ends_at = now + timedelta(minutes=position.session_minutes)
    for phase in sc.DEBATE_PHASES:
        db.add(Slot(session_id=session.id, phase=phase, status="empty"))
    db.add(
        Proposal(
            session_id=session.id,
            sections=empty_sections(position.scenario["proposal_template"]),
            revision=0,
            updated_at=now,
        )
    )
    await db.flush()
    await enter_phase(db, session, position, "keyword", "start", fx, clock)


async def submit(
    db: AsyncSession,
    session: Session,
    reason: str,
    now: datetime,
    fx: Effects,
    template: list[str],
    warning_shown: bool | None = None,
) -> Proposal:
    """제출·자동 제출: 한 트랜잭션에서 제출본 고정 → completed → (커밋 뒤) 큐 발행 →
    session.ended. 빈 칸은 막지 않고 칸 id만 기록한다(자동 제출이면 경고 표시 여부 null)."""
    proposal = await db.get(Proposal, session.id, with_for_update=True)
    if session.status in ENDED_STATUSES - {"cancelled", "failed"}:
        return proposal
    if session.status != "in_progress":
        raise conflict("conflict", f"cannot submit from {session.status}")
    proposal.submitted = dict(proposal.sections)
    proposal.submitted_at = now
    proposal.auto_submitted = reason == "timeout"
    proposal.submit_blank_sections = [
        f for f in template if not (proposal.submitted.get(f) or "").strip()
    ]
    proposal.blank_warning_shown = None if proposal.auto_submitted else bool(warning_shown)
    session.status = "completed"
    session.phase = "completed"
    session.submitted_at = now
    session.completed_at = now
    session.ended_at = now
    session.generation += 1
    fx.generation = session.generation
    fx.publish.append(queue.GENERATE)
    fx.emit("session.ended", {"reason": reason})
    return proposal


def cancel(session: Session, now: datetime, fx: Effects) -> None:
    if session.status not in ("invited", "in_progress"):
        raise conflict("conflict", f"cannot cancel from {session.status}")
    session.status = "cancelled"
    session.ended_at = now
    fx.emit("session.ended", {"reason": "cancelled"})


def fail(session: Session, stage: str, reason: str, now: datetime, fx: Effects) -> None:
    if stage == "session":
        if session.status != "in_progress":
            return
        session.ended_at = now
        fx.emit("session.ended", {"reason": "failed"})
    session.status = "failed"
    session.failed_stage = stage
    session.failed_reason = reason


async def report_failed_step(db: AsyncSession, session: Session) -> str:
    """failed(report)가 난 곳: 담당자 승인 뒤 확정이면 finalize, 그 전(초안 생성)이면 draft."""
    report = await db.get(Report, session.id)
    return "finalize" if report is not None and report.reviewed_at is not None else "draft"


async def regenerate(db: AsyncSession, session: Session, fx: Effects) -> str:
    """failed(report) 복구. 확정 실패는 approving으로 돌려 같은 회차 finalize를 재개하고(draft
    유지), 초안 전 실패는 남은 draft를 지우고 completed로 재발행한다(최신 평가에 실패 차원이
    있으면 eval_round +1). 지운 draft는 새 draft가 저장될 때까지 조회·후보 목록에 나가지 않는다."""
    if session.status != "failed" or session.failed_stage != "report":
        raise conflict("conflict", "only report failures can be regenerated")
    session.failed_stage = None
    session.failed_reason = None
    if await report_failed_step(db, session) == "finalize":
        session.status = "approving"
        session.approve_enqueued_at = None
        fx.publish.append(queue.APPROVE)
        return session.status
    latest = await db.scalar(
        select(EvaluationRun)
        .where(EvaluationRun.session_id == session.id)
        .order_by(EvaluationRun.created_at.desc())
        .limit(1)
    )
    if latest is not None and latest.has_failed:
        session.eval_round += 1
    stale = await db.get(Report, session.id)
    if stale is not None:
        await db.delete(stale)
    session.status = "completed"
    session.report_enqueued_at = None
    fx.publish.append(queue.GENERATE)
    return session.status


def invite_url(base: str, raw: str) -> str:
    return f"{base.rstrip('/')}/s/{raw}"


def invite_response(
    session: Session, invite: Invite, raw: str, position: Position, web_base: str
) -> dict[str, Any]:
    url = invite_url(web_base, raw)
    template = position.scenario["admin_catalog"]["candidate_notice_template"]
    return {
        "session_id": str(session.id),
        "invite_url": url,
        "expires_at": iso(invite.expires_at),
        "notice_text": template.format(
            alias=invite.alias, session_minutes=position.session_minutes, invite_url=url
        ),
    }
