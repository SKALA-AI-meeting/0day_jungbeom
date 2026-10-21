"""관리자 쪽 서비스: 채용 건 조립·초대·재응시·지원자 목록, e2e 테스트 세션."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Invite, Message, Position, Report, RubricAdjustment, Session
from app.services import reports
from app.services import scenario as sc
from app.services import session as session_service
from app.services.common import conflict, invalid, iso, not_found, purge_at

GROUPS = {
    "invited": "waiting",
    "in_progress": "in_progress",
    "completed": "needs_review",
    "report_ready": "needs_review",
    "approving": "done",
    "reviewed": "done",
    "failed": "problem",
    "cancelled": "problem",
}


async def create_position(
    db: AsyncSession,
    company_id: uuid.UUID,
    *,
    name: str,
    session_minutes: int,
    mission_id: str,
    scenarios_dir,
    now: datetime,
) -> Position:
    if session_minutes not in (60, 15):
        raise invalid("invalid_input", "session_minutes must be 60 or 15")
    try:
        scenario = sc.assemble(scenarios_dir, mission_id, session_minutes)
    except sc.InvalidMission as exc:
        raise invalid("invalid_input", str(exc)) from exc
    await sc.seed_materials(db, scenarios_dir, mission_id, scenario["catalog_version"])
    position = Position(
        company_id=company_id,
        name=name,
        mission_id=mission_id,
        session_minutes=session_minutes,
        catalog_version=scenario["catalog_version"],
        scenario=scenario,
        created_at=now,
    )
    db.add(position)
    await db.flush()
    return position


def position_created(position: Position) -> dict[str, Any]:
    scenario = position.scenario
    return {
        "id": str(position.id),
        "name": position.name,
        "session_minutes": position.session_minutes,
        "seats": [
            {
                "seat": s["seat"],
                "name": s["name"],
                "persona_type": s["persona_type"],
                "avatar_url": sc.avatar_url(scenario, s),
            }
            for s in scenario["seats"]
        ],
        "keywords": [o["label"] for o in sc.keyword_options(scenario)],
        "catalog_version": position.catalog_version,
    }


async def invite(
    db: AsyncSession,
    position: Position,
    *,
    alias: str | None,
    email: str,
    previous_session_id: uuid.UUID | None,
    now: datetime,
) -> tuple[Session, Invite, str]:
    if previous_session_id is not None:
        prev = await db.get(Session, previous_session_id)
        prev_invite = await db.get(Invite, prev.invite_id) if prev else None
        if prev is None or prev_invite.position_id != position.id:
            raise invalid("invalid_previous_session", "unknown previous session")
        expired = prev.status == "invited" and now >= prev_invite.expires_at
        retryable = (prev.status == "failed" and prev.failed_stage == "session") or (
            prev.status == "cancelled" or expired
        )
        if not retryable:
            raise invalid("invalid_previous_session", "previous session is not retryable")
        alias = alias or prev_invite.alias
        prev_invite.superseded_at = now
        await db.flush()
    if not alias:
        raise invalid("invalid_input", "alias required")
    taken = await db.scalar(
        select(Invite.id).where(
            Invite.position_id == position.id, Invite.alias == alias, Invite.superseded_at.is_(None)
        )
    )
    if taken:
        raise conflict("conflict", "alias already used")
    return await session_service.create_for_invite(
        db, position, alias=alias, email=email, now=now, previous_session_id=previous_session_id
    )


async def candidate_rows(db: AsyncSession, position: Position, now: datetime) -> list[dict]:
    rows = (
        await db.execute(
            select(Session, Invite)
            .join(Invite, Invite.id == Session.invite_id)
            .where(Invite.position_id == position.id)
            .order_by(Invite.created_at)
        )
    ).all()
    out = []
    for session, inv in rows:
        count = await db.scalar(
            select(func.count()).where(
                Message.session_id == session.id,
                Message.sender == "candidate",
                Message.channel == "room",
            )
        )
        last = await db.scalar(
            select(func.max(Message.created_at)).where(
                Message.session_id == session.id, Message.sender == "candidate"
            )
        )
        expired = session.status == "invited" and now >= inv.expires_at
        report = await db.get(Report, session.id)
        elements = low = source = None
        if report is not None:
            merged_elements = await _element_chips(db, session, report)
            elements, low, source = merged_elements
        out.append(
            {
                "session_id": str(session.id),
                "alias": inv.alias,
                "email": inv.email,
                "status": session.status,
                "display_status": "expired" if expired else session.status,
                "display_group": "problem" if expired else GROUPS[session.status],
                "phase": session.phase,
                "invited_at": iso(inv.created_at),
                "started_at": iso(session.started_at),
                "ends_at": iso(session.ends_at),
                "ended_at": iso(session.ended_at),
                "last_activity_at": iso(last),
                "message_count": count,
                "report_ready_at": iso(report.generated_at) if report else None,
                "purge_at": purge_at(session),
                "failed_stage": session.failed_stage,
                "failed_reason": session.failed_reason,
                "next_action": _next_action(session, expired),
                "previous_session_id": str(inv.previous_session_id)
                if inv.previous_session_id
                else None,
                "reissued_at": iso(inv.reissued_at),
                "elements": elements,
                "low_confidence_count": low,
                "level_source": source,
            }
        )
    return out


def _next_action(session: Session, expired: bool) -> str | None:
    if expired:
        return "초대를 재발급하세요"
    if session.status == "failed" and session.failed_stage == "session":
        return "새 초대로 재응시를 보내세요"
    if session.status == "failed":
        return "리포트를 다시 생성하세요"
    if session.status == "report_ready":
        return "리포트를 검토하세요"
    return None


async def _element_chips(db: AsyncSession, session: Session, report: Report):
    """요소별 수준 칩(조정 병합 후 값)·확신도 low 차원 수·출처. 총점·정렬 키는 만들지 않는다."""
    rows = (
        await db.scalars(
            select(RubricAdjustment)
            .where(RubricAdjustment.session_id == session.id)
            .order_by(RubricAdjustment.adjusted_at)
        )
    ).all()
    latest = {r.dimension_id: r for r in rows}
    content = report.content
    dims = content.get("dimensions", [])
    chips = []
    for element in content.get("elements", []):
        mine = [d for d in dims if d.get("element") == element["element"]]
        touched = any(d["dimension_id"] in latest for d in mine)
        level = element.get("level")
        if touched:
            levels = [
                latest[d["dimension_id"]].level if d["dimension_id"] in latest else d.get("level")
                for d in mine
            ]
            levels = [lv for lv in levels if lv is not None]
            level = reports.round_half_up(sum(levels) / len(levels)) if levels else None
        chips.append({"element": element["element"], "level": level, "adjusted": touched})
    low = sum(1 for d in dims if d.get("confidence") == "low")
    return chips, low, "reviewer" if latest else "auto"


async def company_session(db: AsyncSession, company_id: uuid.UUID, session_id: uuid.UUID):
    """관리자 조회는 JWT의 company_id로 positions를 거쳐 필터(기업 간 격리)."""
    row = (
        await db.execute(
            select(Session, Invite, Position)
            .join(Invite, Invite.id == Session.invite_id)
            .join(Position, Position.id == Invite.position_id)
            .where(Session.id == session_id, Position.company_id == company_id)
        )
    ).first()
    if row is None:
        raise not_found("session not found")
    return row
