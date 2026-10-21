"""WebSocket /ws/sessions/{id}?token=<세션 JWT>. 서버 프레임은 hub의 단일 송신 큐로만 나간다.

message.send: in_progress 확인 → 마스킹·저장·generation +1·agent_runs queued 한 커밋 →
message.ack(의도 분류 전) → message.new → message 자극 enqueue. 같은 client_msg_id는 기존 메시지로
ack.
typing: 지원자 입력 중(5초 갱신·6초 만료), 저장하지 않는다.
연결 없는 구간은 connection_gaps에 기록한다.
"""

import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.auth import decode_token
from app.models import ConnectionGap
from app.services import debate
from app.services.common import ServiceError, load_session, serialize_message
from app.services.context import AppContext

router = APIRouter()


async def handle_send(ctx: AppContext, session_id: uuid.UUID, payload: dict[str, Any]) -> None:
    client_msg_id = str(payload.get("client_msg_id") or "")
    content = str(payload.get("content") or "")
    if not client_msg_id or not content.strip():
        await ctx.hub.send(session_id, "error", {"code": "invalid_input", "message": "empty"})
        return
    try:
        async with ctx.session_factory() as db:
            session = await load_session(db, session_id, lock=True)
            message, run_id, stimulus = await debate.save_candidate_message(
                db, session, client_msg_id, content, ctx.clock
            )
            await db.commit()
            serialized = serialize_message(session, message)
            generation = session.generation
    except ServiceError as exc:
        code = exc.code if exc.code in ("session_ending", "invalid_input") else "conflict"
        await ctx.hub.send(session_id, "error", {"code": code, "message": exc.message})
        return
    ack = {
        "client_msg_id": client_msg_id,
        "message_id": serialized["id"],
        "run_id": str(run_id) if run_id else None,
    }
    await ctx.hub.send(session_id, "message.ack", ack)
    if stimulus is None:
        return
    ctx.generations[session_id] = generation
    await ctx.hub.send(session_id, "message.new", serialized)
    ctx.mailboxes.put(session_id, stimulus, run_id)


@router.websocket("/ws/sessions/{session_id}")
async def socket(websocket: WebSocket, session_id: uuid.UUID) -> None:
    ctx: AppContext = websocket.app.state.ctx
    token = websocket.query_params.get("token", "")
    try:
        principal = decode_token(token)
    except Exception:
        await websocket.close(code=4401)
        return
    if principal.role != "candidate":
        await websocket.close(code=4401)
        return
    if principal.subject != session_id:
        await websocket.close(code=4403)
        return
    await websocket.accept()
    await ctx.hub.connect(session_id, websocket)
    await _mark_reconnected(ctx, session_id)
    try:
        while True:
            frame = await websocket.receive_json()
            kind, payload = frame.get("type"), frame.get("payload") or {}
            if kind == "message.send":
                await handle_send(ctx, session_id, payload)
            elif kind == "typing":
                ctx.hub.candidate_typing(session_id, payload.get("state", "stop"))
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if ctx.hub.disconnect(session_id, websocket):
            await _mark_disconnected(ctx, session_id)


async def _mark_reconnected(ctx: AppContext, session_id: uuid.UUID) -> None:
    async with ctx.session_factory() as db:
        gap = await db.scalar(
            select(ConnectionGap).where(
                ConnectionGap.session_id == session_id, ConnectionGap.reconnected_at.is_(None)
            )
        )
        if gap is not None:
            gap.reconnected_at = ctx.clock.now()
            await db.commit()


async def _mark_disconnected(ctx: AppContext, session_id: uuid.UUID) -> None:
    async with ctx.session_factory() as db:
        session = await load_session(db, session_id)
        if session.status == "in_progress":
            db.add(ConnectionGap(session_id=session_id, disconnected_at=ctx.clock.now()))
            await db.commit()
