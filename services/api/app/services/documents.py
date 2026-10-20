"""문서 주고받기(docs/api/design.md "문서와 보드"). 지원자·내부 라우터가 함께 쓴다.

문서마다 주인이 하나다. 지원자 파트 문서 5개와 최종본은 세션 시작 때,
동료 문서는 처음 보낼 때 만든다.
- 자동 저장: content·revision을 바꾸고 document_revisions에 스냅샷을 남긴다(관찰·재사용 추정용).
- 보내기: 현재 revision을 가리키는 version, 문서 카드 메시지, share를 한 트랜잭션으로 만든다.
- 열기: 동료가 보낸 버전만 열고 document_opens에 남긴다.
- 최종본: final_document.sections가 섹션별 내용·출처이고, 저장마다 최종본 행에도 revision을 남긴다.
보내기는 이 모듈이 커밋하고, 나머지 쓰기는 호출자가 커밋한다.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hub import Hub
from app.models import (
    Document,
    DocumentOpen,
    DocumentRevision,
    DocumentShare,
    DocumentVersion,
    FinalDocument,
    Message,
    Session,
    SessionEvent,
    Task,
)
from app.services.messages import insert_internal_message, serialize, t_min_at

FINAL_TITLE = "최종본"


class DocumentError(Exception):
    """code: not_found(404), forbidden(403)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def diff_ratio(old: str, new: str) -> float:
    """직전 본문 대비 바뀐 비율(0 같음 ~ 1 전부 바뀜)."""
    if not old and not new:
        return 0.0
    # autojunk는 긴 한국어 본문에서 자주 나오는 글자를 버려 비율을 왜곡한다
    return round(1 - SequenceMatcher(None, old, new, autojunk=False).ratio(), 4)


def part_title(scenario: dict[str, Any], part_no: int) -> str:
    return scenario["parts"][str(part_no)]["title"]


async def db_now(db: AsyncSession) -> datetime:
    """DB 시각. 재사용 추정이 assistant_calls.created_at(DB 기본값)과 선후를 비교한다."""
    return await db.scalar(select(func.now()))


# ───────────── 생성 ─────────────


async def create_session_documents(
    db: AsyncSession, session_id: uuid.UUID, scenario: dict[str, Any]
) -> None:
    """지원자 파트 문서(빈 본문)와 최종본 행, 템플릿 골격의 final_document를 만든다."""
    for no in scenario["parts"]:
        db.add(
            Document(
                session_id=session_id,
                owner="candidate",
                part_no=int(no),
                final=False,
                title=part_title(scenario, int(no)),
            )
        )
    db.add(Document(session_id=session_id, owner="candidate", final=True, title=FINAL_TITLE))
    sections = [
        {
            "part_no": s["part_no"],
            "title": s["title"],
            "content": "",
            "source_doc_id": None,
            "source_version": None,
            "edited": False,
        }
        for s in scenario["final_template"]["sections"]
    ]
    db.add(FinalDocument(session_id=session_id, sections=sections))


# ───────────── 조회 도우미 ─────────────


