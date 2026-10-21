"""WS 거부는 accept 뒤 close 코드로 보낸다(4401 토큰 문제, 4403 다른 세션)."""

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.auth import session_token
from app.config import get_settings
from app.hub import Hub
from app.main import create_public_app
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.mark.parametrize("other_session", [False, True])
def test_rejected_socket_gets_close_code_after_accept(other_session):
    app = create_public_app(SimpleNamespace(settings=get_settings()))
    sid = uuid.uuid4()
    token = session_token(uuid.uuid4(), 15) if other_session else "bad-token"
    with (
        TestClient(app) as client,
        client.websocket_connect(f"/ws/sessions/{sid}?token={token}") as ws,
    ):
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == (4403 if other_session else 4401)


class _Socket:
    """send_json이 stuck이면 영원히 멈추는 가짜 소켓."""

    def __init__(self, stuck: bool = False):
        self.stuck, self.got, self.closed = stuck, [], None

    async def send_json(self, data):
        if self.stuck:
            await asyncio.Event().wait()
        self.got.append(data)

    async def close(self, code: int = 1000):
        self.closed = code


async def _settle():
    for _ in range(5):
        await asyncio.sleep(0)


async def test_replacing_stuck_socket_lets_new_socket_receive_frames():
    hub = Hub(lambda: datetime.now(UTC))
    hub.send_timeout = 0.05
    sid = uuid.uuid4()
    old, new = _Socket(stuck=True), _Socket()
    await hub.connect(sid, old)
    hub.enqueue(sid, "message.new", {"n": 1})  # 옛 소켓 writer가 멈춤
    await _settle()
    await asyncio.wait_for(hub.connect(sid, new), 1)
    hub.enqueue(sid, "message.new", {"n": 2})
    await asyncio.sleep(0.01)
    assert [f["payload"] for f in new.got] == [{"n": 2}]  # 옛 연결로 가던 프레임은 버림
    assert all(ws is new for ws, _ in hub._outbox.get(sid, ()))


async def test_disconnect_and_send_timeout_clear_writer_queue_and_socket():
    hub = Hub(lambda: datetime.now(UTC))
    hub.send_timeout = 0.05
    sid = uuid.uuid4()
    ws = _Socket(stuck=True)
    await hub.connect(sid, ws)
    hub.enqueue(sid, "a", {})
    hub.enqueue(sid, "b", {})
    await _settle()
    assert hub.disconnect(sid, ws)
    await _settle()
    assert sid not in hub._outbox and sid not in hub._writers and not hub.is_connected(sid)

    stuck = _Socket(stuck=True)
    await hub.connect(sid, stuck)
    hub.enqueue(sid, "c", {})
    await asyncio.sleep(0.2)  # 전송 타임아웃 → 끊고 정리
    assert not hub.is_connected(sid) and stuck.closed == 1011  # 클라이언트는 재연결
    assert sid not in hub._outbox and sid not in hub._writers
