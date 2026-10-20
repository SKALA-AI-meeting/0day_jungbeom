"""여러 라우터가 같은 형태로 내는 조회: 회사 문서 공개 목록, 접속 끊김 구간, 전체 기록 타임라인.

전체 기록(GET /admin/sessions/{id}/record)의 ref {type, id, t_min}는 리포트 근거의 record_ref와 같은
값이다.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AssistantCall,
    ConnectionGap,
    Document,
    DocumentOpen,
    DocumentRelease,
    DocumentShare,
    Message,
    Session,
    TaskEvent,
)
from app.services.messages import t_min_at


async def company_documents(
    db: AsyncSession, session: Session, scenario: dict[str, Any]
) -> list[dict[str, Any]]:
    """회사 문서 목록. release_at_min은 아직 공개 전인 지연 공개만(공개됐거나 시작 공개면 null)."""
    rows = {
        r.doc_id: r
        for r in (
            await db.execute(
                select(DocumentRelease).where(DocumentRelease.session_id == session.id)
            )
        ).scalars()
    }
    out = []
    for d in scenario["documents"]:
        row = rows.get(d["doc_id"])
        released = row is not None and row.released_at is not None
        out.append(
            {
                "doc_id": d["doc_id"],
                "title": d["title"],
                "released": released,
                "release_at_min": (
                    None if released or row is None else t_min_at(row.release_at, session)
                ),
            }
        )
    return out


async def gap_rows(db: AsyncSession, session: Session) -> list[ConnectionGap]:
    rows = await db.execute(
        select(ConnectionGap)
        .where(ConnectionGap.session_id == session.id)
        .order_by(ConnectionGap.disconnected_at)
    )
    return list(rows.scalars())


async def connection_gaps(db: AsyncSession, session: Session) -> list[dict[str, Any]]:
    return [
        {
            "from_t_min": t_min_at(g.disconnected_at, session),
            "to_t_min": t_min_at(g.reconnected_at, session),
        }
        for g in await gap_rows(db, session)
    ]


def _clock(t_min: float | None) -> str:
    if t_min is None:
        return "종료"
    total = int(t_min)
    return f"{total // 60:02d}:{total % 60:02d}"


def _num(value: float | None) -> str:
    """12.0 → "12", 12.5 → "12.5"(요약 문장의 분 표기)."""
    return "" if value is None else f"{value:g}"


# 보드 변경 요약의 필드·값 한국어 표기(contracts.md "n번 <필드> → <새 값>(t분)").
_FIELD_NAMES = {"assignee": "담당", "status": "상태", "order": "순서", "due_min": "언제까지"}
_VALUE_NAMES = {
    "candidate": "지원자",
    "colleague": "동료",
    "both": "함께",
    "todo": "할 일",
    "doing": "진행 중",
    "done": "완료",
}


def _task_summary(part_no: int, field: str, new_value: str | None, t_min: float | None) -> str:
    """ "1번 담당 → 지원자(12분)", "1번 언제까지 → 40분(15분)". 값이 비면 "없음"."""
    if new_value is None:
        value = "없음"
    elif field == "due_min":
        value = f"{new_value}분"
    else:
        value = _VALUE_NAMES.get(new_value, new_value)
    return f"{part_no}번 {_FIELD_NAMES.get(field, field)} → {value}({_num(t_min)}분)"


def _entry(t_min, type_, by, summary, ref_type, ref_id, channel=None) -> dict[str, Any]:
    entry = {"t_min": t_min, "type": type_}
    if channel is not None:
        entry["channel"] = channel
    entry.update(
        {"by": by, "summary": summary, "ref": {"type": ref_type, "id": str(ref_id), "t_min": t_min}}
    )
    return entry


async def record(db: AsyncSession, session: Session) -> list[dict[str, Any]]:
    """대화(채널별, 카드 메시지 포함)·문서 보내기/열기·보드 변경·어시스턴트 호출·알림·접속 끊김을
    t_min 순으로.
    """
    out: list[dict[str, Any]] = []
    messages = await db.execute(
        select(Message)
        .where(Message.session_id == session.id, Message.channel != "assistant")
        .order_by(Message.created_at, Message.seq)
    )
    for m in messages.scalars():
        t = t_min_at(m.created_at, session)
        type_ = "notice" if m.channel == "notice" else "message"
        out.append(_entry(t, type_, m.sender, m.content, "message", m.id, m.channel))

    docs = {
        d.id: d
        for d in (
            await db.execute(select(Document).where(Document.session_id == session.id))
        ).scalars()
    }
    shares = await db.execute(select(DocumentShare).where(DocumentShare.doc_id.in_(list(docs))))
    for s in shares.scalars():
        doc = docs[s.doc_id]
        t = t_min_at(s.created_at, session)
        prefix = "동료 " if doc.owner == "colleague" else ""
        summary = f"{prefix}{doc.part_no}번 파트 v{s.version} 보냄({_num(t)}분)"
        out.append(_entry(t, "share", doc.owner, summary, "share", s.id, s.channel))
    opens = await db.execute(select(DocumentOpen).where(DocumentOpen.doc_id.in_(list(docs))))
    for o in opens.scalars():
        doc = docs[o.doc_id]
        t = t_min_at(o.created_at, session)
        summary = f"동료 {doc.part_no}번 v{o.version} 열람({_num(t)}분)"
        out.append(_entry(t, "open", "candidate", summary, "open", o.id))

    events = await db.execute(select(TaskEvent).where(TaskEvent.session_id == session.id))
    for e in events.scalars():
        t = t_min_at(e.created_at, session)
        summary = _task_summary(e.part_no, e.field, e.new_value, t)
        out.append(_entry(t, "task_event", e.by, summary, "task_event", e.id))

    calls = await db.execute(
        select(AssistantCall, Message.content)
        .join(Message, Message.id == AssistantCall.request_message_id)
        .where(AssistantCall.session_id == session.id)
    )
    for call, request in calls.all():
        t = t_min_at(call.created_at, session)
        out.append(_entry(t, "assistant_call", "candidate", request, "assistant_call", call.id))

    for g in await gap_rows(db, session):
        start, end = t_min_at(g.disconnected_at, session), t_min_at(g.reconnected_at, session)
        summary = f"{_clock(start)}~{_clock(end)} 연결 끊김"
        out.append(_entry(start, "connection_gap", "system", summary, "connection_gap", g.id))

    out.sort(key=lambda e: (e["t_min"] is None, e["t_min"] or 0))
    return out
