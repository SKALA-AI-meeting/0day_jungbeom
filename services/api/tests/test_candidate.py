"""완료 기준: 지원자 엔드포인트, WS(ack·증분·재연결 후 /state),
submitted_at 이후 PUT 409 session_ending.

앱은 TestClient의 별도 스레드 루프에서 돈다. asyncpg 연결은 루프에 묶이므로 앱 쪽 엔진은 NullPool로
따로 만들고, 테스트 쪽 조회는 conftest의 db(테스트 루프)로 한다.
"""

import json
from datetime import timedelta

import jwt
import pytest
from app.agent.runner import FAKE_REPLY, FakeAgentRunner
from app.auth import session_token
from app.config import REPO_ROOT, get_settings
from app.db import make_session_factory
from app.hub import Hub
from app.main import create_public_app
from app.models import (
    AssistantCall,
    AssistantReuse,
    DocView,
    Message,
    Session,
    SessionEvent,
    Task,
)
from app.queue import GENERATE
from app.services.context import AppContext
from app.services.locks import SessionLocks
from app.services.messages import save_internal_message
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

ALL_FOUR = ["cooperation", "responsibility", "flexibility", "respect"]
STATE_FIXTURE = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "contracts" / "state.json").read_text(encoding="utf-8")
)


@pytest.fixture
async def client(database_url, publisher):
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


async def started_session(service, make_position, elements=("cooperation",)):
    position = await make_position(list(elements))
    session, _, _ = await service.create_for_invite(position.id, "A", "a@example.com")
    await service.consent(session.id)
    session = await service.start(session.id)
    return session, session_token(session.id, position.session_minutes)


async def test_candidate_endpoints(client, db, service, make_position, publisher):
    position = await make_position(ALL_FOUR)
    session, _, raw = await service.create_for_invite(position.id, "지원자A", "a@example.com")
    sid = session.id

    entry = client.get(f"/s/{raw}").json()
    assert entry["company_name"] == "테스트 회사" and entry["duration_minutes"] == 120
    assert entry["status"] == "invited" and "debrief_token" not in entry
    assert entry["elements_names"] == ["협력 태도", "책임감", "유연성", "존중·소통"]
    assert "2시간" in entry["entry_notice"] and "루프랩" in entry["entry_notice"]

    token = client.post(f"/s/{raw}/consent").json()["session_token"]
    started = client.post(f"/s/{raw}/start", headers=bearer(token)).json()
    assert started["session_id"] == str(sid) and started["ends_at"]
    assert client.post(f"/s/{raw}/start", headers=bearer(token)).json() == started  # 멱등
    token = client.post(f"/s/{raw}/resume").json()["session_token"]  # 링크만으로 재발급
    auth = bearer(token)

    other, _ = await started_session(service, make_position)
    other_token = session_token(other.id, 120)
    assert client.get(f"/sessions/{sid}/state", headers=bearer(other_token)).status_code == 403

    # 분업 확정(내부 division PUT이 하는 일)을 흉내 낸다: division과 tasks 행
    parts = {str(no): who for no, who in position.scenario["default_division"].items()}
    stored = await db.get(Session, sid, populate_existing=True)
    stored.division = {"parts": parts, "decided_by": "candidate"}
    db.add_all(Task(session_id=sid, part_no=int(no), assignee=who) for no, who in parts.items())
    await db.commit()

    docs = client.get(f"/sessions/{sid}/documents", headers=auth).json()
    assert {d["doc_id"]: d["released"] for d in docs}["interview_summary"] is False
    locked = client.get(f"/sessions/{sid}/documents/interview_summary", headers=auth)
    assert (locked.status_code, locked.json()["error"]["code"]) == (423, "not_released")
    metrics = client.get(f"/sessions/{sid}/documents/metrics", headers=auth).json()
    assert metrics["title"] == "지표 현황" and "22%" in metrics["content"]
    views = (await db.execute(select(DocView.doc_id).where(DocView.session_id == sid))).scalars()
    assert list(views) == ["metrics"]

    assert client.put(
        f"/sessions/{sid}/tasks/1", json={"status": "doing"}, headers=auth
    ).json() == {
        "part_no": 1,
        "assignee": "candidate",
        "status": "doing",
    }
    colleague_task = client.put(f"/sessions/{sid}/tasks/4", json={"status": "done"}, headers=auth)
    assert colleague_task.status_code == 403
    colleague_part = client.put(f"/sessions/{sid}/document/4", json={"content": "x"}, headers=auth)
    assert (colleague_part.status_code, colleague_part.json()["error"]["code"]) == (
        403,
        "forbidden",
    )

    put = client.put(f"/sessions/{sid}/document/1", json={"content": "초안"}, headers=auth)
    assert put.json()["revision"] == 1
    body = {"content": "휴면 참여자 대상 초안"}
    assert (
        client.put(f"/sessions/{sid}/document/1", json=body, headers=auth).json()["revision"] == 2
    )
    assert (
        client.put(f"/sessions/{sid}/document/1", json=body, headers=auth).json()["revision"] == 2
    )

    state = client.get(f"/sessions/{sid}/state", headers=auth).json()
    assert state.keys() == STATE_FIXTURE.keys()
    assert state["session"].keys() == STATE_FIXTURE["session"].keys()
    assert state["session"]["status"] == "in_progress"
    assert 7100 < state["session"]["remaining_seconds"] <= 7200
    assert state["document"]["1"] == {
        "content": "휴면 참여자 대상 초안",
        "revision": 2,
        "updated_by": "candidate",
    }
    assert state["document"]["2"] == {"content": "", "revision": 0, "updated_by": None}
    assert state["tasks"][0] == {"part_no": 1, "assignee": "candidate", "status": "doing"}
    assert state["persona"] == STATE_FIXTURE["persona"]
    assert (state["messages"], state["assistant"], state["active_runs"]) == ([], [], [])

    # 디브리핑은 실제 실행된(done) 요소 카드만 보여 준다
    await db.execute(
        update(SessionEvent)
        .where(SessionEvent.session_id == sid, SessionEvent.card_id == "cooperation")
        .values(status="done")
    )
    await db.commit()
    assert client.post(f"/sessions/{sid}/submit", headers=auth).json() == {"status": "completed"}
    assert client.post(f"/sessions/{sid}/submit", headers=auth).json() == {"status": "completed"}
    assert publisher.published == [(GENERATE, {"session_id": str(sid), "attempt": 1})]

    ended = client.get(f"/s/{raw}").json()
    assert ended["status"] == "completed" and ended["debrief_token"]
    # 디브리핑 기한은 발급 시각이 아니라 종료 시각 + 7일로 고정
    submitted_at = (await db.get(Session, sid, populate_existing=True)).submitted_at
    claims = jwt.decode(ended["debrief_token"], options={"verify_signature": False})
    assert claims["exp"] == int((submitted_at + timedelta(days=7)).timestamp())
    debrief = client.get(f"/sessions/{sid}/debrief", headers=bearer(ended["debrief_token"])).json()
    assert [e["element"] for e in debrief["events"]] == ["cooperation"]
    assert len(debrief["events"][0]["rubric_items"]) == 4
    assert "이도현" in debrief["persona_note"] and "채용 담당자" in debrief["scoring_notice"]