async def candidate_part(db: AsyncSession, session_id: uuid.UUID, part_no: int) -> Document:
    doc = await db.scalar(
        select(Document)
        .where(
            Document.session_id == session_id,
            Document.owner == "candidate",
            Document.part_no == part_no,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if doc is None:
        raise DocumentError("not_found", f"part {part_no} not found")
    return doc


async def final_doc(db: AsyncSession, session_id: uuid.UUID) -> tuple[Document, FinalDocument]:
    doc = await db.scalar(
        select(Document)
        .where(Document.session_id == session_id, Document.final.is_(True))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    final = await db.get(FinalDocument, session_id, populate_existing=True, with_for_update=True)
    if doc is None or final is None:
        raise DocumentError("not_found", "final document not found")
    return doc, final


async def session_document(db: AsyncSession, session_id: uuid.UUID, doc_id: uuid.UUID) -> Document:
    doc = await db.get(Document, doc_id, populate_existing=True)
    if doc is None or doc.session_id != session_id:
        raise DocumentError("not_found", "document not found")
    return doc


def _append_revision(db: AsyncSession, doc: Document, content: str, by: str, now: datetime) -> None:
    """content·revision을 바꾸고 스냅샷 한 행을 남긴다."""
    db.add(
        DocumentRevision(
            doc_id=doc.id,
            revision=doc.revision + 1,
            by=by,
            content=content,
            length=len(content),
            diff_ratio=diff_ratio(doc.content, content),
            created_at=now,
        )
    )
    doc.content = content
    doc.revision += 1
    doc.updated_at = now


def final_text(sections: list[dict[str, Any]]) -> str:
    """최종본 documents 행의 본문(revision 스냅샷). 섹션 제목과 내용을 순서대로 잇는다."""
    return "\n\n".join(f"## {s['part_no']}. {s['title']}\n{s['content']}" for s in sections)


async def freeze_final(db: AsyncSession, session_id: uuid.UUID) -> None:
    """제출 시 최종본 현재 내용을 version 1로 고정한다. 이미 있으면 그대로(재실행 멱등)."""
    doc, _ = await final_doc(db, session_id)
    if await _version(db, doc.id, 1) is None:
        db.add(
            DocumentVersion(doc_id=doc.id, version=1, revision=doc.revision, content=doc.content)
        )


# ───────────── 지원자 쓰기 ─────────────


async def save_part(
    db: AsyncSession, session_id: uuid.UUID, part_no: int, content: str
) -> dict[str, Any]:
    """디바운스 자동 저장. 같은 본문이면 revision을 늘리지 않는다."""
    doc = await candidate_part(db, session_id, part_no)
    if doc.content != content:
        _append_revision(db, doc, content, "candidate", await db_now(db))
    return {"updated_at": iso(doc.updated_at), "revision": doc.revision}


async def save_final(
    db: AsyncSession, session_id: uuid.UUID, sections: list[dict[str, Any]]
) -> dict[str, Any]:
    """바뀐 섹션만 덮어쓰고 edited=true. 출처(source_doc_id·version)는 그대로 둔다."""
    doc, final = await final_doc(db, session_id)
    updated = [dict(s) for s in final.sections]
    by_part = {s["part_no"]: s for s in updated}
    changed = False
    for patch in sections:
        section = by_part.get(patch["part_no"])
        if section is None:
            raise DocumentError("not_found", f"final section {patch['part_no']} not found")
        if section["content"] != patch["content"]:
            section["content"] = patch["content"]
            section["edited"] = True
            changed = True
    if changed:
        now = await db_now(db)
        final.sections = updated
        final.updated_at = now
        _append_revision(db, doc, final_text(updated), "candidate", now)
    return {"updated_at": iso(final.updated_at), "revision": doc.revision}


async def _version(db: AsyncSession, doc_id: uuid.UUID, version: int) -> DocumentVersion | None:
    return await db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.doc_id == doc_id, DocumentVersion.version == version
        )
    )


async def _shared_versions(db: AsyncSession, doc_id: uuid.UUID) -> set[int]:
    rows = await db.execute(select(DocumentShare.version).where(DocumentShare.doc_id == doc_id))
    return set(rows.scalars())


async def import_section(
    db: AsyncSession,
    session: Session,
    part_no: int,
    source_doc_id: uuid.UUID,
    version: int | None,
) -> dict[str, Any]:
    """그 버전 내용으로 섹션을 덮어쓰고 출처를 남긴다(edited=false). 동료 문서는 보낸 버전만.

    version이 null이면 내 문서의 현재 저장본(보내지 않았어도 됨)이고 source_version도 null이다.
    """
    source = await session_document(db, session.id, source_doc_id)
    if source.final:
        raise DocumentError("not_found", "final cannot be a source")
    if version is None:
        if source.owner != "candidate":
            raise DocumentError("not_found", "colleague documents need a sent version")
        content = source.content
    else:
        found = await _version(db, source.id, version)
        if found is None or (
            source.owner == "colleague" and version not in await _shared_versions(db, source.id)
        ):
            raise DocumentError("not_found", "version not found")
        content = found.content
    doc, final = await final_doc(db, session.id)
    updated = [dict(s) for s in final.sections]
    section = next((s for s in updated if s["part_no"] == part_no), None)
    if section is None:
        raise DocumentError("not_found", f"final section {part_no} not found")
    section.update(
        content=content, source_doc_id=str(source.id), source_version=version, edited=False
    )
    now = await db_now(db)
    final.sections = updated
    final.updated_at = now
    _append_revision(db, doc, final_text(updated), "candidate", now)
    return section


def _share_text(doc: Document, version: int) -> str:
    """동료 문서 카드 메시지의 본문(동료의 말은 그래프가 따로 post한다)."""
    return f"{doc.part_no}번 {doc.title} v{version}"


async def _next_version(db: AsyncSession, doc_id: uuid.UUID) -> int:
    current = await db.scalar(
        select(func.coalesce(func.max(DocumentVersion.version), 0)).where(
            DocumentVersion.doc_id == doc_id
        )
    )
    return current + 1


@dataclass
class Sent:
    doc: Document
    version: int
    message: Message
    created: bool


async def _send(
    db: AsyncSession,
    hub: Hub,
    session: Session,
    doc: Document,
    channel: str,
    by: str,
    content: str,
    run_id: uuid.UUID,
    seq: int,
    event_id: uuid.UUID | None = None,
) -> Sent:
    """version 고정 → 문서 카드 메시지(meta.shared_doc) → document_shares를 한 트랜잭션으로 커밋한
    뒤 message.new·document.shared를 보낸다.

    중간에 끊기면 아무것도 남지 않으므로 같은 요청을 그대로 다시 보내면 된다.
    """
    number = await _next_version(db, doc.id)
    db.add(
        DocumentVersion(
            doc_id=doc.id,
            version=number,
            revision=doc.revision,
            content=doc.content,
            run_id=run_id if by == "colleague" else None,
        )
    )
    await db.flush()
    message, _ = await insert_internal_message(
        db,
        session.id,
        channel,
        by,
        content,
        run_id,
        seq,
        event_id,
        {"shared_doc": {"doc_id": str(doc.id), "version": number}},
    )
    db.add(DocumentShare(doc_id=doc.id, version=number, channel=channel, message_id=message.id))
    await db.commit()
    await hub.broadcast(session.id, "message.new", serialize(message, session))
    await hub.broadcast(
        session.id,
        "document.shared",
        {
            "doc_id": str(doc.id),
            "version": number,
            "part_no": doc.part_no,
            "by": by,
            "channel": channel,
            "message_id": str(message.id),
        },
    )
    return Sent(doc, number, message, True)


async def share_part(
    db: AsyncSession, hub: Hub, session: Session, part_no: int, channel: str, note: str = ""
) -> dict[str, Any]:
    """지원자 보내기. 메시지 본문은 지원자가 쓴 note뿐이다(시스템이 지원자 발화를 만들지 않음).

    메시지 멱등 키가 필요 없어 새 run_id·seq=파트 번호×10을 쓴다.
    """
    doc = await candidate_part(db, session.id, part_no)
    run_id = uuid.uuid4()
    sent = await _send(db, hub, session, doc, channel, "candidate", note, run_id, part_no * 10)
    return {"version": sent.version, "message_id": str(sent.message.id)}


async def colleague_send(
    db: AsyncSession,
    hub: Hub,
    session: Session,
    scenario: dict[str, Any],
    content: str,
    channel: str,
    run_id: uuid.UUID,
    seq: int,
    event_id: uuid.UUID | None,
    doc_id: uuid.UUID | None = None,
    part_no: int | None = None,
) -> dict[str, Any]:
    """동료 문서 쓰기·보내기. (doc_id, run_id) 멱등이라 재요청은 버전을 늘리지 않는다."""
    if doc_id is not None:
        doc = await session_document(db, session.id, doc_id)
        if doc.owner != "colleague":
            raise DocumentError("forbidden", "not a colleague document")
        part_no = doc.part_no
    else:
        doc = await db.scalar(
            select(Document).where(
                Document.session_id == session.id,
                Document.owner == "colleague",
                Document.part_no == part_no,
            )
        )
    task = await db.get(Task, (session.id, part_no))
    if task is None or task.assignee not in ("colleague", "both"):
        raise DocumentError("forbidden", "part is not the colleague's")

    if doc is not None:
        done = await db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.doc_id == doc.id, DocumentVersion.run_id == run_id
            )
        )
        if done is not None:
            share = await db.scalar(
                select(DocumentShare).where(
                    DocumentShare.doc_id == doc.id, DocumentShare.version == done.version
                )
            )
            return {
                "doc_id": str(doc.id),
                "version": done.version,
                "message_id": str(share.message_id),
            }
    else:
        doc = Document(
            session_id=session.id,
            owner="colleague",
            part_no=part_no,
            final=False,
            title=part_title(scenario, part_no),
        )
        db.add(doc)
        await db.flush()
    if doc.content != content:
        _append_revision(db, doc, content, "colleague", await db_now(db))
    text = _share_text(doc, await _next_version(db, doc.id))
    sent = await _send(db, hub, session, doc, channel, "colleague", text, run_id, seq, event_id)
    return {"doc_id": str(doc.id), "version": sent.version, "message_id": str(sent.message.id)}


