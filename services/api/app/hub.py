"""세션별 WebSocket 연결과 브로드캐스트. 한 프로세스(api) 안에서만 유효하다.

프레임 형식: {"type": <이벤트 이름>, "payload": {...}}. 이벤트 이름은 contracts.md의 WebSocket 표.
같은 세션에 새 연결이 붙으면 이전 연결은 session.replaced를 받고 닫힌다.
"""

import asyncio
import logging
import uuid
from typing import Any, Protocol

log = logging.getLogger(__name__)

REPLACED_CLOSE_CODE = 4000


class SocketLike(Protocol):
    async def send_json(self, data: Any) -> None: ...
    async def close(self, code: int = 1000) -> None: ...


def frame(type_: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"type": type_, "payload": payload or {}}


class Hub:
    def __init__(self) -> None:
        self._sockets: dict[uuid.UUID, SocketLike] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: uuid.UUID, ws: SocketLike) -> None:
        async with self._lock:
            previous = self._sockets.get(session_id)
            self._sockets[session_id] = ws
        if previous is not None and previous is not ws:
            try:
                await previous.send_json(frame("session.replaced"))
                await previous.close(code=REPLACED_CLOSE_CODE)
            except Exception:  # 이미 끊긴 연결
                log.debug("previous socket already closed", exc_info=True)

    async def disconnect(self, session_id: uuid.UUID, ws: SocketLike) -> None:
        async with self._lock:
            if self._sockets.get(session_id) is ws:
                del self._sockets[session_id]

    def is_connected(self, session_id: uuid.UUID) -> bool:
        return session_id in self._sockets

    async def broadcast(self, session_id: uuid.UUID, type_: str, payload: dict[str, Any]) -> None:
        """연결이 없으면 버린다. 재접속한 클라이언트는 /state 스냅샷으로 따라잡는다."""
        ws = self._sockets.get(session_id)
        if ws is None:
            return
        try:
            await ws.send_json(frame(type_, payload))
        except Exception:
            log.info("drop socket for session %s", session_id, exc_info=True)
            await self.disconnect(session_id, ws)
