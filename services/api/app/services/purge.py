"""보관 기한 삭제(data-model.md "보관과 삭제"). ended_at + 90일이 지난 세션을 세션 단위로 지운다.

completed 이후·failed·cancelled 모두 대상이고 끝나지 않은 세션(ended_at 없음)은 대상이 아니다.
채용 건 정의와 지원자 수는 남기므로 초대 행은 지우지 않고 별칭·이메일·토큰 해시만 지운다.
스키마에 ON DELETE CASCADE가 없어 자식 테이블부터 FK 순서대로 지운다.
"""

import uuid
from datetime import datetime

from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AgentRun,
    AssistantCall,
    ConnectionGap,
    DebriefSurvey,
    Evaluation,
    EvaluationRun,
    Invite,
    MaterialView,
    Message,
    MessageIntent,
    Observation,
    Option,
    Proposal,
    Report,
    ReportNote,
    RubricAdjustment,
    Session,
    SessionCard,
    Slot,
    Stance,
)
from app.services.common import RETENTION

# 자식 → 부모 순서(메시지·안을 가리키는 행이 먼저)
CHILDREN = (
    ReportNote,
    RubricAdjustment,
    Report,
    Evaluation,
    EvaluationRun,
    Observation,
    SessionCard,
    DebriefSurvey,
    AssistantCall,
    MaterialView,
    ConnectionGap,
    AgentRun,
    Proposal,
    Slot,
    Stance,
    MessageIntent,
    Option,
    Message,
)
CHECKPOINT_PREFIXES = ("debate:", "assistant:", "report:")


async def purge_expired(db: AsyncSession, now: datetime) -> int:
    rows = (
        await db.execute(
            select(Session.id, Session.invite_id).where(Session.ended_at <= now - RETENTION)
        )
    ).all()
    for session_id, invite_id in rows:
        for table in CHILDREN:
            await db.execute(delete(table).where(table.session_id == session_id))
        await _drop_checkpoints(db, session_id)
        await db.execute(delete(Session).where(Session.id == session_id))
        await db.execute(
            update(Invite)
            .where(Invite.id == invite_id)
            .values(alias="(삭제됨)", email="", token_hash=f"purged:{invite_id}", superseded_at=now)
        )
    await db.commit()
    return len(rows)


async def _drop_checkpoints(db: AsyncSession, session_id: uuid.UUID) -> None:
    """LangGraph 체크포인트 thread(debate:·assistant:·report:)를 지운다. 테이블이 없으면
    건너뛴다."""
    for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
        if await db.scalar(text(f"SELECT to_regclass('{table}')")) is None:
            continue
        for prefix in CHECKPOINT_PREFIXES:
            await db.execute(
                text(f"DELETE FROM {table} WHERE thread_id LIKE :thread"),
                {"thread": f"{prefix}{session_id}%"},
            )
