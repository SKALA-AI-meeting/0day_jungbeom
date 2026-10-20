"""관리자 REST (/admin/*, 포트 8000). 계약은 docs/common/contracts.md.

모든 조회·변경은 JWT의 company_id로 positions를 거쳐 필터한다. 남의 회사 자원은 404다.
상태 전이는 SessionService가 하고, 이 파일은 평가표 조정과 리포트 합성만 직접 다룬다.
"""

import asyncio
import copy
import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    Principal,
    admin_token,
    hash_password,
    require_admin,
    verify_password,
)
from app.models import (
    Admin,
    Company,
    DocumentState,
    Invite,
    Message,
    Position,
    Report,
    RubricAdjustment,
    Session,
    SessionEvent,
    Task,
)
from app.services import scenario as scenario_service
from app.services.context import AppContext, get_context
from app.services.messages import t_min
from app.services.session import SessionError

router = APIRouter(prefix="/admin")

KST = timezone(timedelta(hours=9))

# 지원자에게 전하는 안내 문안. 발송은 하지 않고 화면이 복사 버튼으로 보여 준다.
CANDIDATE_NOTICE_TEMPLATE = (
    "안녕하세요, {alias}님. 이번 전형은 가상 회사 {virtual_company}에서 AI 동료와 함께 "
    "업무를 진행하는 시뮬레이션입니다.\n"
    "- 2시간 연속으로 진행하며 중간 휴식은 없습니다.\n"
    "- PC에서 진행하시길 권장합니다.\n"
    "- 아래 링크는 발급 후 72시간({expires_at}까지) 유효합니다.\n"
    "{invite_url}"
)
ELEMENT_FRACTION_RULE = (
    "리뷰에 붙는 카드를 뺀 요소 카드가 n개일 때, n=1이면 세션의 1/4 지점, "
    "n≥2이면 i번째(0부터)가 1/4 + i×(1/2)/n 지점이다. 흐름 카드는 고정 시점이다."
)


def error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"error": {"code": code, "message": message}})


async def get_db(ctx: Annotated[AppContext, Depends(get_context)]):
    async with ctx.session_factory() as db:
        yield db


Ctx = Annotated[AppContext, Depends(get_context)]
Db = Annotated[AsyncSession, Depends(get_db)]
Admin_ = Annotated[Principal, Depends(require_admin)]


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


# ───────────── 가입·로그인 ─────────────


class Credentials(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class Signup(Credentials):
    company_name: str = Field(min_length=1)


@router.post("/auth/signup")
async def signup(body: Signup, db: Db) -> dict[str, str]:
    taken = await db.scalar(select(Admin.id).where(Admin.email == body.email))
    if taken is not None:
        raise error(409, "conflict", "email already registered")
    company = Company(name=body.company_name)
    db.add(company)
    await db.flush()
    password_hash = await asyncio.to_thread(hash_password, body.password)
    admin = Admin(company_id=company.id, email=body.email, password_hash=password_hash)
    db.add(admin)
    try:
        await db.commit()
    except IntegrityError as exc:  # 동시 가입
        await db.rollback()
        raise error(409, "conflict", "email already registered") from exc
    return {"token": admin_token(admin.id, company.id)}


@router.post("/auth/login")
async def login(body: Credentials, db: Db) -> dict[str, str]:
    admin = (await db.execute(select(Admin).where(Admin.email == body.email))).scalar_one_or_none()
    if admin is None or not await asyncio.to_thread(
        verify_password, body.password, admin.password_hash
    ):
        raise error(401, "unauthorized", "invalid email or password")
    return {"token": admin_token(admin.id, admin.company_id)}


# ───────────── 카탈로그·채용 건 ─────────────


@router.get("/catalog")
async def catalog(ctx: Ctx, _: Admin_) -> dict[str, Any]:
    data = scenario_service.load_catalog(ctx.settings.scenarios_dir)
    return {
        "elements": [
            {
                "id": card["id"],
                "name": card["name"],
                "situation_public": card["situation"],
                "rubric": [
                    {
                        "id": item["id"],
                        "text": item["text"],
                        "pilot_value": bool(item.get("pilot_value")),
                    }
                    for item in card["rubric"]
                ],
            }
            for card in sorted(data["element_cards"], key=lambda c: c["order"])
        ],
        "timeline": {
            "flow": [
                {"card_id": flow["id"], "at_fraction": flow["at_fraction"]}
                for flow in data["flow_cards"]
            ],
            "element_fraction_rule": ELEMENT_FRACTION_RULE,
        },
        "candidate_notice_template": CANDIDATE_NOTICE_TEMPLATE,
        "session_minutes": 120,
    }


class PositionIn(BaseModel):
    name: str = Field(min_length=1)
    elements: list[str]


@router.get("/positions")
async def list_positions(db: Db, admin: Admin_) -> list[dict[str, Any]]:
    count = (
        select(Invite.position_id, func.count().label("n")).group_by(Invite.position_id).subquery()
    )
    rows = await db.execute(
        select(Position, func.coalesce(count.c.n, 0))
        .outerjoin(count, count.c.position_id == Position.id)
        .where(Position.company_id == admin.company_id)
        .order_by(Position.created_at)
    )
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "elements": p.elements,
            "candidate_count": n,
            "created_at": iso(p.created_at),
        }
        for p, n in rows
    ]


