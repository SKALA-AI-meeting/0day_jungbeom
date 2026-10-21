"""어시스턴트 tool-calling 루프(최대 3회, 인용, 잠금 안내, guard)."""

import uuid
from contextlib import asynccontextmanager

from app.agent.assistant import AssistantGraphRunner
from app.agent.llm import FakeLLM, make_llm, tool_call
from app.agent.mcp_client import ASSISTANT_TOOLS, ToolScope
from app.ports import FakeSessionPorts
from conftest import FakeServer


def make(catalog, script, keyword: str | None = "water"):
    server = FakeServer(catalog, FakeSessionPorts(uuid.uuid4()))
    server.keyword = keyword
    llm = FakeLLM(script)

    @asynccontextmanager
    async def rag(_sid):
        yield ToolScope(server, ASSISTANT_TOOLS)

    async def scenario(_sid):
        return {
            "mission_id": "debate",
            "prompts": catalog.prompts,
            "catalog": {
                "mission": catalog.mission,
                "personas": catalog.personas,
                "cards": catalog.cards,
                "keywords": catalog.keywords,
            },
        }

    return AssistantGraphRunner(llm=llm, rag=rag, scenario=scenario), llm, server


async def test_model_picks_tools_and_cites(catalog):
    runner, llm, server = make(
        catalog,
        [
            tool_call("search_materials", query="침수 사례"),
            tool_call("get_material", material_id="water_flood_cases"),
            "도심 침수 사례를 보면 하수관 수위 센서로 30분 전에 경보했어요.",
        ],
    )
    result = await runner.answer(uuid.uuid4(), "침수 대응 사례 있어?", uuid.uuid4())
    assert [c["name"] for c in result.tool_calls] == ["search_materials", "get_material"]
    assert result.cited_material_ids == ["water_flood_cases"]
    assert "도심 침수 사례" in result.content
    assert (
        llm.calls[0].tools and llm.calls[0].temperature == 0.7
    )  # FakeLLM 기본, 역할 값은 make_llm이 넣는다
    assert result.usage["tool_calls"] == 2


async def test_tool_calls_capped_at_three(catalog):
    runner, llm, _ = make(
        catalog, [tool_call("search_materials", query="q")] * 4 + ["물 부족 통계를 참고하세요."]
    )
    result = await runner.answer(uuid.uuid4(), "자료?", uuid.uuid4())
    assert len(result.tool_calls) == 3
    assert llm.calls[-1].tools is None  # 3회 뒤에는 도구를 바인딩하지 않는다
    assert result.cited_material_ids and result.content


async def test_locked_materials_answer_fixed_sentence(catalog):
    runner, _, _ = make(
        catalog, [tool_call("search_materials", query="침수"), "모르겠어요."], keyword=None
    )
    result = await runner.answer(uuid.uuid4(), "침수 자료 있어?", uuid.uuid4())
    assert (
        result.content == "키워드가 정해지면 자료를 찾을 수 있어요."
        and result.cited_material_ids == []
    )


async def test_guard_replaces_with_notice(catalog):
    runner, _, _ = make(catalog, ["이렇게 하시면 합격이에요.", "점수는 높을 거예요."])
    result = await runner.answer(uuid.uuid4(), "저 붙을까요?", uuid.uuid4())
    assert result.content == catalog.notices["evaluation"]


async def test_llm_fake_mode_assistant(catalog):
    runner, _, _ = make(catalog, [])
    runner.llm = make_llm("assistant", {"LLM_FAKE": "1"})
    result = await runner.answer(uuid.uuid4(), "침수 사례", uuid.uuid4())
    assert [c["name"] for c in result.tool_calls] == ["search_materials"]
    assert result.cited_material_ids == ["water_flood_cases"]
    assert result.content.startswith("도심 침수 사례")
