"""회사 문서 공개. 스케줄러(지연 공개 시각 도래)와 내부 POST /releases/{doc_id}가 함께 쓴다.

공개 시각을 기록하고 document.released를 보내며, notice 채널에 "공개됨" 시스템 줄을 남긴다. 줄의
멱등 키는 (uuid5(session, "release:<doc_id>"), seq 1)이라 재실행·동시 호출에도 한 번만 생긴다.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hub import Hub
from app.models import DocumentRelease
from app.services.messages import save_internal_message


def _notice_text(scenario: dict[str, Any], doc_id: str, title: str) -> str:
    for card in scenario["cards"]:
        if (card.get("effects") or {}).get("release_document") == doc_id and card.get(
            "release_text"
        ):
            return card["release_text"]
    return f"「{title}」이 공개됐어요"


async def release(
    db: AsyncSession,
    hub: Hub,
    session_id: uuid.UUID,
    scenario: dict[str, Any],
    doc_id: str,
    now: datetime,
) -> datetime:
    """released_at(처음 공개한 시각)을 돌려준다. 이미 공개됐으면 아무것도 보내지 않는다."""
    title = next(d["title"] for d in scenario["documents"] if d["doc_id"] == doc_id)
    row = await db.scalar(
        select(DocumentRelease)
        .where(DocumentRelease.session_id == session_id, DocumentRelease.doc_id == doc_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is not None and row.released_at is not None:
        released_at = row.released_at  # rollback이 행을 만료시키므로 먼저 꺼낸다
        await db.rollback()
        return released_at
    if row is None:
        row = DocumentRelease(session_id=session_id, doc_id=doc_id, release_at=now)
        db.add(row)
    row.released_at = now
    await db.commit()
    await hub.broadcast(session_id, "document.released", {"doc_id": doc_id, "title": title})
    await save_internal_message(
        db,
        hub,
        session_id,
        "notice",
        "system",
        _notice_text(scenario, doc_id, title),
        uuid.uuid5(session_id, f"release:{doc_id}"),
        1,
    )
    return now
