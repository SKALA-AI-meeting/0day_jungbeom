"""실 모델 확인(`-m live`): 페르소나 발언 1회·의도 분류 1회. infra/.env 키, 호출 수 최소."""

import pytest
from app.agent import intent
from app.agent.llm import make_llm
from conftest import intent_of

pytestmark = pytest.mark.live


async def test_live_persona_reply(harness):
    h = harness("keyword")
    h.runner.llms.persona = make_llm("persona")
    mid = h.candidate("한결님은 어떤 키워드가 좋으세요?", intent_of("question", to=("p1",)))
    run = await h.run("message", message_id=mid)
    assert run.ok and run.error is None, run.error
    post = h.posted("p1")[0]
    assert post["content"] and post["meta"]["guard"] in ("pass", "regenerated")
    print(f"persona llm_calls={run.usage['llm_calls']} meta={post['meta']}")


async def test_live_intent_one(catalog):
    llm = make_llm("intent")
    out, used_fallback = await intent.classify(
        llm,
        "저는 물로 하면 좋겠어요.",
        phase="keyword",
        catalog=catalog.catalog_options("keyword", None),
        options=[],
        recent=[],
        seats={"p1": "강한결", "p2": "윤하람", "p3": "서지안"},
        instructions=catalog.prompts.get("intent.md"),
    )
    assert (
        not used_fallback and out["intent"] == "propose" and out["scenario_option_key"] == "water"
    )
