"""기획안: 조회·디바운스 저장(revision 검사)·제출. 제출 이후 쓰기는 409 session_ending."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Proposal, Session
from app.services import session as session_service
from app.services.clock import Clock
from app.services.common import Effects, conflict, invalid, iso, not_found


def serialize(proposal: Proposal | None, template: list[str]) -> dict[str, Any]:
    if proposal is None:
        return {
            "sections": {f: "" for f in template},
            "revision": 0,
            "updated_at": None,
            "submitted_at": None,
        }
    return {
        "sections": proposal.sections,
        "revision": proposal.revision,
        "updated_at": iso(proposal.updated_at),
        "submitted_at": iso(proposal.submitted_at),
    }


def internal(proposal: Proposal, session: Session) -> dict[str, Any]:
    """내부 GET /proposal: in_progress면 초안, completed 이후면 제출본."""
    sections = proposal.submitted if proposal.submitted is not None else proposal.sections
    return {
        "sections": sections,
        "revision": proposal.revision,
        "updated_at": iso(proposal.updated_at),
        "submitted_at": iso(proposal.submitted_at),
        "auto_submitted": proposal.auto_submitted,
    }


async def put(
    db: AsyncSession,
    session: Session,
    sections: dict[str, str],
    revision: int,
    template: list[str],
    clock: Clock,
) -> dict[str, Any]:
    if session.status != "in_progress":
        raise conflict("session_ending", "session is not in progress")
    if set(sections) != set(template) or not all(isinstance(v, str) for v in sections.values()):
        raise invalid("invalid_input", "sections must have the 6 template fields as strings")
    proposal = await db.get(Proposal, session.id, with_for_update=True)
    if proposal is None:
        raise not_found("proposal not found")
    if revision != proposal.revision:
        raise conflict("conflict", "revision mismatch")
    proposal.sections = dict(sections)
    proposal.revision += 1
    proposal.updated_at = clock.now()
    return {"revision": proposal.revision, "updated_at": iso(proposal.updated_at)}


async def submit(
    db: AsyncSession,
    session: Session,
    template: list[str],
    clock: Clock,
    fx: Effects,
    warning_shown: bool | None = None,
) -> dict[str, Any]:
    if session.status == "in_progress" and session.phase != "proposal":
        raise conflict("phase_not_open", "submit only in proposal phase")
    if session.status in ("cancelled", "failed", "invited"):
        raise conflict("conflict", f"cannot submit from {session.status}")
    proposal = await session_service.submit(
        db, session, "submitted", clock.now(), fx, template, warning_shown
    )
    return {
        "status": "completed",
        "completed_at": iso(session.completed_at),
        "submitted_at": iso(proposal.submitted_at),
    }
