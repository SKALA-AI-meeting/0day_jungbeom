"""지원자 REST.

/s/{token}: 입장·동의·재입장·시작. /sessions/{id}: 상태·내 문서·받은 문서·최종본·보드·회사
문서·어시스턴트·제출·디브리핑.

계약은 docs/common/contracts.md의 "지원자 REST"와 State 스냅샷이 정본이다. 상태 전이는
SessionService만 하고, 이 라우터는 읽기와 지원자 쓰기(문서·보드·열람 기록)를 한다. 지원자 쓰기는
세션 Lock 안에서 해 제출 처리(같은 Lock)와 직렬화한다. 그래서 제출이 시작된 뒤에는 저장되지 않고 409
session_ending이다. 내부 라우터는 Lock을 잡지 않는다(실행 중인 러너가 부르므로 잡으면 교착된다).
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app import scheduler
from app.agent.runner import Stimulus
from app.auth import (
    Bearer,
    Principal,
    debrief_deadline,
    debrief_token,
    decode_token,
    hash_invite_token,
    require_candidate,
    require_debrief_reader,
    session_token,
)
from app.masking import mask
from app.models import (
    Admin,
    AgentRun,
    AssistantCall,
    Company,
    DebriefSurvey,
    DocumentRelease,
    DocView,
    Invite,
    Message,
    Position,
    Session,
    SessionEvent,
)
from app.services import board, documents, views
from app.services.context import AppContext, get_context
from app.services.documents import DocumentError
from app.services.messages import serialize, t_min_at
from app.services.runs import start_run
from app.services.states import ENDED_STATUSES, SessionError

router = APIRouter()

ASSISTANT_LIMIT = 60
RETENTION_DAYS = 90
SURVEY_QUESTIONS = [
    {"q": "natural", "text": "대화와 상황이 실제 업무처럼 자연스러웠나요?"},
    {"q": "fair", "text": "이 방식이 공정하다고 느꼈나요?"},
]
CHANNELS = {
    "team": {"members": ["manager", "colleague", "candidate"]},
    "dm": {"members": ["colleague", "candidate"]},
    "manager_dm": {"members": ["manager", "candidate"]},
    "notice": {"members": ["candidate"]},
}
# 디브리핑·종료 안내를 보여 주는 상태(보고 종료 이후와 failed)
DEBRIEF_STATUSES = ENDED_STATUSES | {"failed"}


async def get_db(ctx: Annotated[AppContext, Depends(get_context)]) -> AsyncIterator[AsyncSession]:
    async with ctx.session_factory() as db:
        yield db


Ctx = Annotated[AppContext, Depends(get_context)]
Db = Annotated[AsyncSession, Depends(get_db)]
Candidate = Annotated[Principal, Depends(require_candidate)]
DebriefReader = Annotated[Principal, Depends(require_debrief_reader)]


def _error(code: int, error_code: str, message: str) -> HTTPException:
    return HTTPException(code, detail={"error": {"code": error_code, "message": message}})


def _doc_error(exc: DocumentError) -> HTTPException:
    return _error(404 if exc.code == "not_found" else 403, exc.code, exc.message)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def _by_token(db: AsyncSession, token: str) -> tuple[Invite, Session, Position]:
    invite = (
        await db.execute(select(Invite).where(Invite.token_hash == hash_invite_token(token)))
    ).scalar_one_or_none()
    if invite is None:
        raise SessionError("not_found", "invite not found")
    session = (await db.execute(select(Session).where(Session.invite_id == invite.id))).scalar_one()
    return invite, session, await db.get(Position, invite.position_id)


async def _load(db: AsyncSession, session_id: uuid.UUID) -> tuple[Session, Position]:
    row = (
        await db.execute(
            select(Session, Position)
            .join(Invite, Invite.id == Session.invite_id)
            .join(Position, Position.id == Invite.position_id)
            .where(Session.id == session_id)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if row is None:
        raise SessionError("not_found", "session not found")
    return row[0], row[1]


async def _writable(db: AsyncSession, session_id: uuid.UUID) -> tuple[Session, Position]:
    """제출(또는 만료 처리) 시작 뒤에는 session_ending, 진행 중이 아니면 conflict."""
    session, position = await _load(db, session_id)
    if session.submitted_at is not None or session.status in DEBRIEF_STATUSES - {"failed"}:
        raise SessionError("session_ending", "session already submitted")
    if session.status != "in_progress":
        raise SessionError("conflict", f"session is {session.status}")
    return session, position


def _ended_at(session: Session) -> datetime:
    """디브리핑 기한의 기준: 보고 종료(completed_at), 진행 중 실패면 fail()이 당긴 ends_at."""
    return session.completed_at or session.ends_at


def _ensure_debrief_open(session: Session) -> datetime:
    """종료 시각 + 7일. 지나면 410 expired. 기한을 돌려줘 debrief_token의 exp로 쓴다."""
    deadline = debrief_deadline(_ended_at(session))
    if datetime.now(UTC) >= deadline:
        raise SessionError("expired", "debrief period is over")
    return deadline


def _duration(minutes: int) -> str:
    return f"{minutes // 60}시간" if minutes % 60 == 0 else f"{minutes}분"


async def _contact_email(db: AsyncSession, position: Position) -> str:
    """문의 창구: 채용 건 회사의 담당자 이메일(MVP는 회사당 계정 1개)."""
    email = await db.scalar(
        select(Admin.email)
        .where(Admin.company_id == position.company_id)
        .order_by(Admin.created_at)
    )
    return email or ""


# ---- /s/{token} -------------------------------------------------------------------------


@router.get("/s/{token}")
async def entry(token: str, db: Db) -> dict[str, Any]:
    invite, session, position = await _by_token(db, token)
    if session.status == "cancelled":
        raise SessionError("cancelled", "invite cancelled")
    # 초대 72시간 만료는 시작 전에만 적용한다
    if session.status == "invited" and invite.expires_at <= datetime.now(UTC):
        raise SessionError("expired", "invite expired")
    scenario = position.scenario
    company = await db.get(Company, position.company_id)
    contact = await _contact_email(db, position)
    minutes = scenario["session_minutes"]
    body: dict[str, Any] = {
        "company_name": company.name,
        "duration_minutes": minutes,
        "status": session.status,
        "elements_names": [e["name"] for e in scenario["element_meta"]],
        "entry_notice": (
            f"{_duration(minutes)} 연속 진행되며 중간 휴식이 없습니다. PC를 권장합니다. "
            f"업무는 가상 회사 {scenario['company']['name']}에서 진행되고, "
            f"지원자는 이번 건의 {scenario['candidate_title']}으로 "
            "파트를 나누고 최종본을 모아 보고합니다. "
            "연결이 끊겨도 시간은 흐릅니다. "
            "외부 도구 사용은 막지 않지만 안의 어시스턴트만 기록됩니다. "
            f"문의: {contact}"
        ),
        "contact_email": contact,
    }
    if session.status in DEBRIEF_STATUSES:
        body["debrief_token"] = debrief_token(session.id, _ensure_debrief_open(session))
    if session.status == "failed":
        body["failed_stage"] = session.failed_stage
    return body


@router.post("/s/{token}/consent")
async def consent(token: str, db: Db, ctx: Ctx) -> dict[str, str]:
    """시작 전까지 몇 번이든 허용하고 매번 새 세션 JWT를 준다."""
    _, session, position = await _by_token(db, token)
    session = await ctx.session_service(db).consent(session.id)
    return {"session_token": session_token(session.id, position.scenario["session_minutes"])}


@router.post("/s/{token}/resume")
async def resume(token: str, db: Db) -> dict[str, str]:
    """진행 중·보고 대기 세션에 링크만으로 다시 들어온다(저장된 JWT가 없어도 됨)."""
    _, session, position = await _by_token(db, token)
    if session.status not in ("in_progress", "reporting"):
        raise SessionError("conflict", f"cannot resume from {session.status}")
    return {"session_token": session_token(session.id, position.scenario["session_minutes"])}


@router.post("/s/{token}/start")
async def start(token: str, creds: Bearer, db: Db, ctx: Ctx) -> dict[str, str | None]:
    _, session, _ = await _by_token(db, token)
    if creds is None:
        raise _error(status.HTTP_401_UNAUTHORIZED, "unauthorized", "missing bearer token")
    principal = decode_token(creds.credentials)
    if principal.role != "candidate" or principal.subject != session.id:
        raise _error(status.HTTP_403_FORBIDDEN, "forbidden", "other session")
    session = await ctx.session_service(db).start(session.id)
    return {
        "session_id": str(session.id),
        "started_at": _iso(session.started_at),
        "ends_at": _iso(session.ends_at),
    }


# ---- /sessions/{id}: 상태 ----------------------------------------------------------------


@router.get("/sessions/{session_id}/state")
async def state(session_id: uuid.UUID, _: Candidate, db: Db) -> dict[str, Any]:
    """재접속 복구용 전체 스냅샷. WS는 이후 증분만 보낸다."""
    session, position = await _load(db, session_id)
    invite = await db.get(Invite, session.invite_id)
    scenario = position.scenario
    messages = (
        await db.execute(
            select(Message)
            .where(Message.session_id == session_id, Message.channel != "assistant")
            .order_by(Message.created_at, Message.seq)
        )
    ).scalars()
    request, response = aliased(Message), aliased(Message)
    calls = (
        await db.execute(
            select(AssistantCall, request.content, response.content)
            .join(request, request.id == AssistantCall.request_message_id)
            .outerjoin(response, response.id == AssistantCall.response_message_id)
            .where(AssistantCall.session_id == session_id)
            .order_by(AssistantCall.created_at)
        )
    ).all()
    runs = (
        await db.execute(
            select(AgentRun)
            .where(AgentRun.session_id == session_id, AgentRun.status == "started")
            .order_by(AgentRun.started_at)
        )
    ).scalars()
    remaining = None
    if session.ends_at is not None:
        remaining = max(0, int((session.ends_at - datetime.now(UTC)).total_seconds()))
    docs = await documents.my_documents(db, session)
    final = docs["final"]
    tasks = await board.load_tasks(db, session_id)
    manager = scenario["company"]["manager"]
    return {
        "session": {
            "id": str(session.id),
            "alias": invite.alias,
            "status": session.status,
            "started_at": _iso(session.started_at),
            "ends_at": _iso(session.ends_at),
            "remaining_seconds": remaining,
            "deadline_at": _iso(session.deadline_at),
            "completed_at": _iso(session.completed_at),
        },
        "division": session.division,
        "messages": [serialize(m, session) for m in messages],
        "my_documents": docs["documents"],
        "received": docs["received"],
        "final": {
            "sections": final["sections"],
            "template": {"length": scenario["final_template"]["length"]},
        },
        "tasks": [board.task_json(t) for t in tasks],
        "documents": await views.company_documents(db, session, scenario),
        "assistant": [
            {
                "call_id": str(call.id),
                "request": req,
                "response": resp,
                "cited_docs": list(call.cited_doc_ids),
                "t_min": t_min_at(call.created_at, session),
            }
            for call, req, resp in calls
        ],
        "active_runs": [await _run_view(db, run, scenario) for run in runs],
        "connection_gaps": await views.connection_gaps(db, session),
        "channels": CHANNELS,
        "persona": {
            "manager": manager.get("display") or manager["name"],
            "colleague": scenario["company"]["colleague"]["name"],
            "candidate_role": scenario["candidate_title"],
        },
    }


async def _run_view(db: AsyncSession, run: AgentRun, scenario: dict[str, Any]) -> dict[str, str]:
    """agent_runs에는 actor·node가 없어 자극 종류로 정한다. 카드 실행은 카드 actor."""
    node = {"message": "respond", "event": "inject", "division": "division"}.get(
        run.stimulus, "end"
    )
    actor = "colleague"
    if run.stimulus == "event" and run.ref_ids:
        card_id = await db.scalar(
            select(SessionEvent.card_id).where(SessionEvent.id == run.ref_ids[0])
        )
        card = next((c for c in scenario["cards"] if c["card_id"] == card_id), {})
        actor = "manager" if card.get("actor") == "manager" else "colleague"
    return {"run_id": str(run.run_id), "actor": actor, "node": node}


# ---- 내 문서·받은 문서·최종본 -----------------------------------------------------------


class DocumentBody(BaseModel):
    content: str


class SectionPatch(BaseModel):
    part_no: int
    content: str


class FinalBody(BaseModel):
    sections: list[SectionPatch]


class ShareBody(BaseModel):
    channel: Literal["team", "dm"]
    note: str = ""  # 문서 카드에 함께 보내는 지원자 한마디(없으면 빈 본문)


class OpenBody(BaseModel):
    version: int


class ImportBody(BaseModel):
    source_doc_id: uuid.UUID
    version: int | None  # null이면 보내지 않은 내 문서의 현재 저장본


@router.get("/sessions/{session_id}/my-documents")
async def my_documents(session_id: uuid.UUID, _: Candidate, db: Db) -> dict[str, Any]:
    session, _ = await _load(db, session_id)
    return await documents.my_documents(db, session)


@router.get("/sessions/{session_id}/my-documents/final")
async def my_final(session_id: uuid.UUID, _: Candidate, db: Db) -> dict[str, Any]:
    session, _ = await _load(db, session_id)
    return (await documents.my_documents(db, session))["final"]


@router.get("/sessions/{session_id}/my-documents/{part_no}")
async def my_document(session_id: uuid.UUID, part_no: int, _: Candidate, db: Db) -> dict[str, Any]:
    session, _ = await _load(db, session_id)
    docs = (await documents.my_documents(db, session))["documents"]
    found = next((d for d in docs if d["part_no"] == part_no), None)
    if found is None:
        raise SessionError("not_found", f"part {part_no} not found")
    return found


@router.put("/sessions/{session_id}/my-documents/final")
async def save_final(
    session_id: uuid.UUID, body: FinalBody, _: Candidate, db: Db, ctx: Ctx
) -> dict[str, Any]:
    """최종본 직접 편집. 바뀐 섹션만 edited=true(출처는 유지)."""
    async with ctx.locks(session_id):
        await _writable(db, session_id)
        try:
            result = await documents.save_final(
                db, session_id, [s.model_dump() for s in body.sections]
            )
        except DocumentError as exc:
            raise _doc_error(exc) from exc
        await db.commit()
        return result


@router.put("/sessions/{session_id}/my-documents/{part_no}")
async def save_part(
    session_id: uuid.UUID, part_no: int, body: DocumentBody, _: Candidate, db: Db, ctx: Ctx
) -> dict[str, Any]:
    """디바운스 저장(version을 만들지 않음). 저장마다 document_revisions에 스냅샷을 남긴다."""
    async with ctx.locks(session_id):
        await _writable(db, session_id)
        try:
            result = await documents.save_part(db, session_id, part_no, body.content)
        except DocumentError as exc:
            raise _doc_error(exc) from exc
        await db.commit()
        return result


@router.post("/sessions/{session_id}/my-documents/{part_no}/share")
async def share(
    session_id: uuid.UUID, part_no: int, body: ShareBody, _: Candidate, db: Db, ctx: Ctx
) -> dict[str, Any]:
    """현재 content로 새 version을 고정하고 채널에 문서 카드 메시지를 올린다."""
    async with ctx.locks(session_id):
        session, _ = await _writable(db, session_id)
        try:
            return await documents.share_part(
                db, ctx.hub, session, part_no, body.channel, body.note
            )
        except DocumentError as exc:
            raise _doc_error(exc) from exc


@router.post("/sessions/{session_id}/documents/{doc_id}/open")
async def open_document(
    session_id: uuid.UUID, doc_id: uuid.UUID, body: OpenBody, _: Candidate, db: Db, ctx: Ctx
) -> dict[str, Any]:
    """동료가 보낸 버전만 연다(아니면 404). 열람은 document_opens에 남긴다."""
    async with ctx.locks(session_id):
        session, _ = await _writable(db, session_id)
        try:
            result = await documents.open_received(db, session, doc_id, body.version)
        except DocumentError as exc:
            raise _doc_error(exc) from exc
        await db.commit()
        return result


@router.put("/sessions/{session_id}/final/sections/{part_no}/import")
async def import_section(
    session_id: uuid.UUID, part_no: int, body: ImportBody, _: Candidate, db: Db, ctx: Ctx
) -> dict[str, Any]:
    """그 버전으로 섹션을 덮어쓰고 출처를 남긴다(edited=false)."""
    async with ctx.locks(session_id):
        session, _ = await _writable(db, session_id)
        try:
            section = await documents.import_section(
                db, session, part_no, body.source_doc_id, body.version
            )
        except DocumentError as exc:
            raise _doc_error(exc) from exc
        await db.commit()
        return section


# ---- 보드 -------------------------------------------------------------------------------


class TaskBody(BaseModel):
    assignee: Literal["candidate", "colleague", "both"] | None = None
    status: Literal["todo", "doing", "done"] | None = None
    order: int | None = Field(default=None, ge=1)
    due_min: int | None = Field(default=None, ge=0)


@router.put("/sessions/{session_id}/tasks/{part_no}")
async def put_task(
    session_id: uuid.UUID, part_no: int, body: TaskBody, _: Candidate, db: Db, ctx: Ctx
) -> dict[str, Any]:
    """모든 카드의 담당·상태·순서·언제까지를 바꾼다. 5행이 다 차고 division_min을 만족하는 순간
    분업을 확정하고(division.confirmed) 동료에게 division 자극을 보낸다. 위반이면 422, 저장 안
    함."""
    changes = body.model_dump(exclude_unset=True)
    async with ctx.locks(session_id):
        session, position = await _writable(db, session_id)
        try:
            change = await board.candidate_update(db, session, position.scenario, part_no, changes)
        except LookupError as exc:
            raise SessionError("not_found", str(exc)) from exc
        except board.InvalidDivision as exc:
            await db.rollback()
            raise _error(422, "invalid_division", str(exc)) from exc
        run_id = None
        if change.division_changed:
            run_id = uuid.uuid4()
            stimulus = Stimulus("division", task_event_ids=tuple(change.event_ids))
            await start_run(db, session_id, stimulus, run_id)
        await db.commit()
        task = board.task_json(change.task)
    await ctx.hub.broadcast(session_id, "task.updated", {**task, "by": "candidate"})
    if change.confirmed:
        payload = {
            "parts": session.division["parts"],
            "decided_by": session.division["decided_by"],
            "t_min": t_min_at(datetime.now(UTC), session),
        }
        await ctx.hub.broadcast(session_id, "division.confirmed", payload)
    if run_id is not None:
        job = lambda: scheduler.run_stimulus(ctx, session_id, stimulus, run_id)  # noqa: E731
        scheduler.spawn(run_id, job)
    return task


# ---- 회사 문서 ----------------------------------------------------------------------------


@router.get("/sessions/{session_id}/documents")
async def list_documents(session_id: uuid.UUID, _: Candidate, db: Db) -> list[dict[str, Any]]:
    session, position = await _load(db, session_id)
    return await views.company_documents(db, session, position.scenario)


@router.get("/sessions/{session_id}/documents/{doc_id}")
async def get_document(session_id: uuid.UUID, doc_id: str, _: Candidate, db: Db) -> dict[str, Any]:
    """공개된 회사 문서만 본문을 준다. 열람은 doc_views에 남긴다(관찰 입력)."""
    _, position = await _load(db, session_id)
    doc = next((d for d in position.scenario["documents"] if d["doc_id"] == doc_id), None)
    if doc is None:
        raise SessionError("not_found", f"document {doc_id} not found")
    release = await db.get(DocumentRelease, (session_id, doc_id))
    if release is None or release.released_at is None:
        raise _error(status.HTTP_423_LOCKED, "not_released", f"{doc_id} is not released yet")
    db.add(DocView(session_id=session_id, doc_id=doc_id))
    await db.commit()
    return {"doc_id": doc_id, "title": doc["title"], "content": doc["content"]}


# ---- 어시스턴트 ---------------------------------------------------------------------------


class AssistantBody(BaseModel):
    prompt: str = Field(min_length=1)


@router.post("/sessions/{session_id}/assistant")
async def assistant(
    session_id: uuid.UUID, body: AssistantBody, _: Candidate, db: Db, ctx: Ctx
) -> dict[str, Any]:
    """어시스턴트 훅(ctx.assistant). 요청·응답을 assistant 채널 메시지와 assistant_calls로 남긴다.

    세션 그래프와 별개 thread라 세션 Lock을 잡지 않는다. 60회를 넘으면 429 assistant_limit.
    한도 확인과 assistant_calls INSERT는 세션 행 잠금(FOR UPDATE)으로 직렬화해 동시 요청이 한도를
    넘지 못하게 한다(커밋까지 잠금 유지, 프로세스가 여러 개여도 유효). 요청 본문은 저장·그래프
    입력 모두 마스킹한 값이다.
    """
    await db.execute(select(Session.id).where(Session.id == session_id).with_for_update())
    await _writable(db, session_id)
    used = await db.scalar(
        select(func.count())
        .select_from(AssistantCall)
        .where(AssistantCall.session_id == session_id)
    )
    if used >= ASSISTANT_LIMIT:
        raise _error(429, "assistant_limit", f"assistant limit {ASSISTANT_LIMIT} reached")
    prompt = mask(body.prompt)
    request = Message(
        session_id=session_id, channel="assistant", sender="candidate", content=prompt
    )
    db.add(request)
    await db.flush()
    call = AssistantCall(session_id=session_id, request_message_id=request.id)
    db.add(call)
    await db.commit()
    result = await ctx.assistant.answer(session_id, prompt, call.id)
    response = Message(
        session_id=session_id,
        channel="assistant",
        sender="assistant",
        content=result.content,
        meta={"usage": result.usage} if result.usage else {},
    )
    db.add(response)
    await db.flush()
    call.response_message_id = response.id
    call.cited_doc_ids = list(result.cited_docs)
    await db.commit()
    return {
        "call_id": str(call.id),
        "message_id": str(response.id),
        "content": result.content,
        "cited_docs": list(result.cited_docs),
    }


# ---- 제출 --------------------------------------------------------------------------------


@router.post("/sessions/{session_id}/submit")
async def submit(session_id: uuid.UUID, _: Candidate, db: Db, ctx: Ctx) -> dict[str, Any]:
    """멱등. 보고 요청 카드가 아직이면 바로 실행하고 reporting(deadline_at) 또는 completed를
    돌려준다.
    """
    session, _ = await _load(db, session_id)
    if session.status == "in_progress":
        session = await ctx.session_service(db).submit(session_id, "submitted")
    body: dict[str, Any] = {"status": session.status}
    if session.status == "reporting":
        body["deadline_at"] = _iso(session.deadline_at)
    return body


# ---- 디브리핑 ----------------------------------------------------------------------------


@router.get("/sessions/{session_id}/debrief")
async def debrief(session_id: uuid.UUID, _: DebriefReader, db: Db) -> dict[str, Any]:
    """실제 실행된(done) 요소 카드만 설명한다. 세션 실패면 연출을 드러내지 않고 중단 안내만."""
    session, position = await _load(db, session_id)
    if session.status not in DEBRIEF_STATUSES:
        raise SessionError("conflict", f"session is {session.status}")
    deadline = _ensure_debrief_open(session)
    texts = position.scenario["debrief_texts"]  # 문안은 미션 카탈로그가 정본
    if session.failed_stage == "session":
        return {
            "events": [],
            "persona_note": None,
            "scoring_notice": texts["failed_notice"],
            "final": None,
            "final_view_until": None,
            "survey": {"submitted": False, "questions": []},
            "failed_stage": "session",
        }
    scenario = position.scenario
    cards = {c["card_id"]: c for c in scenario["cards"] if c.get("element")}
    done = (
        await db.execute(
            select(SessionEvent.card_id)
            .where(
                SessionEvent.session_id == session_id,
                SessionEvent.element.is_not(None),
                SessionEvent.status == "done",
            )
            .order_by(SessionEvent.due_at, SessionEvent.card_id)
        )
    ).scalars()
    final = await documents.final_view(db, session_id)
    surveyed = await db.get(DebriefSurvey, session_id)
    colleague = scenario["company"]["colleague"]["name"]
    manager = (
        scenario["company"]["manager"].get("display") or scenario["company"]["manager"]["name"]
    )
    body: dict[str, Any] = {
        "events": [
            {
                "card_id": card_id,
                "element": cards[card_id]["element"],
                "name": cards[card_id]["name"],
                "description": cards[card_id]["debrief"],
                "rubric_items": [item["text"] for item in cards[card_id]["rubric"]],
            }
            for card_id in done
            if card_id in cards
        ],
        "persona_note": texts["persona_note"].format(
            colleague=colleague,
            manager=manager,
            company=scenario["company"]["name"],
            values=", ".join(texts["values_short"]),
        ),
        "scoring_notice": texts["scoring_notice"],
        "connection_gaps": await views.connection_gaps(db, session),
        "retention_notice": texts["retention_notice"].format(days=RETENTION_DAYS),
        "contact_email": await _contact_email(db, position),
        "final": (
            {
                "sections": [
                    {"part_no": s["part_no"], "title": s["title"], "content": s["content"]}
                    for s in final.sections
                ]
            }
            if final
            else None
        ),
        "final_view_until": _iso(deadline),
        "survey": {"submitted": surveyed is not None, "questions": SURVEY_QUESTIONS},
    }
    if session.status == "failed":
        body["failed_stage"] = session.failed_stage
    return body


class SurveyAnswer(BaseModel):
    q: Literal["natural", "fair"]
    value: int = Field(ge=1, le=5)


class SurveyBody(BaseModel):
    answers: list[SurveyAnswer]


@router.post("/sessions/{session_id}/debrief/survey")
async def survey(
    session_id: uuid.UUID, body: SurveyBody, _: DebriefReader, db: Db
) -> dict[str, bool]:
    """종료 설문 2문항. 한 번만 저장하고 재요청은 기존 값을 둔다(멱등)."""
    session, _ = await _load(db, session_id)
    if session.status not in DEBRIEF_STATUSES or session.failed_stage == "session":
        raise SessionError("conflict", f"session is {session.status}")
    _ensure_debrief_open(session)
    if await db.get(DebriefSurvey, session_id) is None:
        db.add(DebriefSurvey(session_id=session_id, answers=[a.model_dump() for a in body.answers]))
        await db.commit()
    return {"submitted": True}
