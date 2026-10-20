"""지원자 REST.

/s/{token}: 입장·동의·재입장·시작. /sessions/{id}: 상태·문서·작업·열람·제출·디브리핑.

계약은 docs/common/contracts.md의 "지원자 REST"와 State 스냅샷이 정본이다.
상태 전이는 SessionService만 하고, 이 라우터는 읽기와 지원자 문서 저장·열람 기록만 직접 쓴다.
complete()는 세션 Lock을 잡으므로 Lock 밖에서 부른다(진행 중 실행이 끝난 뒤 종료가 돈다).
"""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

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
from app.models import (
    AgentRun,
    AssistantCall,
    Company,
    DocumentRelease,
    DocumentRevision,
    DocumentState,
    DocView,
    Invite,
    Message,
    Position,
    Session,
    SessionEvent,
    Task,
)
from app.services.context import AppContext, get_context
from app.services.messages import serialize
from app.services.session import ORDER, SessionError

router = APIRouter()

# 디브리핑·종료 안내를 보여 주는 상태(completed 이후와 failed)
ENDED = {*ORDER[ORDER.index("completed") :], "failed"}
CANDIDATE_TASKS = {"candidate", "both"}


async def get_db(ctx: Annotated[AppContext, Depends(get_context)]) -> AsyncIterator[AsyncSession]:
    async with ctx.session_factory() as db:
        yield db


Ctx = Annotated[AppContext, Depends(get_context)]
Db = Annotated[AsyncSession, Depends(get_db)]
Candidate = Annotated[Principal, Depends(require_candidate)]
DebriefReader = Annotated[Principal, Depends(require_debrief_reader)]


class DocumentBody(BaseModel):
    content: str


class TaskBody(BaseModel):
    status: Literal["todo", "doing", "done"]


def _error(code: int, error_code: str, message: str) -> HTTPException:
    return HTTPException(code, detail={"error": {"code": error_code, "message": message}})


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _t_min(value: datetime, session: Session) -> float | None:
    if session.started_at is None:
        return None
    return round((value - session.started_at).total_seconds() / 60, 2)


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
        )
    ).one_or_none()
    if row is None:
        raise SessionError("not_found", "session not found")
    return row[0], row[1]


def _ensure_writable(session: Session) -> None:
    """제출(또는 만료 처리) 시작 뒤에는 session_ending, 진행 중이 아니면 conflict."""
    if session.submitted_at is not None:
        raise SessionError("session_ending", "session already submitted")
    if session.status != "in_progress":
        raise SessionError("conflict", f"session is {session.status}")


def _ensure_debrief_open(session: Session) -> datetime:
    """종료 시각(제출, 없으면 ends_at — 진행 중 실패는 fail()이 실패 시각으로 당김) + 7일.

    지나면 410 expired. 기한을 돌려줘 debrief_token의 exp로 쓴다.
    """
    deadline = debrief_deadline(session.submitted_at or session.ends_at)
    if datetime.now(UTC) >= deadline:
        raise SessionError("expired", "debrief period is over")
    return deadline


def _duration(minutes: int) -> str:
    return f"{minutes // 60}시간" if minutes % 60 == 0 else f"{minutes}분"


