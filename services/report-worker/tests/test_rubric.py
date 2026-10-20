"""완료 기준: rubric.evaluate 단위 테스트.

카드 7장 각각 고정 관찰 → 항목 값(기록 없음 사유 포함).
"""

import pytest
from report_worker.rubric import evaluate, tally

from tests.conftest import scenario

CARDS = {c["card_id"]: c for c in scenario()["cards"] if c.get("element")}


def obs(label, **metrics):
    return {
        "label": label,
        "evidence": [{"type": "message", "id": "m1"}],
        "metrics": {name: {"value": v, "evidence_ids": ["m1"]} for name, v in metrics.items()},
    }


# (카드, 관찰, 항목 값 순서대로)
CASES = [
    (
        "planning_division",
        obs("assign_only", division_by_candidate=True, stated_schedule=False),
        [1, 0],
    ),
    ("planning_checkin", obs("acknowledge", draft_delivered=True, draft_opened=False), [0, 1]),
    (
        "collab_help",
        obs("negotiate_timing", promise_kept=True),  # 종료 finalize에서 확정된 값
        [1, 1],
    ),
    ("collab_disagree", obs("dismiss", responded_to_request=True), [1, 0]),
    (
        "responsibility_delay",
        obs(
            "notify_with_alternative",
            notified_before_release=True,
            impact_possible=False,  # 영향 없는 분업 → 해당 없음
            proposes_alternative=True,
            notified_where_manager_sees=False,
        ),
        [1, None, 1, 0],
    ),
    (
        "adaptability_change",
        # 무관한 편집(C4): 문서는 바뀌었지만 바뀐 대상은 반영되지 않음 → 반영 항목 0
        obs(
            "refuse_or_ignore",
            document_changed_after=True,
            target_applied=False,
            redirected_colleague=False,
            mentions_scope_or_division=False,
        ),
        [0, 0, 0, 0],
    ),
    (
        "honesty_report",
        obs(
            "fair_report",
            has_colleague_shares=True,
            has_incomplete_facts=False,  # 미완료가 없으면 숨김 항목은 해당 없음
            has_report_message=True,
            credits_colleague=True,
            claims_colleague_work=False,
            response_minutes=12,
        ),
        [1, None, 1, 0],
    ),
]


@pytest.mark.parametrize(("card_id", "observation", "expected"), CASES, ids=[c[0] for c in CASES])
def test_each_card_items(card_id, observation, expected):
    items = evaluate(CARDS[card_id], observation)
    assert [i["auto"] for i in items] == expected
    reasons = [i["no_record_reason"] for i in items if i["auto"] is None]
    assert all(r == "not_applicable" for r in reasons)


def test_no_record_reasons():
    card = CARDS["planning_checkin"]
    reason = lambda items: [i["no_record_reason"] for i in items]  # noqa: E731
    assert reason(evaluate(card, None)) == ["no_activity"] * 2
    assert reason(evaluate(card, obs("feedback"), event_fired=False)) == ["event_not_fired"] * 2
    assert reason(evaluate(card, obs("feedback"), window_missed=True)) == ["window_missed"] * 2
    # 초안이 끝내 오지 않음(C5): 이벤트 표시 또는 draft_delivered=false 둘 다 document_missing
    assert (
        reason(evaluate(card, obs("feedback"), document_missing=True)) == ["document_missing"] * 2
    )
    undelivered = evaluate(card, obs("feedback", draft_delivered=False))
    assert reason(undelivered) == ["document_missing"] * 2
    unclassified = evaluate(card, obs(None, draft_delivered=True, draft_opened=True))
    assert [(i["auto"], i["no_record_reason"]) for i in unclassified] == [
        (1, None),
        (None, "classify_failed"),
    ]
    # 분류 실패: aux에 값이 남아 있어도 aux 기반 항목은 기록 없음, 기록 기반 항목은 그대로
    delay = evaluate(
        CARDS["responsibility_delay"],
        obs(
            "unclassified",
            notified_before_release=True,
            impact_possible=True,
            mentions_colleague_impact=True,
            proposes_alternative=False,
            notified_where_manager_sees=True,
        ),
    )
    assert [(i["auto"], i["no_record_reason"]) for i in delay] == [
        (1, None),
        (None, "classify_failed"),
        (None, "classify_failed"),
        (1, None),
    ]
    assert tally([1, 0, None, 1]) == {"met": 2, "unmet": 1, "no_record": 1}
