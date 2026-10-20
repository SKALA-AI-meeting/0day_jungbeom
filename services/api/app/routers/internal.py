"""내부 REST (/internal/*, 포트 8001, X-Internal-Token). 계약은 docs/common/contracts.md.

business-mcp·rag-mcp·report-worker가 부른다. 권한·상태 검증(담당자, 세션 상태, 문서 공개 여부)의
최종 판단은 여기서 한다. 저장은 모두 멱등 키로 중복 없이 한 번만 만든다.
"""

import difflib
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_internal
from app.models import (
    AssistantCall,
    AssistantReuse,
    Company,
    DocumentRelease,
    DocumentRevision,
    DocumentState,
    DocView,
    Invite,
    Message,
    Observation,
    Position,
    Report,
    Session,
    SessionEvent,
    Task,
)
from app.services import scenario as scenario_service
from app.services.context import AppContext, get_context
from app.services.messages import save_internal_message, serialize
from app.services.session import SessionError

router = APIRouter(prefix="/internal", dependencies=[Depends(require_internal)])

Channel = Literal["team", "dm", "notice", "assistant"]
Assignee = Literal["candidate", "colleague", "both"]
E2E_COMPANY = "e2e 테스트 회사"


def error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"error": {"code": code, "message": message}})


async def get_db(ctx: Annotated[AppContext, Depends(get_context)]):
    async with ctx.session_factory() as db:
        yield db


Ctx = Annotated[AppContext, Depends(get_context)]
Db = Annotated[AsyncSession, Depends(get_db)]


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def load_session(db: AsyncSession, session_id: uuid.UUID) -> Session:
    session = await db.get(Session, session_id, populate_existing=True)
    if session is None:
        raise SessionError("not_found", "session not found")
    return session


async def load_position(db: AsyncSession, session: Session) -> Position:
    invite = await db.get(Invite, session.invite_id)
    return await db.get(Position, invite.position_id)


def with_meta(message: Message, session: Session) -> dict[str, Any]:
    """내부 API 전용: 공개 Message 형식에 meta(classification 포함)를 더한다."""
    return {**serialize(message, session), "meta": message.meta or {}}


def require_in_progress(session: Session, action: str) -> None:
    """in_progress일 때만 새 업무 변경을 받는다(제출 직후 종료 실행 중에도 in_progress)."""
    if session.status != "in_progress":
        raise SessionError("conflict", f"cannot {action} from {session.status}")


def task_json(task: Task) -> dict[str, Any]:
    return {"part_no": task.part_no, "assignee": task.assignee, "status": task.status}


# ───────────── 세션 컨텍스트·메시지 ─────────────


def current_element(events: list[SessionEvent], status: str) -> str | None:
    """열린 관찰 창의 요소. 가장 최근에 실행된 요소 카드의 요소다.

    흐름 카드와 결 메시지는 창을 닫지 않는다. 마지막 요소 창은 종료 실행(제출 뒤 in_progress)까지
    열려 있고, completed 이후에는 없다.
    """
    if status != "in_progress":
        return None
    fired = [e for e in events if e.status in ("fired", "done") and e.element and not e.texture]
    if not fired:
        return None
    return max(fired, key=lambda e: e.due_at).element


@router.get("/sessions/{session_id}")
async def get_session(session_id: uuid.UUID, db: Db) -> dict[str, Any]:
    session = await load_session(db, session_id)
    position = await load_position(db, session)
    events = (
        (await db.execute(select(SessionEvent).where(SessionEvent.session_id == session_id)))
        .scalars()
        .all()
    )
    minutes = None
    if session.started_at is not None:
        minutes = round((datetime.now(UTC) - session.started_at).total_seconds() / 60, 2)
    return {
        "id": str(session.id),
        "status": session.status,
        "position": {
            "elements": position.elements,
            "scenario": position.scenario,
            "catalog_version": position.catalog_version,
        },
        "division": session.division,
        "started_at": iso(session.started_at),
        "ends_at": iso(session.ends_at),
        "t_min_now": minutes,
        "current_element": current_element(list(events), session.status),
    }