@router.post("/positions")
async def create_position(body: PositionIn, ctx: Ctx, db: Db, admin: Admin_) -> dict[str, Any]:
    try:
        scenario, version = scenario_service.build_scenario(
            ctx.settings.scenarios_dir, body.elements, 120
        )
    except scenario_service.InvalidElements as exc:
        raise error(400, "invalid_elements", str(exc)) from exc
    position = Position(
        company_id=admin.company_id,
        name=body.name,
        elements=body.elements,
        session_minutes=120,
        catalog_version=version,
        scenario=scenario,
    )
    db.add(position)
    await db.commit()
    return {
        "id": str(position.id),
        "name": position.name,
        "elements": position.elements,
        "scenario": scenario,
        "catalog_version": version,
    }


async def own_position(db: AsyncSession, admin: Principal, position_id: uuid.UUID) -> Position:
    position = (
        await db.execute(
            select(Position).where(
                Position.id == position_id, Position.company_id == admin.company_id
            )
        )
    ).scalar_one_or_none()
    if position is None:
        raise error(404, "not_found", "position not found")
    return position


async def own_session(
    db: AsyncSession, admin: Principal, session_id: uuid.UUID
) -> tuple[Session, Invite, Position]:
    row = (
        await db.execute(
            select(Session, Invite, Position)
            .join(Invite, Session.invite_id == Invite.id)
            .join(Position, Invite.position_id == Position.id)
            .where(Session.id == session_id, Position.company_id == admin.company_id)
        )
    ).first()
    if row is None:
        raise error(404, "not_found", "session not found")
    return row[0], row[1], row[2]


# ───────────── 평가표 합산 ─────────────


def tally(values: list[int | None]) -> dict[str, int]:
    return {
        "met": sum(v == 1 for v in values),
        "judged": sum(v is not None for v in values),
        "no_record": sum(v is None for v in values),
    }


def _final_value(item: dict[str, Any], adjustments: dict[str, RubricAdjustment]) -> int | None:
    adjustment = adjustments.get(item["id"])
    return adjustment.reviewer_value if adjustment else item.get("auto")