async def open_received(
    db: AsyncSession, session: Session, doc_id: uuid.UUID, version: int
) -> dict[str, Any]:
    """동료가 보낸 버전만 연다(아니면 not_found). 열람은 document_opens에 남긴다."""
    doc = await session_document(db, session.id, doc_id)
    found = await _version(db, doc.id, version)
    if (
        doc.owner != "colleague"
        or found is None
        or version not in await _shared_versions(db, doc.id)
    ):
        raise DocumentError("not_found", "shared version not found")
    now = await db_now(db)
    db.add(DocumentOpen(doc_id=doc.id, version=version, by="candidate", created_at=now))
    return {
        "doc_id": str(doc.id),
        "owner": doc.owner,
        "part_no": doc.part_no,
        "title": doc.title,
        "version": version,
        "content": found.content,
        "t_min": t_min_at(now, session),
    }


async def is_shared_version(
    db: AsyncSession, session_id: uuid.UUID, doc_id: str, version: int
) -> bool:
    """reply_to_doc 검증: 같은 세션 문서의 보낸 버전인가."""
    try:
        key = uuid.UUID(doc_id)
    except ValueError:
        return False
    doc = await db.get(Document, key)
    if doc is None or doc.session_id != session_id:
        return False
    return version in await _shared_versions(db, key)


