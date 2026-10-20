"""메시지 저장과 브로드캐스트. WS 라우터(지원자)와 내부 라우터(MCP 경유 페르소나)가 함께 쓴다.

지원자: 마스킹 → 저장((session_id, client_msg_id) 멱등, 커밋) → agent_runs started(커밋)
        → message.ack·message.new. 이어서 호출자가 runs.run_agent로 실행한다.
내부:   (session_id, run_id, seq) 멱등 저장(커밋) → 새로 만든 행만 message.new.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runner import Stimulus
from app.hub import Hub
from app.masking import mask
from app.models import AgentRun, Message, Session
from app.services.runs import start_run
from app.services.session import SessionError


def t_min(message: Message, session: Session) -> float | None:
    if session.started_at is None:
        return None
    return round((message.created_at - session.started_at).total_seconds() / 60, 2)


def serialize(message: Message, session: Session) -> dict[str, Any]:
    """contracts.md의 Message 형식."""
    return {
        "id": str(message.id),
        "channel": message.channel,
        "sender": message.sender,
        "content": message.content,
        "event_id": str(message.event_id) if message.event_id else None,
        "run_id": str(message.run_id) if message.run_id else None,
        "t_min": t_min(message, session),
        "created_at": message.created_at.isoformat(),
    }


async def _session(db: AsyncSession, session_id: uuid.UUID) -> Session:
    session = await db.get(Session, session_id)
    if session is None:
        raise SessionError("not_found", "session not found")
    return session


async def accept_candidate_message(
    db: AsyncSession,
    hub: Hub,
    session_id: uuid.UUID,
    client_msg_id: str,
    channel: str,
    content: str,
) -> tuple[Message, uuid.UUID, bool]:
    """(message, run_id, created).

    같은 client_msg_id 재전송은 기존 메시지와 그 run_id로 다시 ack한다.
    """
    session = await _session(db, session_id)
    if session.status != "in_progress":
        raise SessionError("conflict", f"session is {session.status}")
    if session.submitted_at is not None:
        raise SessionError("session_ending", "session already submitted")

    stmt = (
        insert(Message)
        .values(
            session_id=session_id,
            channel=channel,
            sender="candidate",
            content=mask(content),
            client_msg_id=client_msg_id,
        )
        .on_conflict_do_nothing(
            index_elements=["session_id", "client_msg_id"],
            index_where=Message.client_msg_id.is_not(None),
        )
        .returning(Message.id)
    )
    new_id = (await db.execute(stmt)).scalar_one_or_none()
    created = new_id is not None
    if created:
        run_id = uuid.uuid4()
        await start_run(db, session_id, Stimulus("message", message_id=new_id), run_id)
        await db.commit()
        message = await db.get(Message, new_id)
    else:
        await db.rollback()
        message = (
            await db.execute(
                select(Message).where(
                    Message.session_id == session_id, Message.client_msg_id == client_msg_id
                )
            )
        ).scalar_one()
        run_id = (
            await db.execute(select(AgentRun.run_id).where(AgentRun.ref_ids.contains([message.id])))
        ).scalar_one()

    ack = {"client_msg_id": client_msg_id, "message_id": str(message.id), "run_id": str(run_id)}
    await hub.broadcast(session_id, "message.ack", ack)
    if created:
        await hub.broadcast(session_id, "message.new", serialize(message, session))
    return message, run_id, created


async def save_internal_message(
    db: AsyncSession,
    hub: Hub,
    session_id: uuid.UUID,
    channel: str,
    sender: str,
    content: str,
    run_id: uuid.UUID,
    seq: int,
    event_id: uuid.UUID | None = None,
    meta: dict[str, Any] | None = None,
) -> tuple[Message, bool]:
    """POST /internal/sessions/{id}/messages의 저장부.

    같은 run_id+seq 재요청은 기존 행을 돌려주고 다시 브로드캐스트하지 않는다.
    """
    session = await _session(db, session_id)
    stmt = (
        insert(Message)
        .values(
            session_id=session_id,
            channel=channel,
            sender=sender,
            content=content,
            event_id=event_id,
            run_id=run_id,
            seq=seq,
            meta=meta or {},
        )
        .on_conflict_do_nothing(index_elements=["session_id", "run_id", "seq"])
        .returning(Message.id)
    )
    new_id = (await db.execute(stmt)).scalar_one_or_none()
    await db.commit()
    created = new_id is not None
    if created:
        message = await db.get(Message, new_id)
        await hub.broadcast(session_id, "message.new", serialize(message, session))
    else:
        message = (
            await db.execute(
                select(Message).where(
                    Message.session_id == session_id,
                    Message.run_id == run_id,
                    Message.seq == seq,
                )
            )
        ).scalar_one()
    return message, created
