"""WS 거부는 accept 뒤 close 코드로 보낸다(4401 토큰 문제, 4403 다른 세션)."""

import uuid
from types import SimpleNamespace

import pytest
from app.auth import session_token
from app.config import get_settings
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
