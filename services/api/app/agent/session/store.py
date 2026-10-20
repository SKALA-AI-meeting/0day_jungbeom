"""MCP 도구가 없는 일을 api 프로세스 안에서 직접 한다(에이전트가 api 안 모듈이라 가능).

- 분류 저장: 내부 `PUT /internal/sessions/{id}/messages/{message_id}/classification`과 같은 결과
  (messages.meta.classification). kind=report인 팀 채널·팀장 DM 지원자 메시지면 같은 라우터처럼
  SessionService.mark_reported로 reported_at을 남긴다(보고 대기 종료는 스케줄러가 한다).
- observe 입력: 세션의 지원자 활동 기록 전체(메시지·문서 저장·보내기·열람·보드 변경·회사 문서
  열람·어시스턴트 호출)와 정직 사실 입력(내부 `GET /honesty_facts`와 같은 함수), 기록된 관찰.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.observe import Inputs
from app.models import (
    AssistantCall,
    Document,
    DocumentOpen,
    DocumentRelease,
    DocumentRevision,
    DocumentShare,
    DocumentVersion,
    DocView,
    Invite,
    Message,
    Observation,
    Position,
    Session,
    TaskEvent,
)
from app.services import documents
from app.services.messages import serialize

REPORT_CHANNELS = ("team", "manager_dm")


class AgentStore(Protocol):
    async def messages_page(
        self, session_id: uuid.UUID, after: dict[str, Any] | None, limit: int
    ) -> list[dict[str, Any]]: ...

    async def save_classification(
        self, session_id: uuid.UUID, message_id: uuid.UUID, classification: dict[str, Any]
    ) -> None: ...

    async def observe_inputs(self, session_id: uuid.UUID, release_doc: str | None) -> Inputs: ...

    async def observations(self, session_id: uuid.UUID) -> list[dict[str, Any]]: ...

    async def redivide_allowed(self, session_id: uuid.UUID) -> bool: ...


def _minutes(value: datetime | None, started: datetime) -> float | None:
    """세션 분. 창 경계 비교용이라 반올림하지 않는다."""
    if value is None:
        return None
    return (value - started).total_seconds() / 60


def _with_previous(revisions, docs, at) -> list[dict[str, Any]]:
    """지원자 저장본마다 같은 문서의 직전 저장본(누가 저장했든)을 붙인다. 관찰이 바뀐 부분을
    본다."""
    last: dict[uuid.UUID, str] = {}
    out = []
    for r in revisions:
        previous = last.get(r.doc_id, "")
        last[r.doc_id] = r.content
        if r.by != "candidate":
            continue
        doc = docs[r.doc_id]
        out.append(
            {
                "id": str(r.id),
                "doc_id": str(r.doc_id),
                "part_no": "final" if doc.final else doc.part_no,
                "content": r.content,
                "previous": previous,
                "t_min": at(r.created_at),
            }
        )
    return out


class _ReportMarker:
    """SessionService.mark_reported만 쓰는 최소 의존성(hub·runner 등은 쓰지 않는다)."""

    def __init__(self, db: AsyncSession) -> None:
        from app.services.session import SessionService

        self.service = SessionService(db, hub=None, runner=None, publisher=None, locks=None)  # type: ignore[arg-type]

    async def mark(self, session_id: uuid.UUID, at: datetime) -> None:
        await self.service.mark_reported(session_id, at)


class DbAgentStore:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def messages_page(
        self, session_id: uuid.UUID, after: dict[str, Any] | None, limit: int
    ) -> list[dict[str, Any]]:
        """반올림하지 않은 시각과 id로 이어 읽는다. 같은 시각의 메시지도 빠뜨리지 않는다."""
        async with self._factory() as db:
            session = await db.get(Session, session_id)
            query = select(Message).where(Message.session_id == session_id)
            if after is not None:
                query = query.where(
                    tuple_(Message.created_at, Message.id)
                    > (datetime.fromisoformat(after["created_at"]), uuid.UUID(after["id"]))
                )
            rows = await db.scalars(query.order_by(Message.created_at, Message.id).limit(limit))
            return [{**serialize(m, session), "meta": m.meta or {}} for m in rows]

    async def save_classification(
        self, session_id: uuid.UUID, message_id: uuid.UUID, classification: dict[str, Any]
    ) -> None:
        async with self._factory() as db:
            message = await db.get(Message, message_id, populate_existing=True)
            if message is None or message.session_id != session_id:
                return
            message.meta = {**(message.meta or {}), "classification": classification}
            await db.commit()
            is_report = (
                classification.get("kind") == "report"
                and message.sender == "candidate"
                and message.channel in REPORT_CHANNELS
            )
            if is_report:
                await _ReportMarker(db).mark(session_id, message.created_at)

    async def observe_inputs(self, session_id: uuid.UUID, release_doc: str | None) -> Inputs:
        async with self._factory() as db:
            session = await db.get(Session, session_id, populate_existing=True)
            started = session.started_at

            def at(value: datetime | None) -> float | None:
                return _minutes(value, started)

            messages = (
                await db.execute(
                    select(Message)
                    .where(Message.session_id == session_id, Message.channel != "assistant")
                    .order_by(Message.created_at, Message.seq)
                )
            ).scalars()
            docs = {
                d.id: d
                for d in (
                    await db.execute(select(Document).where(Document.session_id == session_id))
                ).scalars()
            }
            revisions = (
                await db.execute(
                    select(DocumentRevision)
                    .where(DocumentRevision.doc_id.in_(docs))
                    .order_by(DocumentRevision.created_at, DocumentRevision.revision)
                )
            ).scalars()
            shares = (
                await db.execute(
                    select(DocumentShare, Message.event_id, DocumentVersion.content)
                    .join(Message, Message.id == DocumentShare.message_id)
                    .join(
                        DocumentVersion,
                        (DocumentVersion.doc_id == DocumentShare.doc_id)
                        & (DocumentVersion.version == DocumentShare.version),
                    )
                    .where(DocumentShare.doc_id.in_(docs))
                    .order_by(DocumentShare.created_at)
                )
            ).all()
            opens = (
                await db.execute(
                    select(DocumentOpen)
                    .where(DocumentOpen.doc_id.in_(docs))
                    .order_by(DocumentOpen.created_at)
                )
            ).scalars()
            task_events = (
                await db.execute(
                    select(TaskEvent)
                    .where(TaskEvent.session_id == session_id)
                    .order_by(TaskEvent.created_at)
                )
            ).scalars()
            views = (
                await db.execute(
                    select(DocView)
                    .where(DocView.session_id == session_id)
                    .order_by(DocView.viewed_at)
                )
            ).scalars()
            calls = (
                await db.execute(
                    select(AssistantCall, Message.content)
                    .join(Message, Message.id == AssistantCall.request_message_id)
                    .where(AssistantCall.session_id == session_id)
                    .order_by(AssistantCall.created_at)
                )
            ).all()
            release_at = None
            if release_doc:
                release = await db.get(DocumentRelease, (session_id, release_doc))
                release_at = at(release.released_at or release.release_at) if release else None
            scenario = await db.scalar(
                select(Position.scenario)
                .join(Invite, Invite.position_id == Position.id)
                .where(Invite.id == session.invite_id)
            )
            facts = await documents.honesty_facts(db, session, scenario)
            division = None
            if session.division:
                decided = session.division.get("decided_at")
                division = {
                    "parts": session.division.get("parts"),
                    "decided_by": session.division.get("decided_by"),
                    "decided_t_min": at(datetime.fromisoformat(decided)) if decided else None,
                }
            return Inputs(
                messages=[
                    {
                        "id": str(m.id),
                        "channel": m.channel,
                        "sender": m.sender,
                        "content": m.content,
                        "event_id": str(m.event_id) if m.event_id else None,
                        "meta": m.meta or {},
                        "t_min": at(m.created_at),
                    }
                    for m in messages
                ],
                revisions=_with_previous(revisions, docs, at),
                shares=[
                    {
                        "id": str(s.id),
                        "doc_id": str(s.doc_id),
                        "owner": docs[s.doc_id].owner,
                        "part_no": docs[s.doc_id].part_no,
                        "version": s.version,
                        "channel": s.channel,
                        "event_id": str(event_id) if event_id else None,
                        "content": content,
                        "t_min": at(s.created_at),
                    }
                    for s, event_id, content in shares
                ],
                opens=[
                    {
                        "id": str(o.id),
                        "doc_id": str(o.doc_id),
                        "part_no": docs[o.doc_id].part_no,
                        "version": o.version,
                        "t_min": at(o.created_at),
                    }
                    for o in opens
                    if o.by == "candidate"
                ],
                task_events=[
                    {
                        "id": str(e.id),
                        "part_no": e.part_no,
                        "by": e.by,
                        "field": e.field,
                        "old_value": e.old_value,
                        "new_value": e.new_value,
                        "t_min": at(e.created_at),
                    }
                    for e in task_events
                ],
                doc_views=[
                    {"id": str(v.id), "doc_id": v.doc_id, "t_min": at(v.viewed_at)} for v in views
                ],
                assistant_calls=[
                    {"id": str(c.id), "request": content, "t_min": at(c.created_at)}
                    for c, content in calls
                ],
                division=division,
                release_at=release_at,
                facts=facts,
            )

    async def redivide_allowed(self, session_id: uuid.UUID) -> bool:
        """확정 뒤 재분업을 지금 할 수 있는가(보드 PUT과 같은 한도, board.redivide_allowed)."""
        from app.services import board

        async with self._factory() as db:
            session = await db.get(Session, session_id, populate_existing=True)
            stage = await board.redivide_stage(db, session_id)
            return board.redivide_allowed(session, stage, datetime.now(UTC), "chat")

    async def observations(self, session_id: uuid.UUID) -> list[dict[str, Any]]:
        async with self._factory() as db:
            session = await db.get(Session, session_id)
            rows = (
                await db.execute(select(Observation).where(Observation.session_id == session_id))
            ).scalars()
            return [
                {
                    "card_id": o.card_id,
                    "window_start": round(_minutes(o.window_start, session.started_at), 2),
                    "window_end": _minutes(o.window_end, session.started_at),
                    "label": o.label,
                    "aux": o.aux or {},
                    "metrics": o.metrics or {},
                }
                for o in rows
            ]
