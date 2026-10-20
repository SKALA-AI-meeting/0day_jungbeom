"""P3 결함 회귀: 분류 전 진행 알림과 반올림 시각이 같은 메시지의 커서 조회."""

import asyncio
import json
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.agent.llm import FakeLLM, Usage
from app.agent.session import common, nodes
from app.agent.session.common import RunDeps, refresh_messages
from app.agent.session.graph import build_graph
from app.agent.session.state import defaults
from app.agent.session.store import DbAgentStore
from app.db import make_session_factory
from app.hub import Hub
from app.models import Message
from app.services.scenario import build_scenario

from tests.agent.brain import cls
from tests.conftest import SCENARIOS, FakeSocket


async def test_started_reaches_hub_while_classification_waits(monkeypatch):
    scenario, _ = build_scenario(SCENARIOS, ["honesty"], 120)
    sid, mid = uuid.uuid4(), uuid.uuid4()
    hub, socket = Hub(), FakeSocket()
    await hub.connect(sid, socket)
    entered, release = asyncio.Event(), asyncio.Event()

    class DelayedLLM(FakeLLM):
        async def _call(self, messages, **kwargs):
            if kwargs["json_mode"]:
                entered.set()
                await release.wait()
            return await super()._call(messages, **kwargs)

    llm = DelayedLLM([json.dumps(cls("question")), "확인했어요."])
    message = {"id": str(mid), "channel": "dm", "sender": "candidate", "content": "자료 있나요?"}
    state = {
        **defaults(str(sid)),
        "scenario": scenario,
        "phase": "work",
        "run_id": str(uuid.uuid4()),
        "stimulus": {"type": "message", "message_id": str(mid)},
        "recent_messages": [message],
    }
    saved = []

    async def prepare(deps, state):
        deps.session = {"events": []}
        return {}

    async def post(deps, state, **kwargs):
        saved.append(kwargs)
        return True

    async def progress(actor, node, status, tool):
        if status == "finished":
            assert saved  # 응답 저장이 끝난 뒤 종료 알림
        await hub.broadcast(sid, "agent.progress", {"actor": actor, "node": node, "status": status})

    scope = SimpleNamespace(
        call=AsyncMock(return_value={"ok": True, "data": {}}), specs=AsyncMock(return_value=[])
    )
    deps = RunDeps(
        llm=llm,
        mcp=SimpleNamespace(scope=lambda _: scope),
        store=SimpleNamespace(save_classification=AsyncMock()),
        usage=Usage(),
        progress=progress,
    )
    monkeypatch.setattr(nodes, "prepare", prepare)
    monkeypatch.setattr(nodes, "post", post)
    monkeypatch.setattr(nodes, "_unreleased_asked", AsyncMock(return_value=[]))
    task = asyncio.create_task(build_graph(None).ainvoke(state, context=deps))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert [f["payload"]["status"] for f in socket.frames] == ["started"]
    finally:
        release.set()
        await task
    statuses = [f["payload"]["status"] for f in socket.frames]
    assert statuses.count("started") == statuses.count("finished") == 1
    assert statuses[-1] == "finished"


async def test_refresh_reads_dm_after_fifty_assistant_messages(
    started_session, db, engine, monkeypatch
):
    session = await started_session(["honesty"])
    stamp = session.started_at + timedelta(minutes=1)
    messages = [
        Message(
            id=uuid.UUID(int=i + 1),
            session_id=session.id,
            channel="assistant",
            sender="candidate",
            content="질문",
            created_at=stamp,
        )
        for i in range(50)
    ]
    target = Message(
        id=uuid.UUID(int=51),
        session_id=session.id,
        channel="dm",
        sender="candidate",
        content="도현님 자료 있나요?",
        created_at=stamp,
    )
    db.add_all([*messages, target])
    await db.commit()
    store = DbAgentStore(make_session_factory(engine))
    recent, error = await refresh_messages(store, session.id, [])
    assert error is None
    assert recent[-1]["id"] == str(target.id)
    # 기존 체크포인트(created_at 없음)는 처음부터 읽고, 새 커서는 같은 행을 중복하지 않는다.
    legacy = [{k: v for k, v in recent[-1].items() if k != "created_at"}]
    assert (await refresh_messages(store, session.id, legacy))[0][-1]["id"] == str(target.id)
    assert await refresh_messages(store, session.id, recent) == (recent, None)
    monkeypatch.setattr(common, "MAX_PAGES", 1)
    _, error = await refresh_messages(store, session.id, [])
    assert error == "page_limit_exceeded"
