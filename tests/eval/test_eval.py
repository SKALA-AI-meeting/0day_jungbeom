"""근거 정확성 픽스처 실행(mock 기본, `-m live`로 gpt-4o-mini 1회).

mock(FakeLLM)은 응답 문구가 고정이라 의미 판정(사실·선점·유출)은 live에서 본다. mock이 보는 것은
실행기가 16건을 실제 경로로 끝까지 묻고 판정하는지, 그리고 코드가 정하는 결과(미공개 문서
고정 문장)와 입력 거부 3종이다.
"""

import uuid
from pathlib import Path

import pytest
from app.agent.llm import OpenAILLM
from app.config import get_settings
from e2e.client import Api, Transcript
from tests.agent.brain import Brain

from eval import evaluate

RECORDS = Path(__file__).resolve().parents[1] / "e2e" / "records"
CODE_DECIDED = {"g05_interview_not_released", "g09_assistant_not_released"}


def mock_brain(cases) -> Brain:
    """질문마다 픽스처의 기대 도구를 한 번 고르고, 검색 결과 첫 문서를 인용해 답한다."""
    tools = {}
    for case in cases:
        if case["persona"] == "assistant" or not case.get("expected_tools"):
            continue
        tool = case["expected_tools"][0]
        args = (
            {"query": case["question"]}
            if tool == "search_documents"
            else {"doc_id": "interview_summary"}
        )
        tools[case["question"]] = (tool, args)
    return Brain(tools=tools, echo_search=True)


def test_cases_load():
    cases = evaluate.load_cases()
    groups = [c["group"] for c in cases]
    assert (groups.count("grounding"), groups.count("leak"), groups.count("preemption")) == (
        10,
        3,
        3,
    )
    assert all(c["question"] and c["elements"] and "at" in c for c in cases)


async def test_eval_runs_every_case(eval_stack, stack):
    target, clock_factory, transports, _ = eval_stack
    cases = evaluate.load_cases()
    stack.llm.default = mock_brain(cases)

    results = await evaluate.run_all(target, transports, clock_factory, cases)

    assert [r["id"] for r in results] == [c["id"] for c in cases]
    assert all(r["reply"] for r in results), [r["id"] for r in results if not r["reply"]]
    for r in results:
        if r["id"] in CODE_DECIDED:  # 미공개 문서 질문의 고정 문장은 코드가 정한다
            assert not [f for f in r["failures"] if f.startswith("fact")], (r["id"], r["reply"])
    grounded = [r for r in results if r["group"] == "grounding" and r["persona"] != "assistant"]
    assert all("search_documents" in r["tools"] or "get_document" in r["tools"] for r in grounded)


async def test_evidence_rejections(eval_stack, stack):
    """다른 세션 id 섞기 422, 창 밖 메시지를 근거로 골라도 저장 안 됨,
    검색하지 않은 문서 인용 제거.
    """
    target, clock_factory, transports, _ = eval_stack
    other = evaluate.Session(target, transports, clock_factory)
    await other.open(["collaboration"], alias="other")
    api = Api(target, Transcript(), transports=transports)
    r = await api.call("GET", f"/internal/sessions/{other.sid}/messages", internal=True)
    foreign = r.json()[0]["id"]
    await other.close()

    # 관찰 분류가 다른 세션 메시지를 근거로 골라도 observe가 버린다
    brain = Brain(labels={"collab_help": {"label": "help_now"}})
    original = brain._observe

    def with_foreign(human: str) -> str:
        import json

        out = json.loads(original(human))
        out["evidence"].append({"type": "message", "id": foreign})
        return json.dumps(out)

    brain._observe = with_foreign
    brain.say = "재참여율은 22%예요 [사용자 인터뷰 요약].\n출처: 사용자 인터뷰 요약, 지표 현황"
    stack.llm.default = brain
    session = evaluate.Session(target, transports, clock_factory)
    await session.open(["collaboration"], alias="mine")
    await session.go_to("collab_help")
    await session.socket.send_message("dm", "지금 바로 같이 볼게요.")
    await session.clock.settle()
    got = await session.ask("assistant", "첫 참여 후 재참여율 알려줘")
    await session.go_to(4.6)
    observations = await api.call(
        "GET", f"/internal/sessions/{session.sid}/observations", internal=True
    )
    help_obs = next(o for o in observations.json() if o["card_id"] == "collab_help")
    assert help_obs["evidence"] and foreign not in {e["id"] for e in help_obs["evidence"]}

    # 미공개(인터뷰 요약)라 검색되지 않은 문서의 인용은 응답·cited_docs에서 지워진다
    assert "[사용자 인터뷰 요약]" not in got["reply"] and "interview_summary" not in got["cited"]

    # 다른 세션 id를 섞은 관찰 저장은 422
    body = {
        "card_id": "collab_help",
        "element": "collaboration",
        "window_start": 9.0,
        "window_end": 9.5,
        "metrics": {},
        "label": "help_now",
        "evidence": [{"type": "message", "id": foreign}],
        "run_id": str(uuid.uuid4()),
    }
    r = await api.call(
        "POST", f"/internal/sessions/{session.sid}/observations", internal=True, json_body=body
    )
    assert r.status_code == 422, r.text
    await session.close()
    await api.aclose()


@pytest.mark.live
async def test_eval_live(eval_stack, stack):
    """실제 모델 1회. 통과를 요구하지 않고 결과를 records/eval-live-<일시>.md에 남긴다."""
    settings = get_settings()
    assert settings.openai_api_key, "OPENAI_API_KEY가 infra/.env에 필요하다"
    llm = OpenAILLM(settings.openai_api_key, settings.openai_model)
    stack.use_llm(llm)
    stack.ctx.assistant.llm = llm
    target, clock_factory, transports, _ = eval_stack

    results = await evaluate.run_all(target, transports, clock_factory)

    path = evaluate.write_live_record(results, RECORDS)
    print(f"\n{path}\n" + "\n".join(f"{r['id']}: {r['ok']} {r['failures']}" for r in results))
    assert path.is_file()
