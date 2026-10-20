"""내부 REST (/internal/*, 포트 8001, X-Internal-Token). 계약은 docs/common/contracts.md.

business-mcp·rag-mcp·report-worker가 부른다. 권한·상태 검증(담당자, 세션 상태, 문서 공개 여부)의
최종 판단은 여기서 한다. 저장은 모두 멱등 키로 중복 없이 한 번만 만든다. 세션 Lock은 잡지 않는다: 이
API는 Lock을 쥔 채 실행 중인 러너가 MCP를 거쳐 부르므로 잡으면 교착된다.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import scheduler
from app.auth import require_internal
from app.models import (
    AssistantCall,
    AssistantReuse,
    Company,
    Document,
    DocumentOpen,
    DocumentRevision,
    DocumentShare,
    DocumentVersion,
    DocView,
    Invite,
    Message,
    Observation,
    Position,
    Report,
    Session,
    SessionEvent,
    TaskEvent,
)
from app.services import board, documents, releases, views
from app.services import scenario as scenario_service
from app.services.context import AppContext, get_context
from app.services.documents import DocumentError
from app.services.messages import save_internal_message, serialize, t_min_at
from app.services.states import SessionError

router = APIRouter(prefix="/internal", dependencies=[Depends(require_internal)])

Channel = Literal["team", "dm", "manager_dm", "notice", "assistant"]
E2E_COMPANY = "e2e 테스트 회사"
OPEN_STATUSES = ("in_progress", "reporting")


def error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"error": {"code": code, "message": message}})


def doc_error(exc: DocumentError) -> HTTPException:
    return error(404 if exc.code == "not_found" else 403, exc.code, exc.message)


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
    """문서·보드·분업 쓰기는 in_progress일 때만(제출 뒤 보고 요청 카드 실행 중에도 in_progress)."""
    if session.status != "in_progress":
        raise SessionError("conflict", f"cannot {action} from {session.status}")


async def _check_event(db: AsyncSession, session_id: uuid.UUID, event_id: uuid.UUID | None) -> None:
    if event_id is None:
        return
    owner = await db.scalar(select(SessionEvent.session_id).where(SessionEvent.id == event_id))
    if owner != session_id:
        raise error(422, "invalid_event", "event_id is not an event of this session")


# ───────────── 세션 컨텍스트·메시지 ─────────────


def current_card(events: list[SessionEvent], status: str) -> str | None:
    """열린 관찰 창의 카드. 가장 최근에 실행된 요소 카드다.

    흐름 카드와 결 메시지는 창을 닫지 않는다. 마지막 창은 보고 종료(completed)까지 열려 있다.
    """
    if status not in OPEN_STATUSES:
        return None
    fired = [e for e in events if e.status in ("fired", "done") and e.element and not e.texture]
    if not fired:
        return None
    return max(fired, key=lambda e: (e.due_at, e.card_id == "collab_disagree")).card_id


@router.get("/sessions/{session_id}")
async def get_session(session_id: uuid.UUID, db: Db) -> dict[str, Any]:
    session = await load_session(db, session_id)
    position = await load_position(db, session)
    events = list(
        (await db.execute(select(SessionEvent).where(SessionEvent.session_id == session_id)))
        .scalars()
        .all()
    )
    return {
        "id": str(session.id),
        "status": session.status,
        "position": {
            "mission_id": position.mission_id,
            "elements": position.elements,
            "scenario": position.scenario,
            "catalog_version": position.catalog_version,
        },
        "division": session.division,
        "started_at": iso(session.started_at),
        "ends_at": iso(session.ends_at),
        "submitted_at": iso(session.submitted_at),
        "reported_at": iso(session.reported_at),
        "completed_at": iso(session.completed_at),
        "deadline_at": iso(session.deadline_at),
        "t_min_now": t_min_at(datetime.now(UTC), session),
        "current_card": current_card(events, session.status),
        "connection_gaps": await views.connection_gaps(db, session),
        # 워커가 카드별 발생 여부·실제 카드 시각(같은 event_id의 메시지)·문서 미제공을 판단한다
        "events": [
            {
                "id": str(e.id),
                "card_id": e.card_id,
                "element": e.element,
                "status": e.status,
                "due_at": iso(e.due_at),
                "fired_at": iso(e.fired_at),
                "document_missing": e.document_missing,
            }
            for e in sorted(events, key=lambda e: (e.due_at, e.card_id == "collab_disagree"))
        ],
    }


@router.get("/sessions/{session_id}/messages")
async def list_messages(
    session_id: uuid.UUID,
    db: Db,
    since_t_min: float | None = None,
    channel: Channel | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    session = await load_session(db, session_id)
    query = select(Message).where(Message.session_id == session_id)
    if channel is not None:
        query = query.where(Message.channel == channel)
    if since_t_min is not None and session.started_at is not None:
        since = session.started_at + timedelta(minutes=since_t_min)
        query = query.where(Message.created_at > since)
    # id까지 정렬해 offset 페이지가 겹치거나 빠지지 않게 한다(워커의 전체 수집)
    query = query.order_by(Message.created_at, Message.seq, Message.id)
    rows = await db.execute(query.offset(offset).limit(limit))
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
    await load_session(db, session_id)
    await _check_event(db, session_id, body.event_id)
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
    session_id: uuid.UUID, message_id: uuid.UUID, body: Classification, ctx: Ctx, db: Db
) -> dict[str, Any]:
    """respond 앞 분류 결과를 meta.classification에 저장한다. 팀 채널·팀장 DM의 지원자
    보고(kind=report)면 reported_at을 남겨 스케줄러가 보고 대기를 끝내게 한다(보고 요청 이후의
    메시지만)."""
    session = await load_session(db, session_id)
    message = await db.get(Message, message_id, populate_existing=True)
    if message is None or message.session_id != session_id:
        raise error(404, "not_found", "message not found")
    message.meta = {**(message.meta or {}), "classification": body.model_dump()}
    await db.commit()
    is_report = (
        body.kind == "report"
        and message.sender == "candidate"
        and message.channel in ("team", "manager_dm")
    )
    if is_report:
        await ctx.session_service(db).mark_reported(session_id, message.created_at)
    return with_meta(message, session)


# ───────────── 보드·분업 ─────────────


@router.get("/sessions/{session_id}/board")
async def get_board(session_id: uuid.UUID, db: Db) -> dict[str, Any]:
    await load_session(db, session_id)
    return {"tasks": [board.task_json(t) for t in await board.load_tasks(db, session_id)]}


class TaskIn(BaseModel):
    status: Literal["todo", "doing", "done"]
    run_id: uuid.UUID


async def _replayed(db: AsyncSession, session_id: uuid.UUID, run_id: uuid.UUID) -> bool:
    found = await db.scalar(
        select(TaskEvent.id).where(TaskEvent.session_id == session_id, TaskEvent.run_id == run_id)
    )
    return found is not None


@router.put("/sessions/{session_id}/tasks/{part_no}")
async def put_task(
    session_id: uuid.UUID, part_no: int, body: TaskIn, ctx: Ctx, db: Db
) -> dict[str, Any]:
    """동료 상태 변경. 동료 담당(colleague·both)이 아니면 403, (part_no, field, run_id) 멱등."""
    session = await load_session(db, session_id)
    if session.status != "in_progress" and not await _replayed(db, session_id, body.run_id):
        require_in_progress(session, "change task")
    try:
        task = await board.colleague_status(db, session_id, part_no, body.status, body.run_id)
    except LookupError as exc:
        raise error(404, "not_found", str(exc)) from exc
    except PermissionError as exc:
        raise error(403, "forbidden", str(exc)) from exc
    await db.commit()
    payload = board.task_json(task)
    await ctx.hub.broadcast(session_id, "task.updated", {**payload, "by": "colleague"})
    return payload


@router.get("/sessions/{session_id}/task_events")
async def task_events(session_id: uuid.UUID, db: Db) -> list[dict[str, Any]]:
    await load_session(db, session_id)
    rows = await db.execute(
        select(TaskEvent)
        .where(TaskEvent.session_id == session_id)
        .order_by(TaskEvent.created_at, TaskEvent.part_no)
    )
    return [
        {
            "id": str(e.id),
            "part_no": e.part_no,
            "by": e.by,
            "field": e.field,
            "old_value": e.old_value,
            "new_value": e.new_value,
            "created_at": iso(e.created_at),
        }
        for e in rows.scalars()
    ]


class DivisionIn(BaseModel):
    parts: dict[str, Literal["candidate", "colleague", "both"]]
    decided_by: Literal["candidate", "colleague_default"]
    run_id: uuid.UUID


@router.put("/sessions/{session_id}/division")
async def put_division(session_id: uuid.UUID, body: DivisionIn, ctx: Ctx, db: Db):
    """동료 set_division(채팅으로 정한 분업·기본안). 같은 tasks를 채우고 바뀐 행마다 task_event."""
    session = await load_session(db, session_id)
    current = session.division or {}
    if session.status != "in_progress":
        if current.get("parts") == body.parts:
            return {"division": current}
        require_in_progress(session, "divide")
    position = await load_position(db, session)
    try:
        tasks, changed = await board.set_division(
            db, session, position.scenario, body.parts, body.decided_by, body.run_id
        )
    except board.InvalidDivision as exc:
        await db.rollback()
        raise error(422, "invalid_division", str(exc)) from exc
    await db.commit()
    if changed:
        for task in tasks:
            await ctx.hub.broadcast(
                session_id, "task.updated", {**board.task_json(task), "by": "colleague"}
            )
        if not current:
            payload = {
                "parts": session.division["parts"],
                "decided_by": session.division["decided_by"],
                "t_min": t_min_at(datetime.now(UTC), session),
            }
            await ctx.hub.broadcast(session_id, "division.confirmed", payload)
    return {"division": session.division}


@router.get("/sessions/{session_id}/honesty_facts")
async def honesty_facts(session_id: uuid.UUID, db: Db) -> dict[str, Any]:
    session = await load_session(db, session_id)
    position = await load_position(db, session)
    return await documents.honesty_facts(db, session, position.scenario)


# ───────────── 문서 주고받기 ─────────────


@router.get("/sessions/{session_id}/docs")
async def docs(session_id: uuid.UUID, db: Db) -> dict[str, Any]:
    session = await load_session(db, session_id)
    return await documents.internal_docs(db, session)


@router.get("/sessions/{session_id}/docs/shared")
async def docs_shared(session_id: uuid.UUID, db: Db) -> dict[str, Any]:
    session = await load_session(db, session_id)
    return await documents.shared_docs(db, session)


@router.get("/sessions/{session_id}/document_revisions")
async def document_revisions(
    session_id: uuid.UUID, db: Db, doc_id: uuid.UUID | None = None, since_t_min: float | None = None
) -> list[dict[str, Any]]:
    session = await load_session(db, session_id)
    return await documents.revisions(db, session, doc_id, since_t_min)


class SendIn(BaseModel):
    doc_id: uuid.UUID | None = None
    part_no: int | None = None
    content: str
    channel: Literal["team", "dm"]
    run_id: uuid.UUID
    event_id: uuid.UUID | None = None
    seq: int

    @model_validator(mode="after")
    def _target(self) -> "SendIn":
        if (self.doc_id is None) == (self.part_no is None):
            raise ValueError("exactly one of doc_id or part_no")
        return self


@router.post("/sessions/{session_id}/docs/send")
async def docs_send(session_id: uuid.UUID, body: SendIn, ctx: Ctx, db: Db) -> dict[str, Any]:
    """동료 문서 쓰기·보내기. (doc_id, run_id) 멱등, 문서 카드 메시지는 (run_id, seq)."""
    session = await load_session(db, session_id)
    position = await load_position(db, session)
    await _check_event(db, session_id, body.event_id)
    if session.status != "in_progress" and not await _sent(db, session_id, body.run_id):
        require_in_progress(session, "send document")
    try:
        return await documents.colleague_send(
            db,
            ctx.hub,
            session,
            position.scenario,
            body.content,
            body.channel,
            body.run_id,
            body.seq,
            body.event_id,
            doc_id=body.doc_id,
            part_no=body.part_no,
        )
    except DocumentError as exc:
        raise doc_error(exc) from exc


async def _sent(db: AsyncSession, session_id: uuid.UUID, run_id: uuid.UUID) -> bool:
    """이 run_id로 이미 보낸 동료 문서가 있는가(제출 뒤 재전달은 기존 결과를 돌려준다)."""
    found = await db.scalar(
        select(DocumentVersion.id)
        .join(Document, Document.id == DocumentVersion.doc_id)
        .where(Document.session_id == session_id, DocumentVersion.run_id == run_id)
    )
    return found is not None


# ───────────── 회사 문서 공개·열람 ─────────────


@router.get("/sessions/{session_id}/documents")
async def company_docs(session_id: uuid.UUID, db: Db) -> dict[str, Any]:
    session = await load_session(db, session_id)
    position = await load_position(db, session)
    return {
        "catalog_version": position.catalog_version,
        "documents": await views.company_documents(db, session, position.scenario),
    }


@router.post("/sessions/{session_id}/releases/{doc_id}")
async def release_document(
    session_id: uuid.UUID, doc_id: str, ctx: Ctx, db: Db
) -> dict[str, str | None]:
    session = await load_session(db, session_id)
    position = await load_position(db, session)
    if doc_id not in {d["doc_id"] for d in position.scenario["documents"]}:
        raise error(404, "not_found", "document not found")
    released_at = await releases.release(
        db, ctx.hub, session_id, position.scenario, doc_id, datetime.now(UTC)
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

EvidenceType = Literal[
    "message", "document", "share", "open", "task_event", "doc_view", "assistant_call"
]


class Evidence(BaseModel):
    type: EvidenceType
    id: uuid.UUID


class ObservationIn(BaseModel):
    """window_start·window_end는 세션 분(t_min). 키는 (card_id, window_start)."""

    card_id: str
    element: str
    window_start: float
    window_end: float
    metrics: dict[str, Any] = {}
    label: str | None = None
    aux: dict[str, Any] = {}
    evidence: list[Evidence] = []
    facts: dict[str, Any] | None = None
    run_id: uuid.UUID | None = None


class ObservationPatch(BaseModel):
    card_id: str
    window_start: float
    metrics_patch: dict[str, Any] = Field(min_length=1)
    run_id: uuid.UUID


def _at(session: Session, minutes: float) -> datetime:
    return session.started_at + timedelta(minutes=minutes)


async def _evidence_in_session(db: AsyncSession, session_id: uuid.UUID, item: Evidence) -> bool:
    """근거 id가 이 세션의 해당 테이블 행인가(rubric.md 근거 타입 표)."""
    direct = {
        "message": Message,
        "doc_view": DocView,
        "assistant_call": AssistantCall,
        "task_event": TaskEvent,
    }
    if item.type in direct:
        table = direct[item.type]
        found = await db.scalar(
            select(table.id).where(table.id == item.id, table.session_id == session_id)
        )
        return found is not None
    via_doc = {"document": DocumentRevision, "share": DocumentShare, "open": DocumentOpen}[
        item.type
    ]
    found = await db.scalar(
        select(via_doc.id)
        .join(Document, Document.id == via_doc.doc_id)
        .where(via_doc.id == item.id, Document.session_id == session_id)
    )
    return found is not None


def observation_json(o: Observation, session: Session) -> dict[str, Any]:
    """계약 픽스처 형태. facts는 정직 카드 행에만 싣는다."""
    row = {
        "id": str(o.id),
        "card_id": o.card_id,
        "element": o.element,
        "window_start": t_min_at(o.window_start, session),
        "window_end": t_min_at(o.window_end, session),
        "metrics": o.metrics,
        "label": o.label,
        "aux": o.aux,
        "evidence": o.evidence,
        "run_id": str(o.run_id) if o.run_id else None,
        "created_at": iso(o.created_at),
    }
    if o.facts is not None:
        row["facts"] = o.facts
    return row


async def _find_observation(
    db: AsyncSession, session: Session, card_id: str, window_start: float
) -> Observation | None:
    return await db.scalar(
        select(Observation)
        .where(
            Observation.session_id == session.id,
            Observation.card_id == card_id,
            Observation.window_start == _at(session, window_start),
        )
        .execution_options(populate_existing=True)
    )


@router.post("/sessions/{session_id}/observations")
async def post_observation(session_id: uuid.UUID, body: ObservationIn, db: Db) -> dict[str, str]:
    session = await load_session(db, session_id)
    for item in body.evidence:
        if not await _evidence_in_session(db, session_id, item):
            raise error(422, "invalid_evidence", f"{item.type} {item.id} is not in this session")
    stmt = (
        insert(Observation)
        .values(
            session_id=session_id,
            card_id=body.card_id,
            element=body.element,
            window_start=_at(session, body.window_start),
            window_end=_at(session, body.window_end),
            metrics=body.metrics,
            label=body.label,
            aux=body.aux,
            evidence=[{"type": e.type, "id": str(e.id)} for e in body.evidence],
            facts=body.facts,
            run_id=body.run_id,
        )
        .on_conflict_do_nothing(index_elements=["session_id", "card_id", "window_start"])
        .returning(Observation.id)
    )
    new_id = (await db.execute(stmt)).scalar_one_or_none()
    await db.commit()
    if new_id is None:
        new_id = (await _find_observation(db, session, body.card_id, body.window_start)).id
    return {"id": str(new_id)}


@router.patch("/sessions/{session_id}/observations")
async def patch_observation(
    session_id: uuid.UUID, body: ObservationPatch, db: Db
) -> dict[str, Any]:
    """종료 finalize의 지표 갱신(collab_help promise_kept).

    지정한 지표만 바꾸고 같은 run_id는 멱등이다.
    """
    session = await load_session(db, session_id)
    row = await _find_observation(db, session, body.card_id, body.window_start)
    if row is None:
        raise error(404, "not_found", "observation not found")
    if row.updated_run_id != body.run_id:
        row.metrics = {**row.metrics, **body.metrics_patch}
        row.updated_run_id = body.run_id
        row.updated_at = datetime.now(UTC)
        await db.commit()
    return observation_json(row, session)


@router.get("/sessions/{session_id}/observations")
async def observations(session_id: uuid.UUID, db: Db) -> list[dict[str, Any]]:
    session = await load_session(db, session_id)
    rows = await db.execute(
        select(Observation)
        .where(Observation.session_id == session_id)
        .order_by(Observation.window_start, Observation.card_id)
    )
    return [observation_json(o, session) for o in rows.scalars()]


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
    """제출 후에만 값이 있다. 비율은 내부 계산값이라 싣지 않고, 대신 호출마다 비율이 큰 행부터
    준다(워커는 호출의 첫 applied 행을 반영 파트로 쓴다)."""
    await load_session(db, session_id)
    rows = await db.execute(
        select(AssistantReuse)
        .join(AssistantCall, AssistantCall.id == AssistantReuse.call_id)
        .where(AssistantCall.session_id == session_id)
        .order_by(
            AssistantCall.created_at,
            AssistantCall.id,
            AssistantReuse.ratio.desc(),
            AssistantReuse.part_no.nulls_last(),
        )
    )
    return [
        {
            "call_id": str(r.call_id),
            "doc_id": str(r.doc_id),
            "part_no": r.part_no if r.part_no is not None else "final",
            "applied": r.applied,
        }
        for r in rows.scalars()
    ]


# ───────────── 종료·리포트 ─────────────


@router.post("/sessions/{session_id}/complete")
async def complete(session_id: uuid.UUID, ctx: Ctx, db: Db) -> dict[str, Any]:
    """보고 종료. 그래프가 보고 메시지 저장 뒤 부른다(러너가 세션 Lock을 쥔 채라 여기서 종료를
    끝까지 돌리면 교착된다). 그래서 completed_at만 확정하고 나머지 종료(종료 실행·발행)는
    백그라운드로 띄운다. 응답의 completed_at은 최종값이다."""
    session = await load_session(db, session_id)
    if session.status in ("completed", "report_ready", "approving", "reviewed"):
        return {"status": "completed", "completed_at": iso(session.completed_at)}
    if session.status != "reporting":
        raise SessionError("conflict", f"cannot complete from {session.status}")
    if session.completed_at is None:
        session.completed_at = session.reported_at or datetime.now(UTC)
        await db.commit()
    reason = scheduler.ended_reason(session)
    scheduler.spawn(("end", session_id), lambda: scheduler.complete(ctx, session_id, reason))
    return {"status": "completed", "completed_at": iso(session.completed_at)}


def content_hash(content: dict[str, Any]) -> str:
    """정규화 JSON(키 정렬·공백 제거)의 sha256. draft와 final의 동일성 판단에 쓴다."""
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


class ReportIn(BaseModel):
    content: dict[str, Any]
    # 워커 LLM 사용량(reports.usage). 해시는 content에만 적용한다
    usage: dict[str, Any] | None = None


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
            usage=body.usage or {},
            auto_met=total.get("met"),
            auto_unmet=total.get("unmet"),
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
    mission_id: str = scenario_service.DEFAULT_MISSION
    alias: str = "e2e"


@router.post("/test/sessions")
async def create_test_session(body: TestSessionIn, ctx: Ctx, db: Db) -> dict[str, str]:
    """ENABLE_TEST_API=1일 때만. 회사·채용 건·초대를 한 번에 만들어 e2e가 링크로 입장하게 한다."""
    if not ctx.settings.enable_test_api:
        raise error(404, "not_found", "not found")
    try:
        scenario, version = scenario_service.build_scenario(
            ctx.settings.scenarios_dir, body.elements, body.session_minutes, body.mission_id
        )
    except scenario_service.InvalidMission as exc:
        raise error(422, "invalid_mission", str(exc)) from exc
    except scenario_service.InvalidElements as exc:
        raise error(422, "invalid_elements", str(exc)) from exc
    company = await db.scalar(select(Company).where(Company.name == E2E_COMPANY))
    if company is None:
        company = Company(name=E2E_COMPANY)
        db.add(company)
        await db.flush()
    position = Position(
        company_id=company.id,
        name="e2e",
        mission_id=body.mission_id,
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