def _element_cards(scenario: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {card["element"]: card for card in scenario["cards"] if card.get("element")}


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
    cards = _element_cards(scenario)
    minutes = scenario["session_minutes"]
    body: dict[str, Any] = {
        "company_name": company.name,
        "duration_minutes": minutes,
        "status": session.status,
        "elements_names": [cards[e]["name"] for e in scenario["elements"]],
        "entry_notice": (
            f"한 번에 {_duration(minutes)} 연속으로 진행하며 중간 휴식은 없습니다. "
            "PC 환경을 권장합니다. "
            f"업무는 가상 회사 {scenario['company']['name']}에서 하며, "
            "지원자는 이번 과제의 리드를 맡습니다."
        ),
    }
    if session.status in ENDED:
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
    """진행 중인 세션에 링크만으로 다시 들어온다(저장된 JWT가 없어도 됨)."""
    _, session, position = await _by_token(db, token)
    if session.status != "in_progress":
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


# ---- /sessions/{id} ---------------------------------------------------------------------


@router.get("/sessions/{session_id}/state")
async def state(session_id: uuid.UUID, _: Candidate, db: Db) -> dict[str, Any]:
    """재접속 복구용 전체 스냅샷. WS는 이후 증분만 보낸다."""
    session, position = await _load(db, session_id)
    scenario = position.scenario
    now = datetime.now(UTC)

    messages = (
        (
            await db.execute(
                select(Message)
                .where(Message.session_id == session_id, Message.channel != "assistant")
                .order_by(Message.created_at, Message.seq)
            )
        )
        .scalars()
        .all()
    )
    parts = (
        (
            await db.execute(
                select(DocumentState)
                .where(DocumentState.session_id == session_id)
                .order_by(DocumentState.part_no)
            )
        )
        .scalars()
        .all()
    )
    tasks = (
        (await db.execute(select(Task).where(Task.session_id == session_id).order_by(Task.part_no)))
        .scalars()
        .all()
    )
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
        (
            await db.execute(
                select(AgentRun)
                .where(AgentRun.session_id == session_id, AgentRun.status == "started")
                .order_by(AgentRun.started_at)
            )
        )
        .scalars()
        .all()
    )
    company = scenario["company"]
    remaining = None
    if session.ends_at is not None:
        remaining = max(0, int((session.ends_at - now).total_seconds()))

    return {
        "session": {
            "id": str(session.id),
            "status": session.status,
            "started_at": _iso(session.started_at),
            "ends_at": _iso(session.ends_at),
            "remaining_seconds": remaining,
        },
        "messages": [serialize(m, session) for m in messages],
        "document": {
            str(p.part_no): {
                "content": p.content,
                "revision": p.revision,
                "updated_by": p.updated_by,
            }
            for p in parts
        },
        "tasks": [
            {"part_no": t.part_no, "assignee": t.assignee, "status": t.status} for t in tasks
        ],
        "documents": await _documents(db, session_id, scenario),
        "assistant": [
            {
                "call_id": str(call.id),
                "request": req,
                "response": resp,
                "cited_docs": list(call.cited_doc_ids),
                "t_min": _t_min(call.created_at, session),
            }
            for call, req, resp in calls
        ],
        "active_runs": [await _run_view(db, run, scenario) for run in runs],
        "persona": {
            # "프로덕트 팀장" → "한서윤 팀장"
            "manager": f"{company['manager']['name']} {company['manager']['title'].split()[-1]}",
            "colleague": company["colleague"]["name"],
        },
    }


async def _run_view(db: AsyncSession, run: AgentRun, scenario: dict[str, Any]) -> dict[str, str]:
    """agent_runs에는 actor·node가 없어 자극 종류로 정한다. 카드 실행은 카드 actor."""
    actor, node = "colleague", {"message": "respond", "event": "inject"}.get(run.stimulus, "end")
    if run.stimulus == "event" and run.ref_ids:
        card_id = await db.scalar(
            select(SessionEvent.card_id).where(SessionEvent.id == run.ref_ids[0])
        )
        card = next((c for c in scenario["cards"] if c["card_id"] == card_id), {})
        actor = "manager" if card.get("actor") == "manager" else "colleague"
    return {"run_id": str(run.run_id), "actor": actor, "node": node}


async def _documents(
    db: AsyncSession, session_id: uuid.UUID, scenario: dict[str, Any]
) -> list[dict[str, Any]]:
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
    return [
        {"doc_id": d["doc_id"], "title": d["title"], "released": d["doc_id"] in released}
        for d in scenario["documents"]
    ]


@router.put("/sessions/{session_id}/document/{part_no}")
async def put_document(
    session_id: uuid.UUID, part_no: int, body: DocumentBody, _: Candidate, db: Db, ctx: Ctx
) -> dict[str, Any]:
    """revision+1과 변경 로그(본문 스냅샷·길이·diff_ratio). 같은 본문 재요청은 그대로 돌려준다.

    세션 Lock 안에서 저장해 complete()(같은 Lock)와 직렬화한다. 그래서 제출이 시작된 뒤에는
    저장되지 않고 409 session_ending이다. Lock은 지원자 진입점만 잡는다. 내부 라우터가 잡으면
    실행 중인 runner의 내부 API 호출이 자기 Lock을 기다려 교착된다.
    """
    async with ctx.locks(session_id):
        return await _save_part(db, session_id, part_no, body.content)


