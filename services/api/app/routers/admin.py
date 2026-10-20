"""관리자 REST (/admin/*, 포트 8000). 계약은 docs/common/contracts.md.

모든 조회·변경은 JWT의 company_id로 positions를 거쳐 필터한다. 남의 회사 자원은 404다. 상태 전이는
SessionService가 하고, 이 파일은 평가표 조정·메모와 리포트 합성(산출물·조정·메모·끊김 병합)만 직접
다룬다. 저장된 reports.content는 불변이고 GET 응답은 매번 합성한다.
"""

import asyncio
import copy
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, admin_token, hash_password, require_admin, verify_password
from app.models import (
    Admin,
    Company,
    Document,
    DocumentOpen,
    DocumentShare,
    DocumentVersion,
    Invite,
    Message,
    Position,
    Report,
    ReportNote,
    RubricAdjustment,
    Session,
)
from app.services import documents, views
from app.services import scenario as scenario_service
from app.services.context import AppContext, get_context
from app.services.messages import t_min_at
from app.services.states import SessionError

router = APIRouter(prefix="/admin")

RETENTION = timedelta(days=90)
# 목록의 다섯 묶음(화면 필터 키)
GROUPS = {
    "invited": "waiting",
    "expired": "waiting",
    "in_progress": "in_progress",
    "reporting": "in_progress",
    "completed": "in_progress",
    "report_ready": "needs_review",
    "approving": "done",
    "reviewed": "done",
    "failed": "problem",
    "cancelled": "problem",
}
NEXT_ACTION = {"session": "새 초대를 만들어 보내세요", "report": "리포트를 다시 생성하세요"}


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
    """채용 건 생성 화면용. 요소의 뜻과 "이렇게 봅니다"만 주고 상황·시점·평가표는 주지 않는다."""
    root = ctx.settings.scenarios_dir
    missions = [
        scenario_service.load_catalog(root, mission_id)
        for mission_id in scenario_service.list_missions(root)
    ]
    default = scenario_service.load_catalog(root)
    return {
        "missions": [
            {
                "id": m["mission"]["id"],
                "name": m["mission"]["name"],
                "company_name": m["mission"]["company"]["name"],
                "deliverable": m["mission"]["deliverable"],
                "documents": [
                    {"doc_id": d["id"], "title": d["title"]} for d in m["mission"]["documents"]
                ],
            }
            for m in missions
        ],
        "elements": [
            {k: e[k] for k in ("id", "name", "meaning", "how_we_see", "if_unselected")}
            for e in default["cards"]["elements"]
        ],
        "candidate_notice_template": default["mission"]["candidate_notice_template"],
        "candidate_faq": default["mission"]["candidate_faq"],
        "session_minutes": 120,
    }


class PositionIn(BaseModel):
    name: str = Field(min_length=1)
    elements: list[str]
    mission_id: str = scenario_service.DEFAULT_MISSION


@router.get("/positions")
async def list_positions(db: Db, admin: Admin_) -> list[dict[str, Any]]:
    # 지원자 수는 사람 수다. 재응시·재발행은 같은 별칭으로 이어지므로 별칭으로 센다
    people = (
        select(Invite.position_id, func.count(func.distinct(Invite.alias)).label("n"))
        .group_by(Invite.position_id)
        .subquery()
    )
    rows = await db.execute(
        select(Position, func.coalesce(people.c.n, 0))
        .outerjoin(people, people.c.position_id == Position.id)
        .where(Position.company_id == admin.company_id)
        .order_by(Position.created_at)
    )
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "mission_id": p.mission_id,
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
            ctx.settings.scenarios_dir, body.elements, 120, body.mission_id
        )
    except scenario_service.InvalidMission as exc:
        raise error(422, "invalid_mission", str(exc)) from exc
    except scenario_service.InvalidElements as exc:
        raise error(422, "invalid_elements", str(exc)) from exc
    position = Position(
        company_id=admin.company_id,
        name=body.name,
        mission_id=body.mission_id,
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
        "mission_id": position.mission_id,
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
            .execution_options(populate_existing=True)
        )
    ).first()
    if row is None:
        raise error(404, "not_found", "session not found")
    return row[0], row[1], row[2]


# ───────────── 평가표 합산 ─────────────