async def test_ws_ack_increment_and_reconnect(client, service, make_position):
    session, token = await started_session(service, make_position)
    url = f"/ws/sessions/{session.id}?token={token}"
    send = {
        "type": "message.send",
        "payload": {"client_msg_id": "c-1", "channel": "team", "content": "파트는 제가 나눌게요"},
    }

    with client.websocket_connect(url) as first:
        first.send_json(send)
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
        assert frames[4]["payload"]["status"] == "finished"

        first.send_json(send)  # 같은 client_msg_id 재전송은 기존 메시지로 ack만
        assert first.receive_json() == {"type": "message.ack", "payload": ack}

        with client.websocket_connect(url) as second:
            assert first.receive_json() == {"type": "session.replaced", "payload": {}}
            with pytest.raises(WebSocketDisconnect) as closed:
                first.receive_json()
            assert closed.value.code == 4000

            state = client.get(f"/sessions/{session.id}/state", headers=bearer(token)).json()
            assert [(m["sender"], m["content"]) for m in state["messages"]] == [
                ("candidate", "파트는 제가 나눌게요"),
                ("colleague", FAKE_REPLY),
            ]
            assert state["active_runs"] == []

            # 재연결한 소켓이 이후 증분을 받는다
            send["payload"] = {**send["payload"], "client_msg_id": "c-2"}
            second.send_json(send)
            assert [second.receive_json()["type"] for _ in range(5)][0] == "message.ack"

            # 제출 뒤 message.send는 session_ending 오류 프레임
            client.post(f"/sessions/{session.id}/submit", headers=bearer(token))
            assert second.receive_json()["type"] == "session.ended"
            send["payload"] = {**send["payload"], "client_msg_id": "c-3"}
            second.send_json(send)
            assert second.receive_json()["payload"]["code"] == "session_ending"


async def test_document_put_after_submit_is_session_ending(client, db, service, make_position):
    session, token = await started_session(service, make_position)
    auth = bearer(token)
    answer = (
        "재참여율을 높이려면 첫 모임 직후에 다음 모임 일정을 바로 잡아 주는 기능이 필요합니다. "
        "참여자의 절반이 다음 일정을 몰라서 다시 오지 않습니다."
    )
    request = Message(session_id=session.id, channel="assistant", sender="candidate", content="?")
    response = Message(
        session_id=session.id, channel="assistant", sender="assistant", content=answer
    )
    db.add_all([request, response])
    await db.flush()
    call = AssistantCall(
        session_id=session.id, request_message_id=request.id, response_message_id=response.id
    )
    db.add(call)
    await db.commit()

    pasted = client.put(
        f"/sessions/{session.id}/document/1", json={"content": answer}, headers=auth
    )
    assert pasted.status_code == 200
    assert client.post(f"/sessions/{session.id}/submit", headers=auth).status_code == 200

    late = client.put(f"/sessions/{session.id}/document/1", json={"content": "x"}, headers=auth)
    assert (late.status_code, late.json()["error"]["code"]) == (409, "session_ending")

    # 제출 처리(complete)가 reuse 훅으로 반영 추정을 남겼다
    reuse = (await db.execute(select(AssistantReuse))).scalars().all()
    assert [(r.call_id, r.part_no, r.reuse, r.ratio) for r in reuse] == [
        (call.id, 1, "verbatim", 1.0)
    ]
