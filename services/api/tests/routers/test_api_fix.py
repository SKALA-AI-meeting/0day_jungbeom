"""완료 기준(api-fix): 어시스턴트 요청 마스킹 저장, 동시 요청의 60회 한도 직렬화, run.py의
어시스턴트 러너 warm-up·aclose, 내부 테스트 세션의 회사 지정.
"""

import asyncio
import types
import uuid
from dataclasses import replace

from app import run
from app.agent.runner import AssistantResult
from app.models import AssistantCall, Invite, Message, Position, Session
from app.routers import candidate
from sqlalchemy import func, select

from tests.routers.test_candidate import enter


class RecordingAssistant:
    """받은 prompt를 모으는 가짜 어시스턴트. 응답 전에 잠깐 쉬어 동시 요청이 겹치게 한다."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def answer(self, session_id, prompt, call_id) -> AssistantResult:
        self.prompts.append(prompt)
        await asyncio.sleep(0.05)
        return AssistantResult(content="답", cited_docs=[])


async def test_assistant_prompt_is_masked_before_save(api, db, ctx, new_position, invite):
    ctx.assistant = RecordingAssistant()
    _, sid, _, auth = await enter(api, new_position, invite)
    prompt = "a@b.com 010-1234-5678 로 연락"
    res = await api.post(f"/sessions/{sid}/assistant", json={"prompt": prompt}, headers=auth)
    assert res.status_code == 200, res.text
    stored = await db.scalar(
        select(Message.content).where(Message.session_id == sid, Message.sender == "candidate")
    )
    assert stored == "[이메일] [전화번호] 로 연락"
    assert ctx.assistant.prompts == [stored]


async def test_concurrent_assistant_requests_respect_limit(
    api, db, ctx, new_position, invite, monkeypatch
):
    ctx.assistant = RecordingAssistant()
    monkeypatch.setattr(candidate, "ASSISTANT_LIMIT", 1)
    writable = candidate._writable

    async def slow_writable(db, session_id):
        # 두 요청이 모두 상태 확인을 통과한 뒤 카운트하게 해 경쟁 구간을 넓힌다
        result = await writable(db, session_id)
        await asyncio.sleep(0.05)
        return result

    monkeypatch.setattr(candidate, "_writable", slow_writable)
    _, sid, _, auth = await enter(api, new_position, invite)
    results = await asyncio.gather(
        *(
            api.post(f"/sessions/{sid}/assistant", json={"prompt": f"질문{i}"}, headers=auth)
            for i in range(2)
        )
    )
    assert sorted(r.status_code for r in results) == [200, 429]
    used = await db.scalar(
        select(func.count()).select_from(AssistantCall).where(AssistantCall.session_id == sid)
    )
    assert used == 1


async def test_run_warms_up_and_closes_assistant(monkeypatch):
    """warm-up·aclose 실패가 기동과 나머지 정리를 막지 않는다."""
    calls: list[str] = []

    class Runner:
        async def graph(self):
            calls.append("assistant.graph")

        async def aclose(self):
            calls.append("assistant.aclose")

    class BrokenRunner:
        async def graph(self):
            calls.append("session.graph")
            raise RuntimeError("db down")

        async def aclose(self):
            calls.append("session.aclose")
            raise RuntimeError("pool")

    async def noop(*_args, **_kwargs):
        return None

    async def serve(self):
        calls.append("serve")

    async def dispose():
        calls.append("engine.dispose")

    settings = types.SimpleNamespace(public_port=0, internal_port=0)
    ctx = types.SimpleNamespace(
        settings=settings,
        runner=BrokenRunner(),
        assistant=Runner(),
        publisher=types.SimpleNamespace(close=noop),
        engine=types.SimpleNamespace(dispose=dispose),
    )
    monkeypatch.setattr(run, "build_context", lambda: ctx)
    monkeypatch.setattr(run, "create_public_app", lambda _ctx: None)
    monkeypatch.setattr(run, "create_internal_app", lambda _ctx: None)
    monkeypatch.setattr(run.scheduler, "run", noop)
    monkeypatch.setattr(run.uvicorn.Server, "serve", serve)
    await run.serve()
    assert calls == [
        "session.graph",
        "assistant.graph",
        "serve",
        "serve",
        "session.aclose",
        "assistant.aclose",
        "engine.dispose",
    ]


async def test_test_session_uses_given_company(internal, db, ctx, signup):
    await signup("owner@example.com", "지정 회사")
    from app.models import Admin

    company_id = await db.scalar(select(Admin.company_id).where(Admin.email == "owner@example.com"))
    ctx.settings = replace(ctx.settings, enable_test_api=True)
    body = {"elements": ["planning"], "session_minutes": 6}
    for extra in ({"company_id": str(company_id)}, {"admin_email": "owner@example.com"}):
        res = await internal.post("/internal/test/sessions", json={**body, **extra})
        assert res.status_code == 200, res.text
        owner = await db.scalar(
            select(Position.company_id)
            .join(Invite, Invite.position_id == Position.id)
            .join(Session, Session.invite_id == Invite.id)
            .where(Session.id == uuid.UUID(res.json()["session_id"]))
        )
        assert owner == company_id
    missing = await internal.post(
        "/internal/test/sessions", json={**body, "admin_email": "none@example.com"}
    )
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "not_found")
    empty = await internal.post("/internal/test/sessions", json={**body, "admin_email": ""})
    assert empty.status_code == 422
