"""페르소나 경계: stance_check 픽스처, guard 픽스처, 비용 상한, 컨텍스트 스냅샷, assessment 차단."""

import re

import pytest
import yaml
from app.agent.catalog import render
from app.agent.mcp_client import ASSESSMENT, McpClient, RunTools
from conftest import MISSION_DIR, intent_of, say

FIXTURES = MISSION_DIR / "prompts" / "fixtures"


def _cases(name: str) -> list[dict]:
    return yaml.safe_load((FIXTURES / name).read_text(encoding="utf-8"))["cases"]


def _setup(harness, case: dict):
    """픽스처 plan이 그 자리의 stance_plan이 되도록 단계 상태를 만든다."""
    h = harness(case["phase"])
    if case["phase"] != "keyword":
        h.server.confirm_keyword("water")
    plan = case["plan"]
    if case["phase"] == "problem" and not plan.get("before_card"):
        lead = h.server.add_option(plan["option"], "p1")
        h.server.lock("flexibility_majority", lead)
        h.server.cards["flexibility_majority"]["delivered"] = ["p1", "p3"]
    for _ in range(plan.get("candidate_counter_count", 0)):
        h.candidate("그 안은 별로예요.", intent_of("oppose", key=plan["option"]))
    return h


@pytest.mark.parametrize("case", _cases("stance_offplan.yaml"), ids=lambda c: c["id"])
async def test_offplan_regenerates_then_fallback(harness, case):
    h = _setup(harness, case)
    bad = case["bad_output"]
    out = say(
        bad["content"], {"option_id": bad["stance"]["option"], "stance": bad["stance"]["stance"]}
    )
    h.persona.script += [out, out]
    mid = h.candidate(case["candidate"], intent_of("question", to=(case["seat"],)))

    run = await h.run("message", message_id=mid)

    assert run.ok and len(h.persona.calls) == 2  # 원 응답 + 재생성 1회
    post = h.posted(case["seat"])[0]
    persona, situation = case["expected_fallback"].split(".")
    entry = h.server.catalog.stance_fallback[persona][situation]
    label = h.server.catalog.label_of(case["plan"]["option"] or "") or ""
    assert post["content"] == render(entry["text"], option=label)
    assert post["meta"]["stance_check"] == "fallback"
    support = h.server.support[case["seat"]]
    if entry["stance"] == "support":
        option = next(o for o in h.server.options if o["option_id"] == support)
        assert option["scenario_option_key"] == case["plan"]["option"]  # 게시 문장과 저장 입장 일치
    else:
        assert support is None


async def test_offplan_regenerated_ok(harness):
    h = harness("keyword")
    h.persona.script += [
        say("바람 말고 물이 낫겠네요.", {"option_id": "water", "stance": "support"}),
        say("저는 그래도 바람이요.", {"option_id": "wind", "stance": "support"}),
    ]
    mid = h.candidate("지안님?", intent_of("question", to=("p3",)))
    await h.run("message", message_id=mid)
    post = h.posted("p3")[0]
    assert (
        post["content"] == "저는 그래도 바람이요." and post["meta"]["stance_check"] == "regenerated"
    )


@pytest.mark.parametrize("case", _cases("verdict.yaml"), ids=lambda c: c["id"])
async def test_guard_regenerates_then_safe_phrase(harness, case):
    h = harness(case["phase"])
    if case["phase"] != "keyword":
        h.server.confirm_keyword("water")
    h.persona.script += [say(case["bad_output"]), say(case["bad_output"])]
    mid = h.candidate(case["candidate"], intent_of("question", to=(case["target_seat"],)))

    await h.run("message", message_id=mid)

    post = h.posted(case["target_seat"])[0]
    assert post["content"] == h.server.catalog.safe_phrase(case["target_seat"])
    assert (
        post["meta"]["guard"] == "safe" and case["expect_guard_group"] in post["meta"]["guard_hits"]
    )


async def test_guard_allow_exact_notice_passes(harness):
    notice = harness("keyword").server.catalog.notices["evaluation"]
    h = harness("keyword", persona=[say(notice)])
    mid = h.candidate("평가 기준이 뭐예요?", intent_of("question", to=("p3",)))
    await h.run("message", message_id=mid)
    assert h.posted("p3")[0]["content"] == notice and len(h.persona.calls) == 1


