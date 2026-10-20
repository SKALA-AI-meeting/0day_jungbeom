"""WebSocket /ws/sessions/{id}?token=<세션 JWT>. 프레임은 {"type", "payload"} 봉투(contracts.md).

연결: accept → 토큰 검증(실패면 4401·4403으로 닫음) → hub.connect(같은 세션의 이전 연결은
session.replaced 후 close 4000). message.send: accept_candidate_message(마스킹·멱등
저장·ack·message.new) → 새 메시지면 에이전트 실행을 백그라운드로(run_agent가 세션 Lock을 잡는다,
lock_held=False). in_progress·reporting 동안 연결이 없던 구간은 connection_gaps에 남긴다(끊김에 열고
재연결에 닫음). 진행·응답은 hub가 증분으로 보낸다. 재접속한 클라이언트는 GET /sessions/{id}/state로
따라잡는다.
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from app import scheduler
from app.auth import decode_token
from app.hub import frame
from app.models import ConnectionGap, Session
from app.services import documents
from app.services.context import AppContext, get_context
from app.services.messages import accept_candidate_message
from app.services.session import SessionError

router = APIRouter()

# 토큰이 없거나 만료(→ /s/{token}/resume으로 재발급), 다른 세션의 토큰
UNAUTHORIZED_CLOSE = 4401
FORBIDDEN_CLOSE = 4403


GAP_STATUSES = ("in_progress", "reporting")


class DocRef(BaseModel):
    doc_id: str
    version: int


class SendPayload(BaseModel):
    client_msg_id: str = Field(min_length=1)
    channel: Literal["team", "dm", "manager_dm"]
    content: str = Field(min_length=1)
    reply_to_doc: DocRef | None = None


@router.websocket("/ws/sessions/{session_id}")
async def session_socket(websocket: WebSocket, session_id: uuid.UUID, token: str = "") -> None:
    ctx = get_context(websocket)
    # 거절 사유를 close code로 알리려면 accept한 뒤 닫아야 한다(accept 전 close는 HTTP 403뿐)
    await websocket.accept()
    try:
        principal = decode_token(token)
    except HTTPException:
        await websocket.close(code=UNAUTHORIZED_CLOSE)
        return
    if principal.role != "candidate" or principal.subject != session_id:
        await websocket.close(code=FORBIDDEN_CLOSE)
        return

    await ctx.hub.connect(session_id, websocket)
    await _close_gap(ctx, session_id)
    try:
        while True:
            text = await websocket.receive_text()
            await _handle(ctx, session_id, websocket, text)
    except (WebSocketDisconnect, RuntimeError):
        # RuntimeError: session.replaced로 서버가 먼저 닫은 소켓에서 receive가 깨어난 경우
        pass
    finally:
        await ctx.hub.disconnect(session_id, websocket)
        # 교체된 연결이 닫힌 경우(새 연결이 이미 있음)는 끊김이 아니다. 연결 종료로 핸들러가
        # 취소돼도 기록은 끝나도록 shield한다
        if not ctx.hub.is_connected(session_id):
            await asyncio.shield(_open_gap(ctx, session_id))


async def _open_gap(ctx: AppContext, session_id: uuid.UUID) -> None:
    async with ctx.session_factory() as db:
        status = await db.scalar(select(Session.status).where(Session.id == session_id))
        open_gap = await db.scalar(
            select(ConnectionGap.id).where(
                ConnectionGap.session_id == session_id, ConnectionGap.reconnected_at.is_(None)
            )
        )
        if status in GAP_STATUSES and open_gap is None:
            db.add(ConnectionGap(session_id=session_id, disconnected_at=datetime.now(UTC)))
            await db.commit()


async def _close_gap(ctx: AppContext, session_id: uuid.UUID) -> None:
    async with ctx.session_factory() as db:
        gap = await db.scalar(
            select(ConnectionGap).where(
                ConnectionGap.session_id == session_id, ConnectionGap.reconnected_at.is_(None)
            )
        )
        if gap is not None:
            gap.reconnected_at = datetime.now(UTC)
            await db.commit()


async def _send_error(websocket: WebSocket, code: str, message: str) -> None:
    await websocket.send_json(frame("error", {"code": code, "message": message}))


async def _handle(ctx: AppContext, session_id: uuid.UUID, websocket: WebSocket, text: str) -> None:
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError:
        await _send_error(websocket, "invalid_input", "frame is not JSON")
        return
    if not isinstance(data, dict) or data.get("type") != "message.send":
        await _send_error(websocket, "invalid_input", "unknown frame type")
        return
    try:
        payload = SendPayload.model_validate(data.get("payload") or {})
    except ValidationError as exc:
        await _send_error(websocket, "invalid_input", str(exc.errors()[0]["msg"]))
        return

    reply = payload.reply_to_doc.model_dump() if payload.reply_to_doc else None
    try:
        async with ctx.session_factory() as db:
            if reply and not await documents.is_shared_version(
                db, session_id, reply["doc_id"], reply["version"]
            ):
                await _send_error(
                    websocket, "invalid_input", "reply_to_doc must point to a shared version"
                )
                return
            message, run_id, created = await accept_candidate_message(
                db,
                ctx.hub,
                session_id,
                payload.client_msg_id,
                payload.channel,
                payload.content,
                reply,
            )
    except SessionError as exc:  # 제출 뒤 session_ending, 진행 중이 아니면 conflict
        await _send_error(websocket, exc.code, exc.message)
        return
    if created:
        scheduler.spawn(run_id, lambda: scheduler.run_message(ctx, session_id, message.id, run_id))
