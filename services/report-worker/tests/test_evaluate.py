"""워커 검증(rubric.md 7.3)·요소 단위 1회 재요청·확신도 clamp·요소 수준 단위 테스트(FakeLLM)."""

import copy

import pytest
from report_worker.evaluate import (
    FAILED_SUMMARY,
    EvalContext,
    RefIndex,
    element_level,
    evaluate_element,
    load_forbidden,
    load_prompts,
    validate_output,
)
from report_worker.llm import empty_usage

from tests.conftest import SCENARIOS, FakeLLM, element_outputs, load

RECORD = load("session_record")
RUBRIC = load("internal_rubric")
CONTRIBUTIONS = load("internal_contributions")
FORBIDDEN = load_forbidden(SCENARIOS, "debate")


def ctx(record=RECORD, rubric=RUBRIC) -> EvalContext:
    return EvalContext(
        record=record,
        rubric=rubric,
        refs=RefIndex(record, CONTRIBUTIONS),
        prompts=load_prompts(SCENARIOS, "debate"),
        forbidden=FORBIDDEN,
    )


def element_rubric(element: str, rubric=RUBRIC) -> dict:
    return next(e for e in rubric["elements"] if e["element"] == element)


def dim(output: dict, dimension_id: str) -> dict:
    return next(d for d in output["dimensions"] if d["dimension_id"] == dimension_id)


async def run(element: str, *outputs, record=RECORD, rubric=RUBRIC):
    llm = FakeLLM()
    llm.script[element] = list(outputs)
    usage = empty_usage(llm.model)
    rows, summary = await evaluate_element(
        llm, ctx(record, rubric), element_rubric(element, rubric), usage
    )
    return {r["dimension_id"]: r for r in rows}, summary, llm, usage


def test_fixture_outputs_pass_validation():
    refs = RefIndex(RECORD, CONTRIBUTIONS)
    for element, output in element_outputs().items():
        ids = [d["dimension_id"] for d in element_rubric(element)["dimensions"]]
        checked = validate_output(output, ids, refs, FORBIDDEN)
        assert checked.errors == {}, element
        assert set(checked.valid) == set(ids)


def _no_evidence(o):
    dim(o, "listen_understand")["evidence_refs"] = []


def _level4_one_unit(o):
    dim(o, "listen_engage")["evidence_refs"] = ["msg:m-15", "msg:m-13"]  # 지원자 1 + 맥락 1


def _context_only(o):
    dim(o, "listen_understand")["evidence_refs"] = ["msg:m-13", "msg:m-16"]  # AI 메시지만


def _other_session(o):
    dim(o, "listen_understand")["evidence_refs"] = ["msg:other-session-m-99"]


def _level_and_reason(o):
    dim(o, "listen_understand")["no_record_reason"] = "no_activity"


def _missing(o):
    o["dimensions"] = [d for d in o["dimensions"] if d["dimension_id"] != "listen_understand"]


def _duplicate(o):
    o["dimensions"].append(copy.deepcopy(dim(o, "listen_understand")))


def _forbidden(o):
    dim(o, "listen_understand")["rationale"] = "총점이 높아 추천합니다."


BROKEN = {
    "listen_understand": [
        _no_evidence,
        _context_only,
        _other_session,
        _level_and_reason,
        _missing,
        _duplicate,
        _forbidden,
    ],
    "listen_engage": [_level4_one_unit],
}
CASES = [(d, f) for d, fs in BROKEN.items() for f in fs]


@pytest.mark.parametrize(("dimension_id", "breaker"), CASES, ids=[f.__name__ for _, f in CASES])
async def test_invalid_dimension_retries_element_once_then_evaluate_failed(dimension_id, breaker):
    bad = copy.deepcopy(element_outputs()["listening"])
    breaker(bad)
    rows, summary, llm, usage = await run("listening", bad, copy.deepcopy(bad))
    assert len(llm.calls) == 2  # 요소 단위 1회 재요청
    assert "[재요청]" in llm.calls[1][2] and dimension_id in llm.calls[1][2]
    assert usage["element_retries"] == 1
    assert rows[dimension_id]["level"] is None
    assert rows[dimension_id]["no_record_reason"] == "evaluate_failed"
    assert rows[dimension_id]["confidence"] is None
    others = [r for d, r in rows.items() if d != dimension_id]
    assert all(r["no_record_reason"] != "evaluate_failed" for r in others)  # 나머지는 재요청 결과
    assert summary["dimension_count"] == 4 and summary["no_record_count"] == 1


