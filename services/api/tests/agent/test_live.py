"""실제 gpt-4o-mini 확인(`make test-live`). 미공개 문서 질문(g05), 그리고 모델 상향 판단 자료로
선점 금지·팀장 DM 규칙, 관찰 레이블 7장, 대본 all_five 전체를 실제 모델로 돌려 결과를 출력한다.

MCP 서버·api 앱은 연결 테스트와 같은 구성이다. LangSmith 트레이싱은 infra/.env 설정을 따르고,
trace에는 run_id 태그가 붙는다.
"""

import json
import re

import pytest
from app.agent import observe
from app.agent.llm import OpenAILLM, Trace, Usage
from app.agent.runner import Stimulus
from app.config import get_settings
from app.models import AgentRun, Message, Observation, Session, SessionEvent
from app.services.messages import accept_candidate_message
from app.services.runs import run_agent
from sqlalchemy import select

from tests.agent.script_driver import start
from tests.agent.test_context_rules import ALL_FIVE
from tests.agent.test_session_flow import G05, INTERVIEW_LINE, persona_messages, start_session


@pytest.mark.live
async def test_live_unreleased_document_question(stack, service, make_position, db):
    settings = get_settings()
    assert settings.openai_api_key, "OPENAI_API_KEY가 infra/.env에 필요하다"
    stack.use_llm(OpenAILLM(settings.openai_api_key, settings.openai_model))
    session_id = await start_session(service, make_position, ("responsibility",))
    async with stack.ctx.session_factory() as session_db:
        message, run_id, _ = await accept_candidate_message(
            session_db, stack.hub, session_id, "c-1", "dm", G05["question"]
        )
        message_id = message.id

    # 첫 그래프 초기화의 인덱스 생성 전에 메시지 조회 트랜잭션을 닫는다.
    async with stack.ctx.session_factory() as session_db:
        result = await run_agent(
            session_db,
            stack.runner,
            stack.ctx.locks,
            session_id,
            Stimulus("message", message_id),
            run_id,
        )

    [answer] = await persona_messages(db, session_id)
    print(f"\nrun_id={run_id} usage={result.usage}\nanswer={answer.content}")
    assert result.ok and not result.fallback_used
    assert answer.meta["model"] == "gpt-4o-mini"
    assert INTERVIEW_LINE not in answer.content
    assert re.search(G05["expected_fact"], answer.content)


# ───────────── 모델 상향 판단 자료(통과를 요구하지 않고 결과를 출력한다) ─────────────

LIVE_RESULTS: dict = {}


def real_llm():
    settings = get_settings()
    assert settings.openai_api_key, "OPENAI_API_KEY가 infra/.env.local에 필요하다"
    return OpenAILLM(settings.openai_api_key, settings.openai_model)


def report(name, rows):
    LIVE_RESULTS[name] = rows
    print(f"\n### {name}")
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))


@pytest.mark.live
async def test_live_rules_preemption_and_manager_dm(stack, service, make_position, db):
    """선점 금지 6건·팀장 DM 5건을 실제 모델로. 픽스처 정규식(must_not·should) 결과를 출력한다."""
    from tests.agent.test_context_rules import PREEMPTION_AT, fixture, last_reply

    stack.use_llm(real_llm())
    driver = await start(stack, service, make_position, ALL_FIVE, 6)
    rows = []
    async with driver.client() as http:
        for index, case in enumerate(fixture("manager_dm")):
            await driver.say(case["candidate"], f"m{index}", http)
            reply = (await last_reply(db, driver.session_id)).content
            rows.append(_check(case["id"], reply, case))
        for index, case in enumerate(fixture("preemption")):
            await driver.advance_to(PREEMPTION_AT[case["id"]])
            await driver.say(case["candidate"], f"p{index}", http)
            reply = (await last_reply(db, driver.session_id)).content
            rows.append(_check(case["id"], reply, case))
    report("rules", rows)


def _check(case_id, reply, case):
    bad = [p for p in case.get("must_not_regex") or [] if re.search(p, reply, re.I)]
    should = case.get("should_regex") or []
    ok_should = not should or any(re.search(p, reply, re.I) for p in should)
    return {"id": case_id, "pass": not bad and ok_should, "must_not_hit": bad, "reply": reply}


@pytest.mark.live
async def test_live_observe_labels():
    """관찰 픽스처 7장을 실제 분류 모델로(temperature 0). 기대 레이블과 같은지 출력한다."""
    from tests.agent.test_observe import CASES, PROMPT

    llm, rows = real_llm(), []
    for card_id, (win, inputs, _, label, _, _) in CASES.items():
        body = await observe.observe(
            win, inputs, llm, PROMPT, usage=Usage(), trace=Trace("live", "live", "observe")
        )
        rows.append({"card": card_id, "expected": label, "got": body["label"], "aux": body["aux"]})
    report("observe", rows)


@pytest.mark.live
async def test_live_all_five_script(stack, service, make_position, db):
    """대본 all_five를 실제 모델 하나로(분류·페르소나·관찰 모두). 카드 실패율·폴백·레이블 일치를
    출력."""
    from tests.agent.script_driver import load_script

    stack.use_llm(real_llm())
    script = load_script("all_five")
    driver = await start(stack, service, make_position, script["elements"], script["minutes"])
    await driver.run(script["steps"], tolerant=True)
    sid = driver.session_id
    events = (
        await db.execute(select(SessionEvent).where(SessionEvent.session_id == sid))
    ).scalars()
    observations = {
        o.card_id: o.label
        for o in (
            await db.execute(select(Observation).where(Observation.session_id == sid))
        ).scalars()
    }
    runs = list((await db.execute(select(AgentRun).where(AgentRun.session_id == sid))).scalars())
    messages = list((await db.execute(select(Message).where(Message.session_id == sid))).scalars())
    rows = [{"card": e.card_id, "status": e.status, "attempts": e.attempts} for e in events] + [
        {"card": c, "expected": label, "got": observations.get(c)}
        for c, label in script["expect"]["labels"].items()
    ]
    rows.append({"driver_log": driver.log})
    rows.append(
        {
            "fallback_messages": sum(1 for m in messages if m.seq == 9),
            "llm_calls": sum((r.usage or {}).get("llm_calls", 0) for r in runs),
            "tokens": sum(
                (r.usage or {}).get("tokens_in", 0) + (r.usage or {}).get("tokens_out", 0)
                for r in runs
            ),
            "session_status": (await db.get(Session, sid, populate_existing=True)).status,
        }
    )
    for m in messages:
        if m.sender in ("colleague", "manager"):
            rows.append({"t": m.sender, "content": m.content[:200]})
    report("all_five", rows)
