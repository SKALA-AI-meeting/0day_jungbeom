"""근거 정확성 실행기 픽스처. e2e 러너 픽스처(api 테스트 스택 + DB 시각 시계)를 그대로 쓰고,
어시스턴트는 고정 문장 대신 실제 어시스턴트 그래프(rag-mcp 하위 프로세스, 스택의 LLM)를 끼운다.
"""

import pytest
from app.agent.assistant import AssistantGraphRunner, db_scenario, mcp_rag
from app.agent.mcp_client import RAG
from e2e.conftest import database_url, db, e2e_stack, engine, servers, stack, tracing_off  # noqa: F401


@pytest.fixture
async def eval_stack(e2e_stack, stack, database_url):  # noqa: F811
    assistant = AssistantGraphRunner(
        llm=stack.llm,
        rag=mcp_rag(stack.servers.mcp_urls[RAG]),
        scenario=db_scenario(stack.ctx.session_factory),
        database_url=database_url,
        broadcast=stack.hub.broadcast,
    )
    stack.ctx.assistant = assistant
    yield e2e_stack
    await assistant.aclose()
