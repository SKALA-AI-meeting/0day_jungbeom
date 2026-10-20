"""완료 기준: rubric.evaluate 단위 테스트. 카드별 픽스처 관찰 → 항목 값·합계(기록 없음 포함)."""

import pytest
from report_worker.rubric import evaluate

from tests.conftest import card


def obs(label, **metrics):
    return {
        "label": label,
        "evidence": [{"type": "message", "id": "m1"}],
        "metrics": {name: {"value": v, "evidence_ids": ["m1"]} for name, v in metrics.items()},
    }


# (요소, 관찰, 항목 값 순서대로, 합계)
CASES = [
    (
        "cooperation",
        obs(
            "negotiate_timing",
            responded_to_request=True,
            response_minutes=3.0,
            response_specific=True,
        ),
        [1, 1, 1, 1],
        {"met": 4, "judged": 4, "no_record": 0},
    ),
    (
        "responsibility",
        obs(
            "notify_only",
            notified_before_release=True,
            proposes_alternative=False,
            notified_in_team=False,
            doc_opened_after_release=True,
        ),
        [1, 0, 0, 1],
        {"met": 2, "judged": 4, "no_record": 0},
    ),
    (
        "flexibility",
        obs(
            "replan_and_apply",
            document_changed_after=True,
            response_minutes=12.0,
            mentions_scope_or_division=True,
            redirected_colleague=False,
        ),
        [1, 0, 1, 0],
        {"met": 2, "judged": 4, "no_record": 0},
    ),
    (
        # 언급 자체가 없으면 respect_no_blame은 only_if 불충족 → 기록 없음(not_applicable)
        "respect",
        obs("not_noticed", mentions_policy=False, proposes_fix=False),
        [0, 0, 0, None],
        {"met": 0, "judged": 3, "no_record": 1},
    ),
]


@pytest.mark.parametrize(("element", "observation", "values", "auto"), CASES)
def test_evaluate_per_card(element, observation, values, auto):
    result = evaluate(card(element), observation)
    assert [i["auto"] for i in result["items"]] == values
    assert result["auto"] == auto
    for item in result["items"]:
        assert bool(item["evidence_ids"]) == (item["auto"] == 1)  # 근거는 충족 항목에만
        assert (item["no_record_reason"] is None) == (item["auto"] is not None)
    if element == "respect":
        assert result["items"][3]["no_record_reason"] == "not_applicable"


def test_evaluate_no_record_reasons():
    coop = card("cooperation")
    not_fired = evaluate(coop, None, event_fired=False)
    assert {i["no_record_reason"] for i in not_fired["items"]} == {"event_not_fired"}
    assert not_fired["auto"] == {"met": 0, "judged": 0, "no_record": 4}

    no_activity = evaluate(coop, {"label": "no_evidence", "metrics": {}, "evidence": []})
    assert {i["no_record_reason"] for i in no_activity["items"]} == {"no_activity"}

    # unclassified: 레이블 항목·aux 지표는 classify_failed, 순수 지표는 계산,
    # response_minutes null은 활동이 있으므로 0
    unclassified = evaluate(
        coop,
        obs(
            "unclassified", responded_to_request=True, response_minutes=None, response_specific=None
        ),
    )
    assert [i["auto"] for i in unclassified["items"]] == [1, 0, None, None]
    assert [i["no_record_reason"] for i in unclassified["items"]] == [
        None,
        None,
        "classify_failed",
        "classify_failed",
    ]
    assert unclassified["auto"] == {"met": 1, "judged": 2, "no_record": 2}


def test_window_missed_and_aux_null_reasons():
    respect = card("respect")
    # aux 판정 지표(proposes_fix)가 null이면 레이블이 정상이어도 classify_failed
    labeled = evaluate(respect, obs("point_out_vague", mentions_policy=False, proposes_fix=None))
    assert [i["no_record_reason"] for i in labeled["items"]] == [
        None,
        None,
        "classify_failed",
        None,
    ]

    # observe가 남긴 window_missed: {value, evidence_ids} 형식과 bool 둘 다
    for flag in ({"value": True, "evidence_ids": []}, True):
        observation = obs("point_out_vague", mentions_policy=True, proposes_fix=True)
        observation["metrics"]["window_missed"] = flag
        result = evaluate(respect, observation)
        assert {i["no_record_reason"] for i in result["items"]} == {"window_missed"}
