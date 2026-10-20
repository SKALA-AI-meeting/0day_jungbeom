"""실제 gpt-4o-mini 1회 확인(`make test-live`). 미공개 문서 질문(g05)을 실제 모델로 돌린다.

MCP 서버·api 앱은 연결 테스트와 같은 구성이다. LangSmith 트레이싱은 infra/.env 설정을 따르고,
trace에는 run_id 태그가 붙는다.
"""

import re

import pytest
from app.agent.llm import OpenAILLM
from app.agent.runner import Stimulus
from app.config import get_settings
from app.services.messages import accept_candidate_message
from app.services.runs import run_agent

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
