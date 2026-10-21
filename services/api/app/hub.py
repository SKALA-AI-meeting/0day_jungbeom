"""세션별 WebSocket 연결, 단일 송신 큐(seq 부여), typing 상태. 한 프로세스(api) 안에서만 유효하다.

프레임 봉투: {"type", "seq", "payload"} (contracts.md "WebSocket"). 모든 서버 프레임은 send()의
세션별
FIFO 잠금 하나를 지나며 seq를 1씩 붙인다. 연결이 없어도 seq는 오르고 프레임은 버려진다(재연결한
클라이언트는 /state의 ws_seq부터 이어 간다). 다른 경로에서 소켓에 직접 쓰지 않는다.
typing: 지원자는 5초마다 start를 갱신하고 6초 동안 갱신이 없으면 만료(R5-9). 페르소나 typing은
SessionPorts.send_typing이 여기로 보낸다.
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Protocol

log = logging.getLogger(__name__)

REPLACED_CLOSE_CODE = 4000
CANDIDATE_TYPING_TTL = timedelta(seconds=6)


class SocketLike(Protocol):
    async def send_json(self, data: Any) -> None: ...
    async def close(self, code: int = 1000) -> None: ...


class Hub:
    def __init__(self, now: Callable[[], datetime], record: bool = False) -> None:
        self._now = now
        self._sockets: dict[uuid.UUID, SocketLike] = {}
        self._locks: dict[uuid.UUID, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._seq: dict[uuid.UUID, int] = defaultdict(int)
        self._candidate_typing_until: dict[uuid.UUID, datetime] = {}
        self._persona_typing: dict[uuid.UUID, set[str]] = defaultdict(set)
        # 테스트용: 세션별 보낸 프레임 전부
        self.record = record
        self.sent: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)

    # ---- 연결 -------------------------------------------------------------------------------

    async def connect(self, session_id: uuid.UUID, ws: SocketLike) -> None:
        previous = self._sockets.get(session_id)
        self._sockets[session_id] = ws
        if previous is not None and previous is not ws:
            try:
                await previous.send_json({"type": "session.replaced", "seq": 0, "payload": {}})
                await previous.close(code=REPLACED_CLOSE_CODE)
            except Exception:
                log.debug("previous socket already closed", exc_info=True)

    def disconnect(self, session_id: uuid.UUID, ws: SocketLike) -> bool:
        if self._sockets.get(session_id) is ws:
            del self._sockets[session_id]
            return True
        return False

    def is_connected(self, session_id: uuid.UUID) -> bool:
        return session_id in self._sockets

    # ---- 송신 -------------------------------------------------------------------------------

    def last_seq(self, session_id: uuid.UUID) -> int:
        return self._seq[session_id]

    async def send(self, session_id: uuid.UUID, type_: str, payload: dict[str, Any]) -> int:
        async with self._locks[session_id]:
            self._seq[session_id] += 1
            frame = {"type": type_, "seq": self._seq[session_id], "payload": payload}
            if self.record:
                self.sent[session_id].append(frame)
            ws = self._sockets.get(session_id)
            if ws is not None:
                try:
                    await ws.send_json(frame)
                except Exception:
                    log.info("drop socket for session %s", session_id, exc_info=True)
                    self.disconnect(session_id, ws)
            return frame["seq"]

    async def send_many(self, session_id: uuid.UUID, events: list[tuple[str, dict]]) -> None:
        for type_, payload in events:
            await self.send(session_id, type_, payload)

    # ---- typing -----------------------------------------------------------------------------

    def candidate_typing(self, session_id: uuid.UUID, state: str) -> None:
        if state == "start":
            self._candidate_typing_until[session_id] = self._now() + CANDIDATE_TYPING_TTL
        else:
            self._candidate_typing_until.pop(session_id, None)

    def is_candidate_typing(self, session_id: uuid.UUID) -> bool:
        until = self._candidate_typing_until.get(session_id)
        return until is not None and self._now() < until

    async def persona_typing(self, session_id: uuid.UUID, seat: str, state: str) -> None:
        if state == "start":
            self._persona_typing[session_id].add(seat)
        else:
            self._persona_typing[session_id].discard(seat)
        await self.send(session_id, "typing", {"participant": seat, "state": state})

    def typing_seats(self, session_id: uuid.UUID) -> list[str]:
        return sorted(self._persona_typing[session_id])
