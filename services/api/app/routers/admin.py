"""관리자 REST(/admin, 포트 8000). 모든 조회는 JWT의 company_id로 필터한다."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth import Principal, admin_token, hash_password, require_admin, verify_password
from app.models import Admin, Company, Invite, Position, Report, ReportNote, Session
from app.services import admin as admin_service
from app.services import reports
from app.services import session as session_service
from app.services.common import Effects, ServiceError, conflict, invalid, iso, not_found
from app.services.context import AppContext, get_context

router = APIRouter(prefix="/admin")
Ctx = Annotated[AppContext, Depends(get_context)]
AdminP = Annotated[Principal, Depends(require_admin)]


class SignupIn(BaseModel):
    email: str
    password: str
    company_name: str


@router.post("/auth/signup")
async def signup(body: SignupIn, ctx: Ctx) -> dict[str, str]:
    async with ctx.session_factory() as db:
        company = Company(name=body.company_name)
        db.add(company)
        await db.flush()
        admin = Admin(
            company_id=company.id, email=body.email, password_hash=hash_password(body.password)
        )
        db.add(admin)
        try:
            await db.commit()
        except IntegrityError as exc:
            raise conflict("conflict", "email already exists") from exc
        return {"token": admin_token(admin.id, company.id)}


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
async def login(body: LoginIn, ctx: Ctx) -> dict[str, str]:
    async with ctx.session_factory() as db:
        admin = await db.scalar(select(Admin).where(Admin.email == body.email))
        if admin is None or not verify_password(body.password, admin.password_hash):
            raise ServiceError(401, "unauthorized", "invalid credentials")
        return {"token": admin_token(admin.id, admin.company_id)}


@router.get("/catalog")
async def catalog(ctx: Ctx, _: AdminP) -> dict[str, Any]:
    from app.services import scenario as sc

    scenario = sc.assemble(ctx.settings.scenarios_dir, sc.DEFAULT_MISSION, 60)
    return {
        "elements": [
            {
                "id": e["id"],
                "name": e["name"],
                "meaning": e["meaning"],
                "how_we_see": e["how_we_see"],
            }
            for e in scenario["element_info"]
        ],
        "session_minutes_options": [60, 15],
        "default_session_minutes": 60,
        "candidate_notice_template": scenario["admin_catalog"]["candidate_notice_template"],
        "candidate_faq": scenario["admin_catalog"]["candidate_faq"],
    }


@router.get("/positions")
async def positions(ctx: Ctx, principal: AdminP) -> list[dict[str, Any]]:
    async with ctx.session_factory() as db:
        rows = (
            await db.scalars(
                select(Position)
                .where(Position.company_id == principal.company_id)
                .order_by(Position.created_at)
            )
        ).all()
        out = []
        for p in rows:
            count = await db.scalar(select(func.count()).where(Invite.position_id == p.id))
            out.append(
                {
                    "id": str(p.id),
                    "name": p.name,
                    "session_minutes": p.session_minutes,
                    "candidate_count": count,
                    "created_at": iso(p.created_at),
                }
            )
        return out


class PositionIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    session_minutes: int = 60
    mission_id: str = "debate"


@router.post("/positions")
async def create_position(body: PositionIn, ctx: Ctx, principal: AdminP) -> dict[str, Any]:
    if "elements" in (body.model_extra or {}):
        raise invalid("invalid_input", "element selection is not supported")
    async with ctx.session_factory() as db:
        position = await admin_service.create_position(
            db,
            principal.company_id,
            name=body.name,
            session_minutes=body.session_minutes,
            mission_id=body.mission_id,
            scenarios_dir=ctx.settings.scenarios_dir,
            now=ctx.clock.now(),
        )
        await db.commit()
        return admin_service.position_created(position)


async def _position(db, principal: Principal, position_id: uuid.UUID) -> Position:
    position = await db.get(Position, position_id)
    if position is None or position.company_id != principal.company_id:
        raise not_found("position not found")
    return position


@router.get("/positions/{position_id}/candidates")
async def candidates(position_id: uuid.UUID, ctx: Ctx, principal: AdminP) -> list[dict]:
    async with ctx.session_factory() as db:
        position = await _position(db, principal, position_id)
        return await admin_service.candidate_rows(db, position, ctx.clock.now())


class InviteIn(BaseModel):
    alias: str | None = None
    email: str
    previous_session_id: uuid.UUID | None = None


@router.post("/positions/{position_id}/invites")
async def create_invite(
    position_id: uuid.UUID, body: InviteIn, ctx: Ctx, principal: AdminP
) -> dict[str, Any]:
    async with ctx.session_factory() as db:
        position = await _position(db, principal, position_id)
        session, inv, raw = await admin_service.invite(
            db,
            position,
            alias=body.alias,
            email=body.email,
            previous_session_id=body.previous_session_id,
            now=ctx.clock.now(),
        )
        await db.commit()
        return session_service.invite_response(
            session, inv, raw, position, ctx.settings.web_base_url
        )


@router.post("/sessions/{session_id}/reissue")
async def reissue(session_id: uuid.UUID, ctx: Ctx, principal: AdminP) -> dict[str, Any]:
    async with ctx.session_factory() as db:
        session, inv, position = await admin_service.company_session(
            db, principal.company_id, session_id
        )
        raw = session_service.reissue(inv, session, ctx.clock.now())
        await db.commit()
        return session_service.invite_response(
            session, inv, raw, position, ctx.settings.web_base_url
        )


@router.post("/sessions/{session_id}/cancel")
async def cancel(session_id: uuid.UUID, ctx: Ctx, principal: AdminP) -> dict[str, str]:
    fx = Effects()
    async with ctx.session_factory() as db:
        await admin_service.company_session(db, principal.company_id, session_id)
        session = await db.get(Session, session_id, with_for_update=True)
        session_service.cancel(session, ctx.clock.now(), fx)
        await db.commit()
    await ctx.apply(session_id, fx)
    return {"status": "cancelled"}


@router.get("/sessions/{session_id}/report")
async def report(session_id: uuid.UUID, ctx: Ctx, principal: AdminP) -> dict[str, Any]:
    async with ctx.session_factory() as db:
        session, inv, position = await admin_service.company_session(
            db, principal.company_id, session_id
        )
        merged = await reports.merged_report(db, session, position, inv)
        if merged is None:
            raise not_found("report not found")
        return merged


@router.post("/sessions/{session_id}/report/regenerate")
async def regenerate(session_id: uuid.UUID, ctx: Ctx, principal: AdminP) -> dict[str, str]:
    fx = Effects()
    async with ctx.session_factory() as db:
        await admin_service.company_session(db, principal.company_id, session_id)
        session = await db.get(Session, session_id, with_for_update=True)
        await session_service.regenerate(db, session, fx)
        await db.commit()
    await ctx.apply(session_id, fx)
    return {"status": "completed"}


@router.post("/sessions/{session_id}/review")
async def review(
    session_id: uuid.UUID, body: dict[str, Any], ctx: Ctx, principal: AdminP
) -> dict[str, str]:
    fx = Effects()
    async with ctx.session_factory() as db:
        _s, _inv, position = await admin_service.company_session(
            db, principal.company_id, session_id
        )
        session = await db.get(Session, session_id, with_for_update=True)
        if not isinstance(body.get("adjustments", []), list):
            raise invalid("invalid_input", "adjustments must be a list")
        result = await reports.review(
            db, session, position, principal.subject, body, ctx.clock.now(), fx
        )
        await db.commit()
    await ctx.apply(session_id, fx)
    return result


class NoteIn(BaseModel):
    text: str
    reviewer_name: str


@router.post("/sessions/{session_id}/report/notes")
async def notes(session_id: uuid.UUID, body: NoteIn, ctx: Ctx, principal: AdminP) -> dict:
    async with ctx.session_factory() as db:
        session, _inv, _p = await admin_service.company_session(
            db, principal.company_id, session_id
        )
        if (
            session.status not in ("approving", "reviewed")
            or await db.get(Report, session_id) is None
        ):
            raise conflict("conflict", "notes only after review")
        if not body.text.strip() or not body.reviewer_name.strip():
            raise invalid("invalid_input", "text and reviewer_name required")
        db.add(
            ReportNote(
                session_id=session_id,
                text=body.text.strip(),
                reviewer_name=body.reviewer_name.strip(),
                admin_id=principal.subject,
                created_at=ctx.clock.now(),
            )
        )
        await db.commit()
        rows = (
            await db.scalars(
                select(ReportNote)
                .where(ReportNote.session_id == session_id)
                .order_by(ReportNote.created_at)
            )
        ).all()
        return {
            "notes": [
                {
                    "id": str(n.id),
                    "text": n.text,
                    "reviewer_name": n.reviewer_name,
                    "created_at": iso(n.created_at),
                }
                for n in rows
            ]
        }


@router.get("/sessions/{session_id}/record")
async def record(session_id: uuid.UUID, ctx: Ctx, principal: AdminP) -> list[dict[str, Any]]:
    async with ctx.session_factory() as db:
        session, _inv, _p = await admin_service.company_session(
            db, principal.company_id, session_id
        )
        return await reports.record(db, session)
