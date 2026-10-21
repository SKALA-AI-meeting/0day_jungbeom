"""지원자 쪽 읽기 모델: State 스냅샷, 자료, 디브리핑, 참여자. 페르소나 유형은 여기서 내보내지 않는다
(디브리핑 seats만 예외, C8)."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AgentRun,
    AssistantCall,
    ConnectionGap,
    DebriefSurvey,
    Invite,
    Material,
    Message,
    Observation,
    Position,
    Proposal,
    Session,
    Slot,
)
from app.services import proposal as proposal_service
from app.services import scenario as sc
from app.services.common import iso, serialize_message, slot_public, t_min
from app.services.phases import keyword_key

DEBRIEF_DAYS = 7


def display_name(session: Session, invite: Invite) -> str:
    return session.display_name or invite.alias


def participants(scenario: dict, session: Session, invite: Invite) -> list[dict[str, Any]]:
    return [{"id": "candidate", "display_name": display_name(session, invite)}] + [
        {"id": s["seat"], "display_name": s["name"], "avatar_url": sc.avatar_url(scenario, s)}
        for s in scenario["seats"]
    ]


def seats_typed(scenario: dict, session: Session, invite: Invite) -> list[dict[str, Any]]:
    """관리자·내부·리포트용 자리 목록(유형 포함)."""
    return [{"seat": "candidate", "display_name": display_name(session, invite)}] + [
        {
            "seat": s["seat"],
            "display_name": s["name"],
            "avatar_url": sc.avatar_url(scenario, s),
            "persona_type": s["persona_type"],
        }
        for s in scenario["seats"]
    ]


async def gaps(db: AsyncSession, session: Session) -> list[dict[str, Any]]:
    rows = await db.scalars(
        select(ConnectionGap)
        .where(ConnectionGap.session_id == session.id)
        .order_by(ConnectionGap.disconnected_at)
    )
    return [
        {
            "from_t_min": t_min(session, g.disconnected_at) or 0.0,
            "to_t_min": t_min(session, g.reconnected_at),
        }
        for g in rows
    ]


async def materials(db: AsyncSession, session: Session, position: Position) -> dict[str, Any]:
    kw = await keyword_key(db, session.id)
    if kw is None:
        return {"locked": True, "keyword": None, "materials": []}
    info = position.scenario["keywords"][kw]
    return {"locked": False, "keyword": info["label"], "materials": info["materials"]}


async def material(
    db: AsyncSession, session: Session, position: Position, material_id: str
) -> Material | None:
    """열린 자료(확정 키워드)의 채용 건 catalog_version 본문. 아니면 None(423)."""
    kw = await keyword_key(db, session.id)
    if kw is None:
        return None
    row = await db.get(Material, (position.catalog_version, material_id))
    if row is None or row.keyword_key != kw:
        return None
    return row


async def state(
    db: AsyncSession,
    session: Session,
    position: Position,
    invite: Invite,
    now: datetime,
    typing: list[str],
    ws_seq: int,
) -> dict[str, Any]:
    scenario = position.scenario
    started = session.started_at is not None
    phase = session.phase if session.phase != "completed" else "proposal"
    live = session.status == "in_progress"
    slots = {
        s.phase: s
        for s in (await db.scalars(select(Slot).where(Slot.session_id == session.id))).all()
    }
    messages = (
        await db.scalars(
            select(Message)
            .where(Message.session_id == session.id, Message.channel == "room")
            .order_by(Message.created_at, Message.seq)
        )
    ).all()
    calls = (
        await db.scalars(
            select(AssistantCall)
            .where(AssistantCall.session_id == session.id)
            .order_by(AssistantCall.created_at)
        )
    ).all()
    by_id = {
        m.id: m
        for m in (
            await db.scalars(
                select(Message).where(
                    Message.session_id == session.id, Message.channel == "assistant"
                )
            )
        ).all()
    }
    runs = (
        await db.scalars(
            select(AgentRun).where(
                AgentRun.session_id == session.id, AgentRun.status.in_(("queued", "started"))
            )
        )
    ).all()
    proposal = await db.get(Proposal, session.id)
    return {
        "session": {
            "id": str(session.id),
            "alias": invite.alias,
            "status": session.status,
            "phase": phase,
            "started_at": iso(session.started_at),
            "ends_at": iso(session.ends_at),
            "session_minutes": position.session_minutes,
            "phase_started_at": iso(session.phase_started_at),
            "phase_deadline_at": iso(session.phase_deadline_at),
            "phase_remaining_seconds": _remaining(session.phase_deadline_at, now) if live else None,
            "session_remaining_seconds": _remaining(session.ends_at, now) if live else None,
            "office_start": scenario["office_clock"]["start"],
            "office_end": scenario["office_clock"]["end"],
            "completed_at": iso(session.completed_at),
        },
        "phases": [
            {
                "phase": s["stage_id"],
                "budget_min": s["budget_min"],
                "deadline_t_min": s["deadline_min"],
            }
            for s in scenario["stages"]
        ],
        "participants": participants(scenario, session, invite),
        "keyword_options": sc.keyword_options(scenario),
        "slots": [
            slot_public(session, slots[p])
            if p in slots
            else {
                "phase": p,
                "status": "empty",
                "value": None,
                "filled_by": None,
                "resolution": None,
                "outcome": None,
                "t_min": None,
            }
            for p in sc.DEBATE_PHASES
        ],
        "messages": [serialize_message(session, m) for m in messages] if started else [],
        "materials": await materials(db, session, position),
        "proposal": proposal_service.serialize(proposal, scenario["proposal_template"]),
        "assistant": [
            {
                "call_id": str(c.id),
                "request": by_id[c.request_message_id].content,
                "response": by_id[c.response_message_id].content if c.response_message_id else "",
                "cited_material_ids": list(c.cited_material_ids),
                "t_min": t_min(session, c.created_at) or 0.0,
            }
            for c in calls
        ],
        "typing": typing,
        "active_runs": [{"run_id": str(r.run_id), "stimulus": r.stimulus} for r in runs],
        "connection_gaps": await gaps(db, session),
        "ws_seq": ws_seq,
    }


def _remaining(at: datetime | None, now: datetime) -> int | None:
    return None if at is None else max(int((at - now).total_seconds()), 0)


def debrief_until(session: Session) -> datetime | None:
    return session.ended_at + timedelta(days=DEBRIEF_DAYS) if session.ended_at else None


async def debrief(
    db: AsyncSession, session: Session, position: Position, invite: Invite, contact: str
) -> dict[str, Any]:
    scenario = position.scenario
    texts = scenario["debrief"]
    survey_row = await db.get(DebriefSurvey, session.id)
    base = {
        "intro_notice": f"{texts['intro_notice']} {texts.get('persona_note', '')}".strip(),
        "scoring_notice": texts["scoring_notice"],
        "appeal_contact": f"{texts['appeal_notice']} 문의: {contact}",
        "connection_gaps": await gaps(db, session),
        "retention_notice": texts["retention_notice"].format(days=texts["retention_days"]),
        "contact_email": contact,
        "view_until": iso(debrief_until(session)),
        "survey": {
            "submitted": survey_row is not None,
            "questions": [
                {"q": q["q"], "text": q["text"], "kind": q["kind"]} for q in texts["survey"]
            ],
        },
    }
    if session.status == "failed" and session.failed_stage == "session":
        return {**base, "intro_notice": texts["failed_notice"], "failed_stage": "session"}
    fired = (
        await db.scalars(select(Observation.card_id).where(Observation.session_id == session.id))
    ).all()
    elements = {e["id"]: e for e in scenario["element_info"]}
    cards = [c for c in scenario["cards"] if c["card_id"] in set(fired)]
    mine = (
        await db.scalars(
            select(Message)
            .where(
                Message.session_id == session.id,
                Message.sender == "candidate",
                Message.channel == "room",
            )
            .order_by(Message.created_at)
        )
    ).all()
    my_messages = []
    for phase in sc.DEBATE_PHASES:
        in_phase = [m for m in mine if m.phase == phase]
        if in_phase:
            m = max(in_phase, key=lambda x: len(x.content))  # 같은 길이면 먼저 쓴 것
            my_messages.append(
                {
                    "id": str(m.id),
                    "content": m.content,
                    "phase": phase,
                    "t_min": t_min(session, m.created_at) or 0.0,
                }
            )
    proposal = await db.get(Proposal, session.id)
    personas = {p["seat"]: p for p in scenario["seats"]}
    return {
        **base,
        "elements": [
            {"element": e, "name": elements[e]["name"], "how_we_see": elements[e]["how_we_see"]}
            for e in scenario["elements"]
        ],
        "cards": [
            {
                "card_id": c["card_id"],
                "element": c["element"],
                "name": c.get("name", c["card_id"]),
                "description": c.get("debrief", ""),
            }
            for c in cards
        ],
        "seats": [{"seat": "candidate", "display_name": display_name(session, invite)}]
        + [
            {
                "seat": seat,
                "display_name": p["name"],
                "avatar_url": sc.avatar_url(scenario, p),
                "persona_type": p["persona_type"],
                "persona_description": p.get("persona_description", ""),
            }
            for seat, p in personas.items()
        ],
        "my_messages": my_messages[:3],
        "proposal": {"sections": proposal.submitted} if proposal and proposal.submitted else None,
    }