@router.get("/sessions/{session_id}/messages")
async def list_messages(
    session_id: uuid.UUID,
    db: Db,
    since_t_min: float | None = None,
    channel: Channel | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[dict[str, Any]]:
    session = await load_session(db, session_id)
    query = select(Message).where(Message.session_id == session_id)
    if channel is not None:
        query = query.where(Message.channel == channel)
    if since_t_min is not None and session.started_at is not None:
        since = session.started_at + timedelta(minutes=since_t_min)
        query = query.where(Message.created_at > since)
    rows = await db.execute(query.order_by(Message.created_at, Message.seq).limit(limit))
    return [with_meta(m, session) for m in rows.scalars()]


class MessageIn(BaseModel):
    channel: Channel
    sender: Literal["colleague", "manager", "system"]
    content: str
    event_id: uuid.UUID | None = None
    run_id: uuid.UUID
    seq: int
    meta: dict[str, Any] | None = None


@router.post("/sessions/{session_id}/messages")
async def post_message(session_id: uuid.UUID, body: MessageIn, ctx: Ctx, db: Db):
    if body.event_id is not None:
        owner = await db.scalar(
            select(SessionEvent.session_id).where(SessionEvent.id == body.event_id)
        )
        if owner != session_id:
            raise error(422, "invalid_event", "event_id is not an event of this session")
    message, _ = await save_internal_message(
        db,
        ctx.hub,
        session_id,
        body.channel,
        body.sender,
        body.content,
        body.run_id,
        body.seq,
        body.event_id,
        body.meta,
    )
    session = await load_session(db, session_id)
    return with_meta(message, session)


class Classification(BaseModel):
    recipient: str
    kind: str
    instruction: str | None = None
    related_card: str | None = None


@router.put("/sessions/{session_id}/messages/{message_id}/classification")
async def put_classification(
    session_id: uuid.UUID, message_id: uuid.UUID, body: Classification, db: Db
) -> dict[str, Any]:
    session = await load_session(db, session_id)
    message = await db.get(Message, message_id, populate_existing=True)
    if message is None or message.session_id != session_id:
        raise error(404, "not_found", "message not found")
    message.meta = {**(message.meta or {}), "classification": body.model_dump()}
    await db.commit()
    return with_meta(message, session)


# ───────────── 분업·보드·문서 ─────────────


@router.get("/sessions/{session_id}/board")
async def board(session_id: uuid.UUID, db: Db) -> dict[str, Any]:
    await load_session(db, session_id)
    rows = await db.execute(
        select(Task).where(Task.session_id == session_id).order_by(Task.part_no)
    )
    return {"tasks": [task_json(t) for t in rows.scalars()]}


class TaskIn(BaseModel):
    status: Literal["todo", "doing", "done"]


@router.put("/sessions/{session_id}/tasks/{part_no}")
async def put_task(
    session_id: uuid.UUID, part_no: int, body: TaskIn, ctx: Ctx, db: Db
) -> dict[str, Any]:
    session = await load_session(db, session_id)
    task = await db.get(Task, (session_id, part_no), populate_existing=True)
    if task is None:
        raise error(404, "not_found", "task not found")
    if task.assignee != "colleague":
        raise error(403, "forbidden", "not a colleague task")
    require_in_progress(session, "change task")
    task.status = body.status
    await db.commit()
    await ctx.hub.broadcast(session_id, "task.updated", task_json(task))
    return task_json(task)


class DivisionIn(BaseModel):
    parts: dict[str, Assignee]
    decided_by: Literal["candidate", "colleague_default"]


def _check_division(parts: dict[str, str], scenario: dict[str, Any]) -> None:
    """모든 파트가 정해져야 하고, 최소 조건(division_min)을 지켜야 한다."""
    if set(parts) != {str(no) for no in scenario["parts"]}:
        raise error(422, "invalid_division", "every part must be assigned exactly once")
    rule = scenario["division_min"]
    if any(parts[str(no)] != "candidate" for no in rule["candidate_parts"]):
        raise error(422, "invalid_division", "required candidate parts are not candidate's")
    if not any(parts[str(no)] == "colleague" for no in rule["colleague_solo_any_of"]):
        raise error(422, "invalid_division", "colleague needs at least one solo part")


@router.put("/sessions/{session_id}/division")
async def put_division(session_id: uuid.UUID, body: DivisionIn, ctx: Ctx, db: Db):
    session = await load_session(db, session_id)
    if session.status != "in_progress":
        raise SessionError("conflict", f"cannot divide from {session.status}")
    position = await load_position(db, session)
    _check_division(body.parts, position.scenario)
    current = session.division or {}
    if current.get("parts") == body.parts and current.get("decided_by") == body.decided_by:
        return {"division": current}  # 재요청: 저장된 값 그대로, 브로드캐스트 없음
    session.division = {
        "parts": body.parts,
        "decided_by": body.decided_by,
        "decided_at": datetime.now(UTC).isoformat(),
    }
    stmt = insert(Task).values(
        [
            {"session_id": session_id, "part_no": int(no), "assignee": assignee}
            for no, assignee in body.parts.items()
        ]
    )
    await db.execute(
        stmt.on_conflict_do_update(
            index_elements=["session_id", "part_no"], set_={"assignee": stmt.excluded.assignee}
        )
    )
    await db.commit()
    tasks = (
        await db.execute(
            select(Task)
            .where(Task.session_id == session_id)
            .order_by(Task.part_no)
            .execution_options(populate_existing=True)
        )
    ).scalars()
    for task in tasks:
        await ctx.hub.broadcast(session_id, "task.updated", task_json(task))
    return {"division": session.division}


@router.get("/sessions/{session_id}/document")
async def get_document(session_id: uuid.UUID, db: Db) -> dict[str, Any]:
    await load_session(db, session_id)
    rows = await db.execute(
        select(DocumentState)
        .where(DocumentState.session_id == session_id)
        .order_by(DocumentState.part_no)
    )
    return {
        str(s.part_no): {"content": s.content, "revision": s.revision, "updated_by": s.updated_by}
        for s in rows.scalars()
    }


class DocumentIn(BaseModel):
    content: str
    by: Literal["colleague"]
    run_id: uuid.UUID


def change_ratio(old: str, new: str) -> float:
    """0이면 같고 1에 가까울수록 많이 바뀜."""
    if not old and not new:
        return 0.0
    return round(1 - difflib.SequenceMatcher(None, old, new).ratio(), 4)


@router.put("/sessions/{session_id}/document/{part_no}")
async def put_document(
    session_id: uuid.UUID, part_no: int, body: DocumentIn, ctx: Ctx, db: Db
) -> dict[str, Any]:
    session = await load_session(db, session_id)
    task = await db.get(Task, (session_id, part_no))
    if task is None or task.assignee != "colleague":
        raise error(403, "forbidden", "not a colleague part")
    # 파트 행을 잠가 같은 파트의 동시 쓰기와 같은 run_id 재요청을 직렬화한다
    state = (
        await db.execute(
            select(DocumentState)
            .where(DocumentState.session_id == session_id, DocumentState.part_no == part_no)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if state is None:
        raise error(404, "not_found", "document part not found")
    done = (
        await db.execute(
            select(DocumentRevision).where(
                DocumentRevision.session_id == session_id,
                DocumentRevision.part_no == part_no,
                DocumentRevision.run_id == body.run_id,
            )
        )
    ).scalar_one_or_none()
    if done is not None:
        replay = {"updated_at": iso(done.created_at), "revision": done.revision}
        await db.rollback()  # 파트 행 잠금을 푼다
        return replay
    require_in_progress(session, "write document")

    now = datetime.now(UTC)
    revision = state.revision + 1
    db.add(
        DocumentRevision(
            session_id=session_id,
            part_no=part_no,
            revision=revision,
            by="colleague",
            content=body.content,
            length=len(body.content),
            diff_ratio=change_ratio(state.content, body.content),
            run_id=body.run_id,
            created_at=now,
        )
    )
    state.content = body.content
    state.revision = revision
    state.updated_by = "colleague"
    state.updated_at = now
    await db.commit()
    await ctx.hub.broadcast(
        session_id,
        "document.part_updated",
        {"part_no": part_no, "content": body.content, "revision": revision, "by": "colleague"},
    )
    return {"updated_at": iso(now), "revision": revision}


@router.get("/sessions/{session_id}/document_revisions")
async def document_revisions(session_id: uuid.UUID, db: Db) -> list[dict[str, Any]]:
    await load_session(db, session_id)
    rows = await db.execute(
        select(DocumentRevision)
        .where(DocumentRevision.session_id == session_id)
        .order_by(DocumentRevision.created_at, DocumentRevision.part_no, DocumentRevision.revision)
    )
    return [
        {
            "id": str(r.id),
            "part_no": r.part_no,
            "revision": r.revision,
            "by": r.by,
            "content": r.content,
            "length": r.length,
            "diff_ratio": r.diff_ratio,
            "created_at": iso(r.created_at),
        }
        for r in rows.scalars()
    ]


# ───────────── 회사 문서 공개·열람 ─────────────


@router.get("/sessions/{session_id}/documents")
async def documents(session_id: uuid.UUID, db: Db) -> dict[str, Any]:
    session = await load_session(db, session_id)
    position = await load_position(db, session)
    released = set(
        (
            await db.execute(
                select(DocumentRelease.doc_id).where(
                    DocumentRelease.session_id == session_id,
                    DocumentRelease.released_at.is_not(None),
                )
            )
        ).scalars()
    )
    return {
        "catalog_version": position.catalog_version,
        "documents": [
            {"doc_id": d["doc_id"], "title": d["title"], "released": d["doc_id"] in released}
            for d in position.scenario["documents"]
        ],
    }


@router.post("/sessions/{session_id}/releases/{doc_id}")
async def release_document(
    session_id: uuid.UUID, doc_id: str, ctx: Ctx, db: Db
) -> dict[str, str | None]:
    session = await load_session(db, session_id)
    position = await load_position(db, session)
    titles = {d["doc_id"]: d["title"] for d in position.scenario["documents"]}
    if doc_id not in titles:
        raise error(404, "not_found", "document not found")
    now = datetime.now(UTC)
    row = (
        await db.execute(
            select(DocumentRelease)
            .where(DocumentRelease.session_id == session_id, DocumentRelease.doc_id == doc_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    newly = row is None or row.released_at is None
    if row is None:
        row = DocumentRelease(session_id=session_id, doc_id=doc_id, release_at=now, released_at=now)
        db.add(row)
    elif newly:
        row.released_at = now
    released_at = row.released_at
    await db.commit()
    if newly:
        await ctx.hub.broadcast(
            session_id, "document.released", {"doc_id": doc_id, "title": titles[doc_id]}
        )
    return {"released_at": iso(released_at)}


@router.get("/sessions/{session_id}/doc_views")
async def doc_views(session_id: uuid.UUID, db: Db) -> list[dict[str, Any]]:
    await load_session(db, session_id)
    rows = await db.execute(
        select(DocView).where(DocView.session_id == session_id).order_by(DocView.viewed_at)
    )
    return [
        {"id": str(v.id), "doc_id": v.doc_id, "viewed_at": iso(v.viewed_at)} for v in rows.scalars()
    ]


# ───────────── 관찰 ─────────────

EVIDENCE_TABLES = {
    "message": Message,
    "revision": DocumentRevision,
    "doc_view": DocView,
    "assistant_call": AssistantCall,
}


class Evidence(BaseModel):
    type: Literal["message", "revision", "doc_view", "assistant_call"]
    id: uuid.UUID


class ObservationIn(BaseModel):
    element: str
    window_start: datetime
    window_end: datetime
    metrics: dict[str, Any] = {}
    label: str | None = None
    evidence: list[Evidence] = []
    run_id: uuid.UUID | None = None


async def _check_evidence(db: AsyncSession, session_id: uuid.UUID, evidence: list[Evidence]):
    """각 근거가 이 세션의 해당 테이블 행이어야 한다."""
    for item in evidence:
        table = EVIDENCE_TABLES[item.type]
        found = await db.scalar(
            select(table.id).where(table.id == item.id, table.session_id == session_id)
        )
        if found is None:
            raise error(422, "invalid_evidence", f"{item.type} {item.id} is not in this session")


@router.post("/sessions/{session_id}/observations")
async def post_observation(session_id: uuid.UUID, body: ObservationIn, db: Db) -> dict[str, str]:
    await load_session(db, session_id)
    await _check_evidence(db, session_id, body.evidence)
    stmt = (
        insert(Observation)
        .values(
            session_id=session_id,
            element=body.element,
            window_start=body.window_start,
            window_end=body.window_end,
            metrics=body.metrics,
            label=body.label,
            evidence=[{"type": e.type, "id": str(e.id)} for e in body.evidence],
            run_id=body.run_id,
        )
        .on_conflict_do_nothing(index_elements=["session_id", "element", "window_start"])
        .returning(Observation.id)
    )
    new_id = (await db.execute(stmt)).scalar_one_or_none()
    await db.commit()
    if new_id is None:
        new_id = await db.scalar(
            select(Observation.id).where(
                Observation.session_id == session_id,
                Observation.element == body.element,
                Observation.window_start == body.window_start,
            )
        )
    return {"id": str(new_id)}


@router.get("/sessions/{session_id}/observations")
async def observations(session_id: uuid.UUID, db: Db) -> list[dict[str, Any]]:
    await load_session(db, session_id)
    rows = await db.execute(
        select(Observation)
        .where(Observation.session_id == session_id)
        .order_by(Observation.window_start, Observation.element)
    )
    return [
        {
            "id": str(o.id),
            "element": o.element,
            "window_start": iso(o.window_start),
            "window_end": iso(o.window_end),
            "metrics": o.metrics,
            "label": o.label,
            "evidence": o.evidence,
            "run_id": str(o.run_id) if o.run_id else None,
            "created_at": iso(o.created_at),
        }
        for o in rows.scalars()
    ]


# ───────────── 어시스턴트 기록 ─────────────


@router.get("/sessions/{session_id}/assistant_calls")
async def assistant_calls(session_id: uuid.UUID, db: Db) -> list[dict[str, Any]]:
    await load_session(db, session_id)
    rows = await db.execute(
        select(AssistantCall)
        .where(AssistantCall.session_id == session_id)
        .order_by(AssistantCall.created_at)
    )
    return [
        {
            "id": str(c.id),
            "request_message_id": str(c.request_message_id),
            "response_message_id": str(c.response_message_id) if c.response_message_id else None,
            "cited_doc_ids": c.cited_doc_ids,
            "created_at": iso(c.created_at),
        }
        for c in rows.scalars()
    ]


@router.get("/sessions/{session_id}/assistant_reuse")
async def assistant_reuse(session_id: uuid.UUID, db: Db) -> list[dict[str, Any]]:
    await load_session(db, session_id)
    rows = await db.execute(
        select(AssistantReuse)
        .join(AssistantCall, AssistantCall.id == AssistantReuse.call_id)
        .where(AssistantCall.session_id == session_id)
        .order_by(AssistantCall.created_at, AssistantReuse.part_no)
    )
    return [
        {"call_id": str(r.call_id), "part_no": r.part_no, "reuse": r.reuse, "ratio": r.ratio}
        for r in rows.scalars()
    ]


# ───────────── 리포트 ─────────────


def content_hash(content: dict[str, Any]) -> str:
    """정규화 JSON(키 정렬·공백 제거)의 sha256. draft와 final의 동일성 판단에 쓴다."""
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


class ReportIn(BaseModel):
    content: dict[str, Any]


@router.post("/sessions/{session_id}/report/draft")
async def save_draft(session_id: uuid.UUID, body: ReportIn, ctx: Ctx, db: Db) -> dict[str, str]:
    session = await load_session(db, session_id)
    if session.status in ("report_ready", "approving", "reviewed"):
        return {"status": "report_ready"}  # 재전달. 먼저 저장된 draft를 그대로 둔다
    if session.status != "completed":
        raise SessionError("conflict", f"cannot save draft from {session.status}")
    total = body.content.get("rubric", {}).get("auto_total") or {}
    await db.execute(
        insert(Report)
        .values(
            session_id=session_id,
            stage="draft",
            content=body.content,
            content_hash=content_hash(body.content),
            auto_met=total.get("met"),
            auto_judged=total.get("judged"),
            auto_no_record=total.get("no_record"),
        )
        .on_conflict_do_nothing(index_elements=["session_id"])
    )
    await ctx.session_service(db).mark_report_ready(session_id)  # 한 번 커밋
    return {"status": "report_ready"}


@router.post("/sessions/{session_id}/report/final")
async def save_final(session_id: uuid.UUID, body: ReportIn, ctx: Ctx, db: Db) -> dict[str, Any]:
    # 세션 행을 잠근 채 상태를 다시 읽어, 동시 재전달에도 reviewed_at이 하나로 정해진다
    session = (
        await db.execute(
            select(Session)
            .where(Session.id == session_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if session is None:
        raise SessionError("not_found", "session not found")
    report = await db.get(Report, session_id, populate_existing=True)
    if report is None or session.status not in ("approving", "reviewed"):
        raise SessionError("conflict", f"cannot save final from {session.status}")
    if content_hash(body.content) != report.content_hash:
        raise error(409, "draft_mismatch", "final content differs from the approved draft")
    if session.status == "reviewed":
        return {"status": "reviewed", "reviewed_at": iso(report.reviewed_at)}
    report.stage = "final"
    report.reviewed_at = datetime.now(UTC)
    await ctx.session_service(db).mark_reviewed(session_id)  # 한 번 커밋
    return {"status": "reviewed", "reviewed_at": iso(report.reviewed_at)}


class ReportFailedIn(BaseModel):
    error: str


@router.post("/sessions/{session_id}/report_failed")
async def report_failed(
    session_id: uuid.UUID, body: ReportFailedIn, ctx: Ctx, db: Db
) -> dict[str, str]:
    session = await ctx.session_service(db).fail(session_id, "report", body.error)
    return {"status": session.status}


# ───────────── e2e 전용 ─────────────


class TestSessionIn(BaseModel):
    elements: list[str]
    session_minutes: int = 120
    alias: str = "e2e"


@router.post("/test/sessions")
async def create_test_session(body: TestSessionIn, ctx: Ctx, db: Db) -> dict[str, str]:
    """ENABLE_TEST_API=1일 때만. 회사·채용 건·초대를 한 번에 만들어 e2e가 링크로 입장하게 한다."""
    if not ctx.settings.enable_test_api:
        raise error(404, "not_found", "not found")
    try:
        scenario, version = scenario_service.build_scenario(
            ctx.settings.scenarios_dir, body.elements, body.session_minutes
        )
    except scenario_service.InvalidElements as exc:
        raise error(400, "invalid_elements", str(exc)) from exc
    company = await db.scalar(select(Company).where(Company.name == E2E_COMPANY))
    if company is None:
        company = Company(name=E2E_COMPANY)
        db.add(company)
        await db.flush()
    position = Position(
        company_id=company.id,
        name="e2e",
        elements=body.elements,
        session_minutes=body.session_minutes,
        catalog_version=version,
        scenario=scenario,
    )
    db.add(position)
    await db.commit()
    session, _, raw = await ctx.session_service(db).create_for_invite(
        position.id, body.alias, "e2e@example.com"
    )
    return {
        "session_id": str(session.id),
        "token": raw,
        "invite_url": f"{ctx.settings.web_origins[0]}/s/{raw}",
    }