def reviewer_scores(
    rubric: dict[str, Any], adjustments: dict[str, RubricAdjustment]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """담당자 값(조정이 없으면 자동 값)으로 센 (요소별, 합계)."""
    per_element, everything = [], []
    for element in rubric.get("elements", []):
        values = [_final_value(item, adjustments) for item in element["items"]]
        per_element.append({"element": element["element"], **tally(values)})
        everything += values
    return per_element, tally(everything)


def merge_rubric(
    rubric: dict[str, Any],
    adjustments: list[RubricAdjustment],
    report: Report,
    submitted: bool,
) -> dict[str, Any]:
    """저장된 draft의 rubric에 rubric_adjustments를 병합한 GET 응답용 사본."""
    merged = copy.deepcopy(rubric)
    by_item = {a.item_id: a for a in adjustments}
    for element in merged.get("elements", []):
        for item in element["items"]:
            adjustment = by_item.get(item["id"])
            item["reviewer"] = adjustment.reviewer_value if adjustment else None
            item["memo"] = adjustment.memo if adjustment else None
            item["adjusted"] = adjustment is not None
        element["reviewer"] = None
    merged["reviewer_total"] = None
    merged["review"] = None
    if submitted:
        per_element, total = reviewer_scores(merged, by_item)
        for element, score in zip(merged["elements"], per_element, strict=True):
            element["reviewer"] = {k: score[k] for k in ("met", "judged", "no_record")}
        merged["reviewer_total"] = total
        merged["review"] = {"memo": report.review_memo, "reviewed_at": iso(report.reviewed_at)}
    merged["history"] = [
        {
            "item_id": a.item_id,
            "element": a.element,
            "auto": a.auto_value,
            "reviewer": a.reviewer_value,
            "memo": a.memo,
            "created_at": iso(a.created_at),
        }
        for a in sorted(adjustments, key=lambda a: a.created_at)
    ]
    return merged


def is_submitted(report: Report) -> bool:
    return report.reviewer_met is not None


# ───────────── 지원자 목록·초대·취소 ─────────────


def display_status(session: Session, invite: Invite, now: datetime) -> str:
    if session.status == "invited" and invite.expires_at <= now:
        return "expired"
    return session.status


def score_of(
    report: Report | None, adjustments: dict[str, RubricAdjustment]
) -> dict[str, Any] | None:
    if report is None:
        return None
    rubric = report.content.get("rubric", {})
    if is_submitted(report):
        by_element, total = reviewer_scores(rubric, adjustments)
        return {**total, "source": "reviewer", "by_element": by_element}
    by_element = [
        {"element": e["element"], "met": e["auto"]["met"], "judged": e["auto"]["judged"]}
        for e in rubric.get("elements", [])
    ]
    total = rubric.get("auto_total") or {"met": 0, "judged": 0, "no_record": 0}
    return {
        "met": total["met"],
        "judged": total["judged"],
        "no_record": total["no_record"],
        "source": "auto",
        "by_element": by_element,
    }


@router.get("/positions/{position_id}/candidates")
async def candidates(position_id: uuid.UUID, db: Db, admin: Admin_) -> list[dict[str, Any]]:
    await own_position(db, admin, position_id)
    rows = (
        await db.execute(
            select(Invite, Session, Report)
            .join(Session, Session.invite_id == Invite.id)
            .outerjoin(Report, Report.session_id == Session.id)
            .where(Invite.position_id == position_id)
            .order_by(Invite.created_at)
        )
    ).all()
    adjustments: dict[uuid.UUID, dict[str, RubricAdjustment]] = {}
    submitted = [s.id for _, s, r in rows if r is not None and is_submitted(r)]
    if submitted:
        found = await db.execute(
            select(RubricAdjustment).where(RubricAdjustment.session_id.in_(submitted))
        )
        for adjustment in found.scalars():
            adjustments.setdefault(adjustment.session_id, {})[adjustment.item_id] = adjustment
    now = datetime.now(UTC)
    result = []
    for invite, session, report in rows:
        row: dict[str, Any] = {
            "session_id": str(session.id),
            "alias": invite.alias,
            "status": session.status,
            "display_status": display_status(session, invite, now),
            "invited_at": iso(invite.created_at),
            "report_ready_at": iso(report.generated_at) if report else None,
            "score": score_of(report, adjustments.get(session.id, {})),
        }
        if session.failed_stage:
            row["failed_stage"] = session.failed_stage
            row["failed_reason"] = session.failed_reason
        if invite.previous_session_id:
            row["previous_session_id"] = str(invite.previous_session_id)
        result.append(row)
    return result


class InviteIn(BaseModel):
    alias: str = Field(min_length=1)
    email: str = Field(min_length=3)
    previous_session_id: uuid.UUID | None = None


@router.post("/positions/{position_id}/invites")
async def create_invite(
    position_id: uuid.UUID, body: InviteIn, ctx: Ctx, db: Db, admin: Admin_
) -> dict[str, Any]:
    position = await own_position(db, admin, position_id)
    if body.previous_session_id is not None:
        await own_session(db, admin, body.previous_session_id)
    session, invite, raw = await ctx.session_service(db).create_for_invite(
        position.id, body.alias, body.email, body.previous_session_id
    )
    invite_url = f"{ctx.settings.web_origins[0]}/s/{raw}"
    notice = CANDIDATE_NOTICE_TEMPLATE.format(
        alias=body.alias,
        virtual_company=position.scenario["company"]["name"],
        expires_at=invite.expires_at.astimezone(KST).strftime("%Y-%m-%d %H:%M KST"),
        invite_url=invite_url,
    )
    return {
        "session_id": str(session.id),
        "invite_url": invite_url,
        "expires_at": iso(invite.expires_at),
        "notice_text": notice,
    }


@router.post("/sessions/{session_id}/cancel")
async def cancel(session_id: uuid.UUID, ctx: Ctx, db: Db, admin: Admin_) -> dict[str, str]:
    await own_session(db, admin, session_id)
    session = await ctx.session_service(db).cancel(session_id)
    return {"status": session.status}


# ───────────── 리포트 조회 ─────────────


def _assignee(part_no: int, tasks: dict[int, str], division: dict[str, Any] | None) -> str | None:
    if part_no in tasks:
        return tasks[part_no]
    parts = (division or {}).get("parts") or {}
    return parts.get(str(part_no))


async def _deliverable(db: AsyncSession, session: Session, position: Position) -> dict[str, Any]:
    states = {
        s.part_no: s
        for s in (
            await db.execute(select(DocumentState).where(DocumentState.session_id == session.id))
        ).scalars()
    }
    tasks = {
        t.part_no: t.assignee
        for t in (await db.execute(select(Task).where(Task.session_id == session.id))).scalars()
    }
    parts = []
    for key, title in sorted(position.scenario["parts"].items(), key=lambda kv: int(kv[0])):
        part_no = int(key)
        state = states.get(part_no)
        content = state.content if state else ""
        parts.append(
            {
                "part_no": part_no,
                "title": title,
                "assignee": _assignee(part_no, tasks, session.division),
                "content": content,
                "revisions": state.revision if state else 0,
                "empty": not content.strip(),
            }
        )
    return {
        "parts": parts,
        "division_decided_by": (session.division or {}).get("decided_by"),
        "final_report_message": await _final_report_message(db, session),
    }


async def _final_report_message(db: AsyncSession, session: Session) -> dict[str, Any] | None:
    """보고 요청 카드 이후 지원자가 팀 채널에 남긴 마지막 메시지."""
    due_at = await db.scalar(
        select(SessionEvent.due_at).where(
            SessionEvent.session_id == session.id, SessionEvent.card_id == "report_request"
        )
    )
    if due_at is None:
        return None
    message = (
        await db.execute(
            select(Message)
            .where(
                Message.session_id == session.id,
                Message.sender == "candidate",
                Message.channel == "team",
                Message.created_at >= due_at,
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if message is None:
        return None
    return {"id": str(message.id), "t_min": t_min(message, session), "content": message.content}


async def _adjustments(db: AsyncSession, session_id: uuid.UUID) -> list[RubricAdjustment]:
    rows = await db.execute(
        select(RubricAdjustment)
        .where(RubricAdjustment.session_id == session_id)
        .order_by(RubricAdjustment.created_at)
    )
    return list(rows.scalars())


@router.get("/sessions/{session_id}/report")
async def get_report(session_id: uuid.UUID, db: Db, admin: Admin_) -> dict[str, Any]:
    session, invite, position = await own_session(db, admin, session_id)
    report = await db.get(Report, session_id)
    if report is None:
        raise error(404, "not_found", "report not ready")
    content = copy.deepcopy(report.content)
    content.update(
        {
            "session_id": str(session.id),
            "alias": invite.alias,
            "stage": report.stage,
            "position": {"name": position.name, "elements": position.elements},
            "deliverable": await _deliverable(db, session, position),
            "rubric": merge_rubric(
                report.content.get("rubric", {}),
                await _adjustments(db, session_id),
                report,
                is_submitted(report),
            ),
            "generated_at": iso(report.generated_at),
            "reviewed_at": iso(report.reviewed_at),
        }
    )
    return content


# ───────────── 리뷰(담당자 조정 + 검토 완료) ─────────────


class Adjustment(BaseModel):
    item_id: str
    value: Literal[0, 1] | None
    memo: str = ""


class ReviewIn(BaseModel):
    adjustments: list[Adjustment] = []
    memo: str | None = None


def _auto_values(report: Report) -> dict[str, int | None]:
    return {
        item["id"]: item.get("auto")
        for element in report.content.get("rubric", {}).get("elements", [])
        for item in element["items"]
    }


def _scenario_elements(position: Position) -> dict[str, str]:
    """평가표 item_id → 요소 id."""
    return {
        item["id"]: card["element"]
        for card in position.scenario["cards"]
        if card.get("element")
        for item in card.get("rubric", [])
    }


def _effective(
    body: ReviewIn, autos: dict[str, int | None], elements: dict[str, str]
) -> dict[str, tuple[int | None, str]]:
    """자동 값과 다른 항목만 {item_id: (값, 메모)}로. 규칙 위반은 400."""
    seen: set[str] = set()
    changes: dict[str, tuple[int | None, str]] = {}
    for adjustment in body.adjustments:
        if adjustment.item_id not in elements:
            raise error(400, "invalid_item", f"unknown item: {adjustment.item_id}")
        if adjustment.item_id in seen:
            raise error(400, "duplicate_item", f"duplicate item: {adjustment.item_id}")
        seen.add(adjustment.item_id)
        memo = adjustment.memo.strip()
        if adjustment.value == autos.get(adjustment.item_id):
            continue
        if not memo:
            raise error(400, "memo_required", f"memo required: {adjustment.item_id}")
        changes[adjustment.item_id] = (adjustment.value, memo)
    return changes


@router.post("/sessions/{session_id}/review")
async def review(
    session_id: uuid.UUID, body: ReviewIn, ctx: Ctx, db: Db, admin: Admin_
) -> dict[str, str]:
    _, _, position = await own_session(db, admin, session_id)
    # 같은 세션의 동시 검토를 직렬화한다. 조정 저장·합계·approving 전이는 한 트랜잭션이다.
    session = (
        await db.execute(
            select(Session)
            .where(Session.id == session_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    report = await db.get(Report, session_id, populate_existing=True)
    if report is None or session.status not in ("report_ready", "approving", "reviewed"):
        raise SessionError("conflict", f"cannot review from {session.status}")

    elements = _scenario_elements(position)
    autos = _auto_values(report)
    memo = (body.memo or "").strip()

    if session.status != "report_ready":
        # 이미 제출된 리뷰: 본문 검증보다 already_reviewed(409)가 먼저다
        try:
            changes = _effective(body, autos, elements)
        except HTTPException:
            changes = None
        stored = {a.item_id: (a.reviewer_value, a.memo) for a in await _adjustments(db, session_id)}
        if changes == stored and memo == (report.review_memo or ""):
            return {"status": session.status}
        raise error(409, "already_reviewed", "review already submitted with different content")
    changes = _effective(body, autos, elements)

    rows = [
        RubricAdjustment(
            session_id=session_id,
            element=elements[item_id],
            item_id=item_id,
            auto_value=autos.get(item_id),
            reviewer_value=value,
            memo=item_memo,
            admin_id=admin.subject,
        )
        for item_id, (value, item_memo) in changes.items()
    ]
    db.add_all(rows)
    _, total = reviewer_scores(report.content.get("rubric", {}), {r.item_id: r for r in rows})
    report.reviewer_met = total["met"]
    report.reviewer_judged = total["judged"]
    report.review_memo = memo or None
    session = await ctx.session_service(db).approve(session_id)  # 한 번 커밋
    return {"status": session.status}