async def test_cost_cap_uses_safe_phrase_without_llm(harness):
    h = harness("keyword")
    h.server.cost_left = 0
    mid = h.candidate("한결님?", intent_of("question", to=("p1",)))
    run = await h.run("message", message_id=mid)
    assert not h.persona.calls and run.usage["llm_calls"] == 0
    assert h.posted("p1")[0]["content"] == h.server.catalog.safe_phrase("p1")


async def test_persona_context_snapshot(harness):
    h = harness("problem", persona=[say("자료부터 봐요.")])
    h.server.confirm_keyword("water")
    h.server.cards["flexibility_majority"] = {
        "card_id": "flexibility_majority",
        "locked_option_id": None,
        "delivered": [],
    }
    mid = h.candidate("지안님 의견은요?", intent_of("question", to=("p3",)))
    await h.run("message", message_id=mid)

    system, human = (str(m.content) for m in h.persona.calls[0].messages)
    assert "김지원님" in human and "강한결" in human and "윤하람" in human
    hidden = [
        "card_progress",
        "cost_left",
        "flexibility_majority",
        "listening_pressure",
        "관찰",
        "평가표",
        "어시스턴트",
    ]
    hidden += ["고집형", "소극형", "비판형", "stubborn", "quiet", "critic", "rubric", "경청/존중"]
    assert [w for w in hidden if w in human] == []
    assert not re.search(r"\b(stubborn|quiet|critic)\b", system)


async def test_persona_scope_has_no_assessment(harness):
    h = harness("keyword")
    tools = RunTools(h.server, h.assessment)
    persona = tools.persona("keyword")
    result = await persona.call(
        "record_observation", {"card_id": "x", "phase": "keyword", "run_id": "r"}
    )
    assert result["error"]["code"] == "forbidden" and not h.assessment.calls
    assert ASSESSMENT not in persona._extra
    assert {s["function"]["name"] for s in await persona.specs()} <= {
        "get_transcript",
        "search_materials",
        "get_material",
    }
    assert "get_draft" in tools.persona("proposal").allowed and "get_draft" not in persona.allowed
    # 운영 경로의 페르소나 클라이언트(debate+rag)에는 assessment 서버가 없다
    main = McpClient({"debate": "http://x", "rag": "http://y"}, h.session_id)
    assert (await main._call("record_observation", {}))["error"]["code"] == "upstream_unavailable"


async def test_material_question_before_keyword_gets_not_released(harness):
    from app.agent.llm import tool_call

    h = harness(
        "keyword",
        persona=[
            tool_call("search_materials", query="침수 사례"),
            say("키워드가 정해지면 자료를 같이 봐요."),
        ],
    )
    mid = h.candidate("지안님, 자료 있어요?", intent_of("question", to=("p3",)))
    await h.run("message", message_id=mid)
    tool_result = h.persona.calls[1].messages[-1]
    assert "not_released" in str(tool_result.content)
    assert h.posted("p3")[0]["content"] == "키워드가 정해지면 자료를 같이 봐요."


def test_resolve_target_maps_catalog_label_to_key():
    from app.agent.debate.persona import resolve_target

    ds = {"options": [], "catalog_options": [{"scenario_option_key": "fire", "label": "불"}]}
    assert resolve_target(ds, "불") == {"fire"}


async def test_guard_blocks_credit_preemption(harness):
    bad = (
        '바람 아이디어는 제가 제안한 것이니, 기획안에 "서지안이 제안한 바람"이라고 적으면 좋겠네요.'
    )
    h = harness("proposal", persona=[say(bad), say(bad)])
    mid = h.candidate(
        "누가 그 아이디어 냈는지 기획안에 뭐라 쓸까?", intent_of("question", to=("p3",))
    )
    await h.run("message", message_id=mid)
    post = h.posted("p3")[0]
    assert post["content"] == h.server.catalog.safe_phrase("p3")
    assert "credit" in post["meta"]["guard_hits"]


def test_credit_group_only_in_proposal_and_narrow(catalog):
    from app.agent.guard import guard_from_prompts

    guard = guard_from_prompts(catalog.prompts)
    spec = next(g for g in catalog.guard_spec["groups"] if g["id"] == "credit")
    for text in spec["examples"]["hit"]:
        assert "credit" in guard.check(text, "proposal").hits
        assert "credit" not in guard.check(text, "keyword").hits  # 토론 단계에는 적용하지 않는다
    for text in spec["examples"]["miss"]:
        assert guard.check(text, "proposal").ok, text