async def test_retry_result_replaces_first_output():
    bad = copy.deepcopy(element_outputs()["listening"])
    _no_evidence(bad)
    good = element_outputs()["listening"]
    rows, summary, llm, _ = await run("listening", bad, good)
    assert len(llm.calls) == 2
    assert all(r["no_record_reason"] is None for r in rows.values())
    assert summary["summary"] == good["summary"]


async def test_valid_output_calls_once():
    rows, summary, llm, usage = await run("listening", element_outputs()["listening"])
    assert len(llm.calls) == 1 and usage["element_retries"] == 0
    assert summary["level"] == 4  # (4+3+4+4)/4 = 3.75 → 4


async def test_confidence_over_cap_is_clamped_not_rejected():
    out = copy.deepcopy(element_outputs()["listening"])
    dim(out, "listen_understand")["confidence"] = "high"  # 근거 1개 → 최대 medium
    rows, _, llm, _ = await run("listening", out)
    assert len(llm.calls) == 1
    assert rows["listen_understand"]["confidence"] == "medium"
    assert rows["listen_understand"]["level"] == 3
    assert rows["listen_understand"]["rationale"] == dim(out, "listen_understand")["rationale"]


async def test_core_card_not_fired_caps_low_and_one_persuasion_card_caps_medium():
    record = copy.deepcopy(RECORD)
    record["observations"] = [
        o for o in record["observations"] if o["card_id"] != "persuasion_solution"
    ]
    record["observations"] = [
        o for o in record["observations"] if o["card_id"] != "listening_pressure"
    ]
    listening, _, _, _ = await run("listening", element_outputs()["listening"], record=record)
    assert listening["listen_engage"]["confidence"] == "low"
    persuasion, _, _, _ = await run("persuasion", element_outputs()["persuasion"], record=record)
    assert persuasion["pers_convergence"]["confidence"] == "medium"  # 설득 카드 하나만 발동


async def test_credit_record_counts_contribution_reference():
    out = copy.deepcopy(element_outputs()["honesty"])
    assert dim(out, "hon_credit_record")["evidence_refs"] == [
        "proposal:idea_credit",
        "contribution:opt-pb-p2",
    ]
    rows, _, llm, _ = await run("honesty", out)
    assert len(llm.calls) == 1 and rows["hon_credit_record"]["level"] == 4
    # 다른 차원에서는 contribution이 개수에 들지 않는다
    dim(out, "hon_process_truth")["evidence_refs"] = ["contribution:opt-pb-p2"]
    rows, _, llm, _ = await run("honesty", out, copy.deepcopy(out))
    assert rows["hon_process_truth"]["no_record_reason"] == "evaluate_failed"


async def test_forbidden_summary_retries_then_fixed_sentence():
    out = copy.deepcopy(element_outputs()["listening"])
    out["summary"] = "이 지원자는 합격 수준이다."
    rows, summary, llm, _ = await run("listening", out, copy.deepcopy(out))
    assert len(llm.calls) == 2
    assert summary["summary"] == FAILED_SUMMARY
    assert all(r["no_record_reason"] != "evaluate_failed" for r in rows.values())


async def test_unparseable_twice_fails_every_dimension():
    rows, summary, llm, _ = await run("listening", "not json", "{broken")
    assert len(llm.calls) == 2
    assert {r["no_record_reason"] for r in rows.values()} == {"evaluate_failed"}
    assert summary["level"] is None and summary["summary"] == FAILED_SUMMARY


def test_element_level_rounds_half_up_and_null_when_no_record():
    def rows(*levels):
        return [{"level": lv} for lv in levels]

    assert element_level(rows(4, 3, 4)) == 4
    assert element_level(rows(3, 4)) == 4  # 3.5 → 4
    assert element_level(rows(2, 3, None)) == 3  # 2.5 → 3, 기록 없음 제외
    assert element_level(rows(2, 2, 3)) == 2
    assert element_level(rows(None, None)) is None