# ───────────── 조회 ─────────────


async def _documents(db: AsyncSession, session_id: uuid.UUID) -> list[Document]:
    rows = await db.execute(
        select(Document)
        .where(Document.session_id == session_id)
        .order_by(Document.final, Document.owner, Document.part_no)
        .execution_options(populate_existing=True)
    )
    return list(rows.scalars())


async def _versions(
    db: AsyncSession, doc_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[DocumentVersion]]:
    out: dict[uuid.UUID, list[DocumentVersion]] = {d: [] for d in doc_ids}
    rows = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.doc_id.in_(doc_ids))
        .order_by(DocumentVersion.version)
    )
    for v in rows.scalars():
        out[v.doc_id].append(v)
    return out


async def _shares(
    db: AsyncSession, doc_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[DocumentShare]]:
    out: dict[uuid.UUID, list[DocumentShare]] = {d: [] for d in doc_ids}
    rows = await db.execute(
        select(DocumentShare)
        .where(DocumentShare.doc_id.in_(doc_ids))
        .order_by(DocumentShare.created_at, DocumentShare.version)
    )
    for s in rows.scalars():
        out[s.doc_id].append(s)
    return out


async def _opens(db: AsyncSession, doc_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[DocumentOpen]]:
    out: dict[uuid.UUID, list[DocumentOpen]] = {d: [] for d in doc_ids}
    rows = await db.execute(
        select(DocumentOpen)
        .where(DocumentOpen.doc_id.in_(doc_ids))
        .order_by(DocumentOpen.created_at)
    )
    for o in rows.scalars():
        out[o.doc_id].append(o)
    return out