async def _save_part(
    db: AsyncSession, session_id: uuid.UUID, part_no: int, content: str
) -> dict[str, Any]:
    session = await db.get(Session, session_id, populate_existing=True)
    if session is None:
        raise SessionError("not_found", "session not found")
    _ensure_writable(session)
    # 분업 전에는 리드가 어느 파트든 초안을 잡을 수 있다. 확정 뒤 동료 단독 파트는 읽기 전용
    assignee = ((session.division or {}).get("parts") or {}).get(str(part_no))
    if assignee == "colleague":
        raise _error(status.HTTP_403_FORBIDDEN, "forbidden", "colleague part is read-only")
    part = (
        await db.execute(
            select(DocumentState)
            .where(DocumentState.session_id == session_id, DocumentState.part_no == part_no)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if part is None:
        raise SessionError("not_found", f"part {part_no} not found")
    if part.content == content:
        unchanged = {"updated_at": _iso(part.updated_at), "revision": part.revision}
        await db.rollback()  # 행 잠금만 풀고 끝낸다
        return unchanged

    # DB 시각을 쓴다. 재사용 추정이 assistant_calls.created_at(DB 기본값)과 선후를 비교한다
    now = await db.scalar(select(func.now()))
    # diff_ratio: 직전 본문 대비 바뀐 비율(0 같음 ~ 1 전부 바뀜)
    diff = 1 - SequenceMatcher(None, part.content, content, autojunk=False).ratio()
    part.content = content
    part.revision += 1
    part.updated_by = "candidate"
    part.updated_at = now
    db.add(
        DocumentRevision(
            session_id=session_id,
            part_no=part_no,
            revision=part.revision,
            by="candidate",
            content=content,
            length=len(content),
            diff_ratio=round(diff, 4),
            created_at=now,
        )
    )
    await db.commit()
    return {"updated_at": _iso(now), "revision": part.revision}


@router.put("/sessions/{session_id}/tasks/{part_no}")
async def put_task(
    session_id: uuid.UUID, part_no: int, body: TaskBody, _: Candidate, db: Db
) -> dict[str, Any]:
    """지원자 담당(candidate·both) 카드만 바꾼다. 동료 카드는 그래프가 내부 API로 바꾼다."""
    session = await db.get(Session, session_id)
    if session is None:
        raise SessionError("not_found", "session not found")
    _ensure_writable(session)
    task = await db.get(Task, (session_id, part_no))
    if task is None:
        raise SessionError("not_found", f"task {part_no} not found")
    if task.assignee not in CANDIDATE_TASKS:
        raise _error(status.HTTP_403_FORBIDDEN, "forbidden", "not a candidate task")
    task.status = body.status
    await db.commit()
    return {"part_no": task.part_no, "assignee": task.assignee, "status": task.status}


@router.get("/sessions/{session_id}/documents")
async def list_documents(session_id: uuid.UUID, _: Candidate, db: Db) -> list[dict[str, Any]]:
    _, position = await _load(db, session_id)
    return await _documents(db, session_id, position.scenario)


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


@router.post("/sessions/{session_id}/submit")
async def submit(session_id: uuid.UUID, _: Candidate, db: Db, ctx: Ctx) -> dict[str, str]:
    """멱등. 종료 실행·재사용 추정·리포트 발행까지 끝난 뒤 돌려준다."""
    await ctx.session_service(db).complete(session_id, "submitted")
    return {"status": "completed"}


@router.get("/sessions/{session_id}/debrief")
async def debrief(session_id: uuid.UUID, _: DebriefReader, db: Db) -> dict[str, Any]:
    """실제 실행된(done) 요소 카드만 설명한다. 세션 실패면 연출을 드러내지 않고 중단 안내만."""
    session, position = await _load(db, session_id)
    if session.status not in ENDED:
        raise SessionError("conflict", f"session is {session.status}")
    _ensure_debrief_open(session)
    if session.failed_stage == "session":
        return {
            "events": [],
            "persona_note": None,
            "scoring_notice": (
                "세션이 중간에 중단되어 평가가 진행되지 않았습니다. "
                "채용 담당자가 다시 응시할 수 있도록 새 링크를 보내 드릴 수 있습니다."
            ),
            "failed_stage": "session",
        }
    scenario = position.scenario
    cards = _element_cards(scenario)
    done = (
        (
            await db.execute(
                select(SessionEvent.element)
                .where(
                    SessionEvent.session_id == session_id,
                    SessionEvent.element.is_not(None),
                    SessionEvent.status == "done",
                )
                .order_by(SessionEvent.due_at)
            )
        )
        .scalars()
        .all()
    )
    colleague = scenario["company"]["colleague"]["name"]
    values = scenario["persona"]["colleague"]["values"]
    body: dict[str, Any] = {
        "events": [
            {
                "element": element,
                "name": cards[element]["name"],
                "description": cards[element]["debrief"],
                "rubric_items": [item["text"] for item in cards[element].get("rubric", [])],
            }
            for element in done
        ],
        "persona_note": (
            f"함께 일한 동료 {colleague}님은 회사가 원하는 인재상으로 설정된 AI 페르소나였습니다. "
            f"이 동료는 다음 성향으로 일했습니다: {', '.join(values)}."
        ),
        "scoring_notice": (
            "세션의 행동은 평가표 항목별 관찰 기록으로 남습니다. "
            "AI가 행동을 분류한 결과를 입력으로 "
            "미리 정해진 평가표 규칙이 기본 점수를 계산하고, 최종 점수와 판단은 채용 담당자가 "
            "근거를 확인해 직접 조정합니다. 점수는 지원자에게 공개되지 않습니다."
        ),
    }
    if session.status == "failed":
        body["failed_stage"] = session.failed_stage
    return body