def tally(values: list[int | None]) -> dict[str, int]:
    return {
        "met": sum(v == 1 for v in values),
        "unmet": sum(v == 0 for v in values),
        "no_record": sum(v is None for v in values),
    }


def rubric_items(rubric: dict[str, Any]):
    """(요소 id, 카드 id, 항목) 순회."""
    for element in rubric.get("elements", []):
        for card in element.get("cards", []):
            for item in card["items"]:
                yield element["element"], card["card_id"], item


def _final_value(item: dict[str, Any], adjustments: dict[str, RubricAdjustment]) -> int | None:
    adjustment = adjustments.get(item["id"])
    return adjustment.reviewer_value if adjustment else item.get("auto")


def reviewer_scores(
    rubric: dict[str, Any], adjustments: dict[str, RubricAdjustment]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """담당자 값(조정이 없으면 자동 값)으로 센 (요소별, 합계)."""
    per_element: dict[str, list[int | None]] = {}
    for element, _, item in rubric_items(rubric):
        per_element.setdefault(element, []).append(_final_value(item, adjustments))
    everything = [v for values in per_element.values() for v in values]
    return (
        [{"element": e, **tally(values)} for e, values in per_element.items()],
        tally(everything),
    )


def is_submitted(report: Report) -> bool:
    return report.reviewer_met is not None


def merge_rubric(
    rubric: dict[str, Any], adjustments: list[RubricAdjustment], report: Report
) -> dict[str, Any]:
    """저장된 draft의 rubric에 rubric_adjustments를 병합한 GET 응답용 사본."""
    merged = copy.deepcopy(rubric)
    by_item = {a.item_id: a for a in adjustments}
    for _, _, item in rubric_items(merged):
        adjustment = by_item.get(item["id"])
        item["reviewer"] = adjustment.reviewer_value if adjustment else None
        item["memo"] = adjustment.memo if adjustment else None
        item["adjusted"] = adjustment is not None
    merged["reviewer_total"] = None
    merged["review"] = None
    if is_submitted(report):
        merged["reviewer_total"] = reviewer_scores(merged, by_item)[1]
        merged["review"] = {
            "memo": report.review_memo,
            "reviewer_name": report.reviewer_name,
            "reviewed_at": iso(report.reviewed_at),
        }
    return merged


def score_fields(report: Report | None, adjustments: dict[str, RubricAdjustment]) -> dict[str, Any]:
    """목록의 평탄화 점수. 리포트가 없으면 전부 null."""
    if report is None:
        return {k: None for k in ("met", "unmet", "no_record", "score_source", "by_element")}
    rubric = report.content.get("rubric", {})
    if is_submitted(report):
        by_element, total = reviewer_scores(rubric, adjustments)
        source = "reviewer"
    else:
        by_element = [
            {"element": e["element"], **{k: e["auto"][k] for k in ("met", "unmet", "no_record")}}
            for e in rubric.get("elements", [])
        ]
        total = rubric.get("auto_total") or tally([])
        source = "auto"
    return {
        **{k: total[k] for k in ("met", "unmet", "no_record")},
        "score_source": source,
        "by_element": by_element,
    }


# ───────────── 지원자 목록·초대·취소 ─────────────


def display_status(session: Session, invite: Invite, now: datetime) -> str:
    if session.status == "invited" and invite.expires_at <= now:
        return "expired"
    return session.status


def purge_at(session: Session) -> datetime | None:
    return session.completed_at + RETENTION if session.completed_at else None


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
    session_ids = [s.id for _, s, _ in rows]
    adjustments: dict[uuid.UUID, dict[str, RubricAdjustment]] = {}
    for a in (
        await db.execute(
            select(RubricAdjustment).where(RubricAdjustment.session_id.in_(session_ids))
        )
    ).scalars():
        adjustments.setdefault(a.session_id, {})[a.item_id] = a
    activity = {
        sid: (count, last)
        for sid, count, last in (
            await db.execute(
                select(Message.session_id, func.count(), func.max(Message.created_at))
                .where(Message.session_id.in_(session_ids), Message.sender == "candidate")
                .group_by(Message.session_id)
            )
        ).all()
    }
    by_id = {s.id: (s, i) for i, s, _ in rows}
    now = datetime.now(UTC)
    result = []
    for invite, session, report in rows:
        shown = display_status(session, invite, now)
        count, last = activity.get(session.id, (0, None))
        row: dict[str, Any] = {
            "session_id": str(session.id),
            "alias": invite.alias,
            "email": invite.email,
            "status": session.status,
            "display_status": shown,
            "display_group": GROUPS[shown],
            "invited_at": iso(invite.created_at),
        }
        optional = {
            "started_at": iso(session.started_at),
            "ends_at": iso(session.ends_at),
            "last_activity_at": iso(last),
        }
        row.update({k: v for k, v in optional.items() if v is not None})
        row["message_count"] = count
        if report is not None:
            row["report_ready_at"] = iso(report.generated_at)
        if purge_at(session):
            row["purge_at"] = iso(purge_at(session))
        if session.failed_stage:
            row["failed_stage"] = session.failed_stage
            row["failed_reason"] = session.failed_reason
            row["next_action"] = NEXT_ACTION[session.failed_stage]
        if invite.previous_session_id:
            row["previous_session_id"] = str(invite.previous_session_id)
            previous = by_id.get(invite.previous_session_id)
            expired = previous is not None and display_status(*previous, now) == "expired"
            row["previous_relation"] = "reissue" if expired else "retry"
        row.update(score_fields(report, adjustments.get(session.id, {})))
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
    """같은 채용 건 안 같은 별칭은 409. 단 재응시·재발행(previous_session_id)은 이전 응시의 별칭을
    잇는다.
    """
    position = await own_position(db, admin, position_id)
    previous_alias = None
    if body.previous_session_id is not None:
        previous, previous_invite, previous_position = await own_session(
            db, admin, body.previous_session_id
        )
        now = datetime.now(UTC)
        eligible = (
            (previous.status == "failed" and previous.failed_stage == "session")
            or previous.status == "cancelled"
            or display_status(previous, previous_invite, now) == "expired"
        )
        if not eligible or previous_position.id != position.id:
            raise error(
                422,
                "invalid_previous_session",
                "previous session must be failed(session), expired or cancelled in this position",
            )
        previous_alias = previous_invite.alias
    # 같은 채용 건의 초대 생성을 직렬화한다(별칭 중복 검사와 생성 사이에 다른 요청이 끼지 않게).
    # 잠금은 create_for_invite의 커밋에서 풀린다
    await db.execute(select(Position.id).where(Position.id == position.id).with_for_update())
    taken = await db.scalar(
        select(Invite.id).where(Invite.position_id == position.id, Invite.alias == body.alias)
    )
    if taken is not None and body.alias != previous_alias:
        raise error(409, "conflict", "alias already used in this position")
    session, invite, raw = await ctx.session_service(db).create_for_invite(
        position.id, body.alias, body.email, body.previous_session_id
    )
    invite_url = f"{ctx.settings.web_origins[0]}/s/{raw}"
    template = scenario_service.load_catalog(ctx.settings.scenarios_dir, position.mission_id)
    notice = template["mission"]["candidate_notice_template"].format(
        alias=body.alias, invite_url=invite_url
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


async def deliverable(db: AsyncSession, session: Session) -> dict[str, Any]:
    """최종본 섹션별 출처·편집 여부(편집한 동료 섹션은 원문 나란히)와 주고받은 문서 목록."""
    docs = {
        d.id: d
        for d in (
            await db.execute(select(Document).where(Document.session_id == session.id))
        ).scalars()
    }
    versions: dict[uuid.UUID, dict[int, DocumentVersion]] = {d: {} for d in docs}
    for v in (
        await db.execute(select(DocumentVersion).where(DocumentVersion.doc_id.in_(list(docs))))
    ).scalars():
        versions[v.doc_id][v.version] = v
    shares: dict[uuid.UUID, list[DocumentShare]] = {d: [] for d in docs}
    for s in (
        await db.execute(
            select(DocumentShare)
            .where(DocumentShare.doc_id.in_(list(docs)))
            .order_by(DocumentShare.created_at)
        )
    ).scalars():
        shares[s.doc_id].append(s)
    opened: dict[uuid.UUID, set[int]] = {d: set() for d in docs}
    for o in (
        await db.execute(select(DocumentOpen).where(DocumentOpen.doc_id.in_(list(docs))))
    ).scalars():
        opened[o.doc_id].add(o.version)

    final = await documents.final_view(db, session.id)
    sections = []
    for s in final.sections if final else []:
        source = docs.get(uuid.UUID(s["source_doc_id"])) if s["source_doc_id"] else None
        original = None
        if source is not None and source.owner == "colleague" and s["edited"]:
            found = versions[source.id].get(s["source_version"])
            original = found.content if found else None
        sections.append(
            {
                **s,
                "source_owner": source.owner if source else None,
                "source_content": original,
            }
        )
    final_doc = next((d for d in docs.values() if d.final), None)
    submitted = max(versions[final_doc.id]) if final_doc and versions[final_doc.id] else None

    listed = []
    for d in sorted(
        (d for d in docs.values() if not d.final), key=lambda d: (d.owner != "candidate", d.part_no)
    ):
        entry = {
            "doc_id": str(d.id),
            "owner": d.owner,
            "part_no": d.part_no,
            "title": d.title,
            "versions": len(versions[d.id]),
            "shares": [
                {
                    "version": s.version,
                    "channel": s.channel,
                    "t_min": t_min_at(s.created_at, session),
                }
                for s in shares[d.id]
            ],
        }
        if d.owner == "candidate":
            entry["empty"] = not d.content.strip()
        else:
            entry["opened_by_candidate"] = sorted(opened[d.id])
        listed.append(entry)
    return {
        "final": {"sections": sections, "submitted_version": submitted},
        "documents": listed,
        "division_decided_by": (session.division or {}).get("decided_by"),
        "final_report_message": await final_report_message(db, session),
    }


async def final_report_message(db: AsyncSession, session: Session) -> dict[str, Any] | None:
    """보고로 분류된(kind=report) 첫 지원자 메시지(팀 채널 또는 팀장 DM)."""
    message = await db.scalar(
        select(Message)
        .where(
            Message.session_id == session.id,
            Message.sender == "candidate",
            Message.channel.in_(("team", "manager_dm")),
            Message.meta["classification"]["kind"].astext == "report",
        )
        .order_by(Message.created_at)
        .limit(1)
    )
    if message is None:
        return None
    return {
        "id": str(message.id),
        "t_min": t_min_at(message.created_at, session),
        "content": message.content,
    }


async def _adjustments(db: AsyncSession, session_id: uuid.UUID) -> list[RubricAdjustment]:
    rows = await db.execute(
        select(RubricAdjustment)
        .where(RubricAdjustment.session_id == session_id)
        .order_by(RubricAdjustment.created_at)
    )
    return list(rows.scalars())


async def _notes(db: AsyncSession, session_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(ReportNote)
        .where(ReportNote.session_id == session_id)
        .order_by(ReportNote.created_at)
    )
    return [
        {
            "id": str(n.id),
            "text": n.text,
            "reviewer_name": n.reviewer_name,
            "created_at": iso(n.created_at),
        }
        for n in rows.scalars()
    ]


@router.get("/sessions/{session_id}/report")
async def get_report(session_id: uuid.UUID, db: Db, admin: Admin_) -> dict[str, Any]:
    session, invite, position = await own_session(db, admin, session_id)
    report = await db.get(Report, session_id, populate_existing=True)
    if report is None:
        raise error(404, "not_found", "report not ready")
    content = copy.deepcopy(report.content)
    content.update(
        {
            "session_id": str(session.id),
            "alias": invite.alias,
            "stage": report.stage,
            "position": {
                "name": position.name,
                "mission_id": position.mission_id,
                "elements": position.elements,
            },
            "deliverable": await deliverable(db, session),
            "rubric": merge_rubric(
                report.content.get("rubric", {}), await _adjustments(db, session_id), report
            ),
            "notes": await _notes(db, session_id),
            "connection_gaps": await views.connection_gaps(db, session),
            "generated_at": iso(report.generated_at),
            "reviewed_at": iso(report.reviewed_at),
            "purge_at": iso(purge_at(session)),
        }
    )
    return content


@router.post("/sessions/{session_id}/report/regenerate")
async def regenerate(session_id: uuid.UUID, ctx: Ctx, db: Db, admin: Admin_) -> dict[str, str]:
    await own_session(db, admin, session_id)
    session = await ctx.session_service(db).regenerate_report(session_id)
    return {"status": session.status}


@router.get("/sessions/{session_id}/record")
async def record(session_id: uuid.UUID, db: Db, admin: Admin_) -> list[dict[str, Any]]:
    session, _, _ = await own_session(db, admin, session_id)
    return await views.record(db, session)


# ───────────── 리뷰(담당자 조정 + 검토 완료)·메모 ─────────────


class Adjustment(BaseModel):
    item_id: str
    value: Literal[0, 1] | None
    memo: str = ""


class ReviewIn(BaseModel):
    adjustments: list[Adjustment] = []
    memo: str | None = None
    reviewer_name: str = Field(min_length=1)


def _auto_values(report: Report) -> dict[str, int | None]:
    return {
        item["id"]: item.get("auto")
        for _, _, item in rubric_items(report.content.get("rubric", {}))
    }


def _scenario_items(position: Position) -> dict[str, tuple[str, str]]:
    """평가표 item_id → (요소 id, 카드 id)."""
    return {
        item["id"]: (card["element"], card["card_id"])
        for card in position.scenario["cards"]
        if card.get("element")
        for item in card.get("rubric", [])
    }


def _effective(
    body: ReviewIn, autos: dict[str, int | None], items: dict[str, tuple[str, str]]
) -> dict[str, tuple[int | None, str]]:
    """자동 값과 다른 항목만 {item_id: (값, 메모)}로. 규칙 위반은 400."""
    seen: set[str] = set()
    changes: dict[str, tuple[int | None, str]] = {}
    for adjustment in body.adjustments:
        if adjustment.item_id not in items:
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

    items = _scenario_items(position)
    autos = _auto_values(report)
    memo = (body.memo or "").strip()
    name = body.reviewer_name.strip()

    if session.status != "report_ready":
        # 이미 제출된 리뷰: 본문 검증보다 already_reviewed(409)가 먼저다
        try:
            changes = _effective(body, autos, items)
        except HTTPException:
            changes = None
        stored = {a.item_id: (a.reviewer_value, a.memo) for a in await _adjustments(db, session_id)}
        same = (
            changes == stored
            and memo == (report.review_memo or "")
            and name == (report.reviewer_name or "")
        )
        if same:
            return {"status": session.status}
        raise error(409, "already_reviewed", "review already submitted with different content")
    changes = _effective(body, autos, items)

    rows = [
        RubricAdjustment(
            session_id=session_id,
            element=items[item_id][0],
            card_id=items[item_id][1],
            item_id=item_id,
            auto_value=autos.get(item_id),
            reviewer_value=value,
            memo=item_memo,
            reviewer_name=name,
            admin_id=admin.subject,
        )
        for item_id, (value, item_memo) in changes.items()
    ]
    db.add_all(rows)
    _, total = reviewer_scores(report.content.get("rubric", {}), {r.item_id: r for r in rows})
    report.reviewer_met = total["met"]
    report.reviewer_unmet = total["unmet"]
    report.reviewer_no_record = total["no_record"]
    report.review_memo = memo or None
    report.reviewer_name = name
    session = await ctx.session_service(db).approve(session_id)  # 한 번 커밋
    return {"status": session.status}


class NoteIn(BaseModel):
    text: str = Field(min_length=1)
    reviewer_name: str = Field(min_length=1)


@router.post("/sessions/{session_id}/report/notes")
async def add_note(
    session_id: uuid.UUID, body: NoteIn, db: Db, admin: Admin_
) -> dict[str, list[dict[str, Any]]]:
    """검토 완료 뒤(approving·reviewed) 메모 추가. 값은 바꾸지 않는다."""
    session, _, _ = await own_session(db, admin, session_id)
    if session.status not in ("approving", "reviewed"):
        raise SessionError("conflict", f"cannot add notes from {session.status}")
    db.add(
        ReportNote(
            session_id=session_id,
            text=body.text.strip(),
            reviewer_name=body.reviewer_name.strip(),
            admin_id=admin.subject,
        )
    )
    await db.commit()
    return {"notes": await _notes(db, session_id)}