async def final_view(db: AsyncSession, session_id: uuid.UUID) -> FinalDocument | None:
    return await db.get(FinalDocument, session_id, populate_existing=True)


async def my_documents(db: AsyncSession, session: Session) -> dict[str, Any]:
    """GET /sessions/{id}/my-documents와 State의 my_documents·received·final."""
    docs = await _documents(db, session.id)
    ids = [d.id for d in docs]
    shares, opens = await _shares(db, ids), await _opens(db, ids)
    versions = await _versions(db, ids)

    def version_rows(doc: Document) -> list[dict[str, Any]]:
        by_version = {v.version: v for v in versions[doc.id]}
        return [
            {
                "version": s.version,
                "revision": by_version[s.version].revision,
                "channel": s.channel,
                "message_id": str(s.message_id),
                "t_min": t_min_at(s.created_at, session),
            }
            for s in shares[doc.id]
        ]

    mine = [
        {
            "doc_id": str(d.id),
            "part_no": d.part_no,
            "title": d.title,
            "content": d.content,
            "updated_at": iso(d.updated_at),
            "revision": d.revision,
            "versions": version_rows(d),
        }
        for d in docs
        if d.owner == "candidate" and not d.final
    ]
    received = []
    for d in docs:
        if d.owner != "colleague":
            continue
        opened = {o.version for o in opens[d.id]}
        received.append(
            {
                "doc_id": str(d.id),
                "owner": "colleague",
                "part_no": d.part_no,
                "title": d.title,
                "versions": [
                    {
                        "version": s.version,
                        "channel": s.channel,
                        "message_id": str(s.message_id),
                        "t_min": t_min_at(s.created_at, session),
                        "opened": s.version in opened,
                    }
                    for s in shares[d.id]
                ],
            }
        )
    received.sort(key=lambda r: r["part_no"])
    final = await final_view(db, session.id)
    return {
        "documents": mine,
        "received": received,
        "final": {"sections": final.sections, "updated_at": iso(final.updated_at)},
    }


async def internal_docs(db: AsyncSession, session: Session) -> dict[str, Any]:
    """GET /internal/sessions/{id}/docs: 워커·observe용 전체."""
    docs = await _documents(db, session.id)
    ids = [d.id for d in docs]
    versions, shares, opens = (
        await _versions(db, ids),
        await _shares(db, ids),
        await _opens(db, ids),
    )
    final = await final_view(db, session.id)
    return {
        "documents": [
            {
                "doc_id": str(d.id),
                "owner": d.owner,
                "part_no": d.part_no,
                "final": d.final,
                "title": d.title,
                "content": d.content,
                "revision": d.revision,
                "updated_at": iso(d.updated_at),
                "versions": [
                    {
                        "id": str(v.id),
                        "version": v.version,
                        "revision": v.revision,
                        "content": v.content,
                        "created_at": iso(v.created_at),
                    }
                    for v in versions[d.id]
                ],
                "shares": [
                    {
                        "id": str(s.id),
                        "version": s.version,
                        "channel": s.channel,
                        "message_id": str(s.message_id),
                        "created_at": iso(s.created_at),
                    }
                    for s in shares[d.id]
                ],
                "opens": [
                    {
                        "id": str(o.id),
                        "version": o.version,
                        "by": o.by,
                        "created_at": iso(o.created_at),
                    }
                    for o in opens[d.id]
                ],
            }
            for d in docs
        ],
        "final": {"sections": final.sections if final else []},
    }


async def shared_docs(db: AsyncSession, session: Session) -> dict[str, Any]:
    """페르소나 컨텍스트용. 지원자 문서는 보낸 버전만, 동료 문서는 전부(동료 문서는 보낼 때만 버전이
    생김).
    """
    docs = [d for d in await _documents(db, session.id) if not d.final]
    ids = [d.id for d in docs]
    versions, shares = await _versions(db, ids), await _shares(db, ids)
    out = []
    for d in docs:
        sent = {s.version for s in shares[d.id]}
        rows = [v for v in versions[d.id] if v.version in sent]
        if not rows:
            continue
        out.append(
            {
                "doc_id": str(d.id),
                "owner": d.owner,
                "part_no": d.part_no,
                "title": d.title,
                "versions": [
                    {"version": v.version, "content": v.content, "created_at": iso(v.created_at)}
                    for v in rows
                ],
            }
        )
    return {"documents": out}


