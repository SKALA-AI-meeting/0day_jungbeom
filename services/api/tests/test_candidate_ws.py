"""완료 기준: WS(ack·증분·재연결 후 /state), reply_to_doc 검증, completed 뒤 session_ending,
reporting 재접속(최소 테스트 ⑥ WS 쪽: 끊김 구간 기록, 보고 대기 중 팀장 DM 보고로 completed).

앱은 TestClient의 별도 스레드 루프에서 돈다. asyncpg 연결은 루프에 묶이므로 앱 쪽 엔진은 NullPool로
따로 만들고, 테스트 쪽 조회는 conftest의 db(테스트 루프)로 한다.
"""

import asyncio

import pytest
from app.agent.runner import FAKE_REPLY, FakeAgentRunner
from app.auth import session_token
from app.config import get_settings
from app.db import make_session_factory
from app.hub import Hub
from app.main import create_public_app
from app.models import ConnectionGap, Message, SessionEvent
from app.services.context import AppContext
from app.services.locks import SessionLocks
from app.services.messages import save_internal_message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.contract import load_contract


@pytest.fixture
async def client(database_url, publisher, db):
    """db에 의존해 앱(백그라운드 실행 포함)을 먼저 닫은 뒤 db 정리(TRUNCATE)가 돌게 한다."""
    engine = create_async_engine(database_url, poolclass=NullPool)
    factory = make_session_factory(engine)
    hub = Hub()

    async def post_message(**kwargs):
        async with factory() as db:
            message, _ = await save_internal_message(db, hub, **kwargs)
            return message

    ctx = AppContext(
        settings=get_settings(),
        engine=engine,
        session_factory=factory,
        hub=hub,
        locks=SessionLocks(),
        publisher=publisher,
        runner=FakeAgentRunner(post_message, hub.broadcast),
    )
    with TestClient(create_public_app(ctx)) as test_client:
        yield test_client
    await engine.dispose()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _open_gap(db, session_id):
    for _ in range(40):
        gap = await db.scalar(
            select(ConnectionGap)
            .where(ConnectionGap.session_id == session_id)
            .execution_options(populate_existing=True)
        )
        if gap is not None:
            return gap
        await asyncio.sleep(0.05)
    return None


def send(client_msg_id: str, content: str, channel: str = "team", **extra) -> dict:
    payload = {"client_msg_id": client_msg_id, "channel": channel, "content": content, **extra}
    return {"type": "message.send", "payload": payload}


async def test_ws_ack_increment_and_reconnect(client, started_session):
    session = await started_session(["collaboration"])
    token = session_token(session.id, 120)
    url = f"/ws/sessions/{session.id}?token={token}"
    first_frame = load_contract("ws_client_frames")[0]

    with client.websocket_connect(url) as first:
        first.send_json(first_frame)
        frames = [first.receive_json() for _ in range(5)]
        assert [f["type"] for f in frames] == [
            "message.ack",
            "message.new",
            "agent.progress",
            "message.new",
            "agent.progress",
        ]
        ack = frames[0]["payload"]
        assert ack["client_msg_id"] == "c-1" and frames[1]["payload"]["id"] == ack["message_id"]
        reply = frames[3]["payload"]
        assert (reply["sender"], reply["content"], reply["run_id"]) == (
            "colleague",
            FAKE_REPLY,
            ack["run_id"],
        )
        first.send_json(first_frame)  # 같은 client_msg_id 재전송은 기존 메시지로 ack만
        assert first.receive_json() == {"type": "message.ack", "payload": ack}

        # 보낸 버전이 아닌 문서에 매단 답글은 invalid_input
        bad = send("c-x", "답글", reply_to_doc={"doc_id": "not-a-doc", "version": 1})
        first.send_json(bad)
        assert first.receive_json() == load_contract("ws_error")

        with client.websocket_connect(url) as second:
            assert first.receive_json() == load_contract("ws_session_replaced")
            with pytest.raises(WebSocketDisconnect) as closed:
                first.receive_json()
            assert closed.value.code == 4000

            state = client.get(f"/sessions/{session.id}/state", headers=bearer(token)).json()
            assert [(m["sender"], m["content"]) for m in state["messages"]] == [
                ("candidate", first_frame["payload"]["content"]),
                ("colleague", FAKE_REPLY),
            ]
            second.send_json(send("c-2", "팀장님께 여쭤볼게요", channel="manager_dm"))
            assert [second.receive_json()["type"] for _ in range(5)][0] == "message.ack"


async def test_reporting_reconnect_over_ws(client, db, service, started_session):
    """제출 → reporting 중 WS 끊김(구간 기록) → resume·재연결(구간 닫힘) → 팀장 DM 메시지는 받는다 →
    보고 분류(kind=report)로 completed → 이후 message.send는 session_ending."""
    session = await started_session(["honesty"])
    # 이 db 세션에 카드 객체(fired_at 없음)를 붙잡아 둔다. 앱이 다른 연결에서 실행한 뒤에도
    # mark_reported가 옛 값을 읽지 않아야 한다(관문 3 리뷰 B2의 간헐 실패 원인)
    held = (
        (await db.execute(select(SessionEvent).where(SessionEvent.session_id == session.id)))
        .scalars()
        .all()
    )
    token = session_token(session.id, 120)
    with client.websocket_connect(f"/ws/sessions/{session.id}?token={token}"):
        res = client.post(f"/sessions/{session.id}/submit", headers=bearer(token))
        assert res.json()["status"] == "reporting", res.text
    gap = await _open_gap(db, session.id)  # 끊김 처리는 앱 스레드에서 비동기로 끝난다
    assert gap is not None and gap.reconnected_at is None
    with client.websocket_connect(f"/ws/sessions/{session.id}?token={token}") as ws:
        state = client.get(f"/sessions/{session.id}/state", headers=bearer(token)).json()
        assert state["session"]["status"] == "reporting" and state["session"]["deadline_at"]
        assert state["connection_gaps"][0]["to_t_min"] is not None
        ws.send_json(send("c-r", "4·5번은 도현님이 썼고 1~3번은 아직이에요.", channel="manager_dm"))
        assert ws.receive_json()["type"] == "message.ack"
        report = await db.scalar(
            select(Message).where(Message.session_id == session.id, Message.client_msg_id == "c-r")
        )
        meta = {**report.meta, "classification": {"recipient": "manager", "kind": "report"}}
        report.meta = meta
        await db.commit()
        if not await service.mark_reported(session.id, report.created_at):
            # 간헐 실패 추적(관문 3 리뷰 B2): 요청 카드 시각·보고 메시지 시각·세션 상태를 남긴다
            request = await db.scalar(
                select(SessionEvent).where(
                    SessionEvent.session_id == session.id, SessionEvent.or_on_submit.is_(True)
                )
            )
            now = await service.get(session.id)
            pytest.fail(
                f"mark_reported False: fired_at={request and request.fired_at} "
                f"request_status={request and request.status} created_at={report.created_at} "
                f"status={now.status} reported_at={now.reported_at}"
            )
        await service.complete(session.id)
        ws.send_json(send("c-z", "끝났나요?"))
        frame = ws.receive_json()
        while frame["type"] != "error":  # 앞선 메시지의 응답·진행 프레임을 건너뛴다
            frame = ws.receive_json()
        assert frame["payload"]["code"] == "session_ending"
    assert held  # 끝까지 참조를 유지한다
    ended = await service.get(session.id)
    assert ended.status == "completed" and ended.completed_at == report.created_at
