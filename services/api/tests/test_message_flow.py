"""완료 기준: FakeAgentRunner로 메시지 → 내부 저장 → hub 브로드캐스트."""

from app.agent.runner import FAKE_REPLY, Stimulus
from app.masking import PHONE_MASK
from app.models import AgentRun, Message
from app.services.messages import accept_candidate_message
from app.services.runs import run_agent
from sqlalchemy import select

from tests.conftest import FakeSocket


async def test_candidate_message_runs_agent_and_broadcasts(
    db, service, make_position, hub, runner, locks
):
    position = await make_position(["collaboration"])
    session, _, _ = await service.create_for_invite(position.id, "A", "a@example.com")
    await service.consent(session.id)
    await service.start(session.id)
    ws = FakeSocket()
    await hub.connect(session.id, ws)

    message, run_id, created = await accept_candidate_message(
        db, hub, session.id, "c-1", "team", "제 번호는 010-1234-5678이에요"
    )
    assert created and message.content == f"제 번호는 {PHONE_MASK}이에요"
    await run_agent(db, runner, locks, session.id, Stimulus("message", message.id), run_id)

    rows = (
        (
            await db.execute(
                select(Message).where(Message.session_id == session.id).order_by(Message.created_at)
            )
        )
        .scalars()
        .all()
    )
    assert [(m.sender, m.run_id) for m in rows] == [("candidate", None), ("colleague", run_id)]
    assert rows[1].content == FAKE_REPLY
    run = await db.get(AgentRun, run_id, populate_existing=True)
    assert (run.status, run.ref_ids) == ("finished", [message.id])

    assert ws.types() == [
        "message.ack",
        "message.new",
        "agent.progress",
        "message.new",
        "agent.progress",
    ]
    assert ws.frames[0]["payload"] == {
        "client_msg_id": "c-1",
        "message_id": str(message.id),
        "run_id": str(run_id),
    }
    assert ws.frames[3]["payload"]["content"] == FAKE_REPLY
    assert ws.frames[3]["payload"]["run_id"] == str(run_id)

    # 같은 client_msg_id 재전송: 저장·실행 없이 기존 메시지로 ack만
    again, again_run, created = await accept_candidate_message(
        db, hub, session.id, "c-1", "team", "제 번호는 010-1234-5678이에요"
    )
    assert (again.id, again_run, created) == (message.id, run_id, False)
    assert ws.types()[-1] == "message.ack"