async def revisions(
    db: AsyncSession, session: Session, doc_id: uuid.UUID | None, since_t_min: float | None
) -> list[dict[str, Any]]:
    """자동 저장 스냅샷 이력. 최종본은 part_no "final"."""
    query = (
        select(DocumentRevision, Document)
        .join(Document, Document.id == DocumentRevision.doc_id)
        .where(Document.session_id == session.id)
    )
    if doc_id is not None:
        query = query.where(Document.id == doc_id)
    if since_t_min is not None and session.started_at is not None:
        query = query.where(
            DocumentRevision.created_at > session.started_at + timedelta(minutes=since_t_min)
        )
    rows = await db.execute(query.order_by(DocumentRevision.created_at, DocumentRevision.revision))
    return [
        {
            "id": str(r.id),
            "doc_id": str(d.id),
            "part_no": "final" if d.final else d.part_no,
            "revision": r.revision,
            "by": r.by,
            "length": r.length,
            "diff_ratio": r.diff_ratio,
            "content": r.content,
            "created_at": iso(r.created_at),
            "t_min": t_min_at(r.created_at, session),
        }
        for r, d in rows
    ]


# ───────────── 정직 사실 입력 ─────────────


async def honesty_facts(
    db: AsyncSession, session: Session, scenario: dict[str, Any]
) -> dict[str, Any]:
    """정직 카드의 사실 입력(rubric.md). 규칙으로만 계산하고 품질 판단은 없다."""
    docs = [d for d in await _documents(db, session.id) if not d.final]
    shares = await _shares(db, [d.id for d in docs])
    tasks = (
        (await db.execute(select(Task).where(Task.session_id == session.id).order_by(Task.part_no)))
        .scalars()
        .all()
    )
    final = await final_view(db, session.id)
    sections = final.sections if final else []

    changed: bool | None = None
    if "adaptability" in scenario["elements"]:
        due = await db.scalar(
            select(SessionEvent.due_at).where(
                SessionEvent.session_id == session.id,
                SessionEvent.card_id == "adaptability_change",
            )
        )
        mine = [d.id for d in docs if d.owner == "candidate"]
        final_row = await db.scalar(
            select(Document.id).where(Document.session_id == session.id, Document.final.is_(True))
        )
        later_revision = await db.scalar(
            select(func.count())
            .select_from(DocumentRevision)
            .where(
                DocumentRevision.doc_id.in_([*mine, final_row]),
                DocumentRevision.by == "candidate",
                DocumentRevision.created_at >= due,
            )
        )
        later_share = sum(1 for d in mine for s in shares[d] if s.created_at >= due)
        changed = bool(later_revision or later_share)

    return {
        "shares": [
            {
                "doc_id": str(d.id),
                "owner": d.owner,
                "part_no": d.part_no,
                "versions": [
                    {
                        "version": s.version,
                        "channel": s.channel,
                        "t_min": t_min_at(s.created_at, session),
                    }
                    for s in shares[d.id]
                ],
            }
            for d in docs
            if shares[d.id]
        ],
        "final_sections": [
            {
                "part_no": s["part_no"],
                "source_doc_id": s["source_doc_id"],
                "source_version": s["source_version"],
                "edited": s["edited"],
            }
            for s in sections
        ],
        "tasks": [
            {"part_no": t.part_no, "assignee": t.assignee, "status": t.status} for t in tasks
        ],
        # 본문이 빈 최종본 섹션(rubric.md 정의. 누가 맡았는지와 무관하게 팀 결과의 빈 곳)
        "empty_sections": [s["part_no"] for s in sections if not s["content"].strip()],
        "tasks_not_done": [t.part_no for t in tasks if t.status != "done"],
        "changed_after_adaptability": changed,
    }
