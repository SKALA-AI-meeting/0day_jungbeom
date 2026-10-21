"""어시스턴트 tool-calling 루프(최대 3회, 인용, 잠금 안내, guard)."""

import uuid
from contextlib import asynccontextmanager

import pytest
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


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (
            "하수관 센서로 30분 전에 경보했어요.\nmaterial_id: water_flood_cases",
            "하수관 센서로 30분 전에 경보했어요.\n출처: 도심 침수 사례",
        ),
        (
            "도심 침수 사례(material_id: water_flood_cases)를 보면 30분 전에 경보했어요.",
            "도심 침수 사례를 보면 30분 전에 경보했어요.",
        ),
        (
            '도심 침수 사례를 보면 경보가 빨랐어요. cited_material_ids: ["water_flood_cases"]',
            "도심 침수 사례를 보면 경보가 빨랐어요.",
        ),
        (
            "water_flood_cases 자료를 보면 30분 전에 경보했어요.",
            "도심 침수 사례 자료를 보면 30분 전에 경보했어요.",
        ),
    ],
)
async def test_internal_material_ids_are_not_shown(catalog, answer, expected):
    runner, _, _ = make(catalog, [tool_call("search_materials", query="침수"), answer])
    result = await runner.answer(uuid.uuid4(), "침수 사례 있어?", uuid.uuid4())
    assert result.content == expected
    assert result.cited_material_ids == ["water_flood_cases"]


TITLES = {"water_flood_cases": "도심 침수 사례", "water_stats": "지역별 물 부족 통계"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # 표기 뒤 숫자·문장은 그대로
        ("material_id: water_flood_cases, 30분 전에 경보했어요.", "30분 전에 경보했어요."),
        (
            "센서가 30분 전에 울렸어요 (material_id: `water_flood_cases`).",
            "센서가 30분 전에 울렸어요.",
        ),
        ('근거는 {"material_id": "water_stats"} 이에요.', "근거는 이에요."),
        (
            '요약했어요.\n"cited_material_ids": ["water_flood_cases", "water_stats"]\n다음 줄',
            "요약했어요.\n다음 줄",
        ),
        # URL·인라인 코드·코드 블록 안, 들여쓰기·빈 줄은 그대로
        (
            "링크 https://x.org/water_flood_cases 참고\n\n  들여쓴 줄  두 칸\n`water_stats`",
            "링크 https://x.org/water_flood_cases 참고\n\n  들여쓴 줄  두 칸\n`water_stats`",
        ),
        (
            "```\nmaterial_id: water_stats\n    x = 1\n```",
            "```\nmaterial_id: water_stats\n    x = 1\n```",
        ),
        # 모르는 id(이번 응답에서 받지 않은 자료)와 정상 문장·제목은 그대로
        (
            "material_id: fire_cases 는 그대로, 도심 침수 사례 30%",
            "material_id: fire_cases 는 그대로, 도심 침수 사례 30%",
        ),
        ("water_stats 기준 3.5배", "지역별 물 부족 통계 기준 3.5배"),
        # URL 바로 뒤 표기는 지워도 링크 뒤 공백 하나는 남긴다
        ("https://example.org (material_id: water_stats) 참고", "https://example.org 참고"),
        # 인라인 코드 전체가 표기면 백틱 쌍째 지운다
        ("자료는 `material_id: water_stats` 하나예요.", "자료는 하나예요."),
        # ~~~ 펜스와 4칸 들여쓴 코드 블록 안은 그대로
        ("~~~\nmaterial_id: water_stats\n~~~", "~~~\nmaterial_id: water_stats\n~~~"),
        (
            "예시:\n\n    material_id: water_stats\n    water_flood_cases",
            "예시:\n\n    material_id: water_stats\n    water_flood_cases",
        ),
    ],
)
def test_hide_ids_touches_only_known_id_notation(text, expected):
    from app.agent.assistant.runner import hide_ids

    assert hide_ids(text, TITLES) == expected


async def test_ids_hidden_with_open_and_locked_lookups(catalog):
    """열린 자료 조회 성공 + 미공개 자료 조회 거부가 섞여도 받은 자료 id만 지운다."""
    runner, _, _ = make(
        catalog,
        [
            tool_call("get_material", material_id="water_flood_cases"),
            tool_call("get_material", material_id="fire_cases"),
            "침수 경보가 빨랐어요 (material_id: water_flood_cases). fire_cases는 못 봤어요.",
        ],
    )
    result = await runner.answer(uuid.uuid4(), "사례 있어?", uuid.uuid4())
    assert result.content == "침수 경보가 빨랐어요. fire_cases는 못 봤어요.\n출처: 도심 침수 사례"
    assert result.cited_material_ids == ["water_flood_cases"]
