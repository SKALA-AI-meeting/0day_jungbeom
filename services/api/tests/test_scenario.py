"""완료 기준: 조립 결과가 docs/common/scenario-model.md 수치와 일치, 카탈로그 이름이 rubric.md 표와
일치, catalog_version이 미션 폴더 전체 해시."""

import shutil

from app.services.scenario import build_scenario, catalog_version, load_catalog

from tests.conftest import SCENARIOS

ALL_FIVE = ["responsibility", "planning", "adaptability", "collaboration", "honesty"]


def _timeline(scenario):
    return [(c["card_id"], c["at_min"]) for c in scenario["cards"]]


def test_assembled_timeline_matches_scenario_model():
    scenario, version = build_scenario(SCENARIOS, ALL_FIVE, 120)

    # L=120, 5개 전부: 저장 형식 예시 그대로
    assert scenario["mission_id"] == "planning" and scenario["session_minutes"] == 120
    assert _timeline(scenario) == [
        ("kickoff", 0),
        ("planning_division", 10),
        ("collab_help", 30),
        ("planning_checkin", 45),
        ("responsibility_delay", 60),
        ("adaptability_change", 75),
        ("review", 90),
        ("collab_disagree", 90),
        ("honesty_report", 110),
    ]
    cards = {c["card_id"]: c for c in scenario["cards"]}
    assert cards["planning_division"]["window_start_min"] == 0
    assert cards["planning_checkin"]["sends_document"] == {"parts": "colleague_all", "version": 1}
    assert cards["review"]["flow"] is True
    assert cards["review"]["sends_document"] == {"parts": "colleague_all", "version": 2}
    assert cards["responsibility_delay"]["effects"] == {
        "release_document": "interview_summary",
        "release_at_min": 70,
    }
    assert cards["collab_disagree"]["attach_to"] == "review"
    assert len(cards["collab_disagree"]["fixed_opinions"]) == 2
    assert cards["honesty_report"]["or_on_submit"] is True
    assert scenario["division_min"] == {
        "2": ["candidate"],
        "3": ["colleague", "both"],
        "any_colleague_only": [4, 5],
    }
    assert scenario["parts"]["3"] == {"title": "핵심 기능 제안", "depends_on": [2]}
    assert scenario["vars"]["interview_expected_time"] == "01:00"
    assert scenario["vars"]["release_time"] == "01:10"
    assert scenario["releases_at_start"] == ["company_intro", "metrics", "policy", "meeting_notes"]
    assert len(version) == 16

    # L=120, 3개(협업·책임·적응): 흐름 division·report_request, texture midpoint_draft
    three, _ = build_scenario(SCENARIOS, ["adaptability", "collaboration", "responsibility"], 120)
    assert _timeline(three) == [
        ("kickoff", 0),
        ("division", 10),
        ("collab_help", 30),
        ("responsibility_delay", 50),
        ("midpoint_draft", 60),
        ("adaptability_change", 70),
        ("review", 90),
        ("collab_disagree", 90),
        ("report_request", 110),
    ]
    assert {c["card_id"]: c for c in three["cards"]}["responsibility_delay"]["effects"][
        "release_at_min"
    ] == 60

    # L=120, 1개(계획성): 지연 없음 → 인터뷰 요약 시작 공개, 킥오프 "시작 시 공유됨"
    one, _ = build_scenario(SCENARIOS, ["planning"], 120)
    assert _timeline(one) == [
        ("kickoff", 0),
        ("planning_division", 10),
        ("planning_checkin", 30),
        ("review", 90),
        ("report_request", 110),
    ]
    assert one["vars"]["interview_expected_time"] == "시작 시 공유됨"
    assert "interview_summary" in one["releases_at_start"]

    # L=6, 5개 전부: 0.5, 1.5, 2.25, 3(공개 3.5), 3.75, 4.5, 5.5분
    short, _ = build_scenario(SCENARIOS, ALL_FIVE, 6)
    assert [at for card_id, at in _timeline(short) if card_id != "kickoff"] == [
        0.5,
        1.5,
        2.25,
        3,
        3.75,
        4.5,
        4.5,
        5.5,
    ]
    assert {c["card_id"]: c for c in short["cards"]}["responsibility_delay"]["effects"][
        "release_at_min"
    ] == 3.5


# rubric.md "카드별 레이블·보조 판정·근거 타입"과 "항목 정의" 표
RUBRIC_TABLE = {
    "planning_division": (
        ["assign_with_schedule", "assign_only", "defer_to_colleague", "ignore"],
        ["mentions_schedule"],
        ["task_event", "message"],
        ["plan_assigned_all_parts", "plan_stated_schedule"],
    ),
    "planning_checkin": (
        ["feedback", "acknowledge", "ignore"],
        [],
        ["open", "message"],
        ["plan_opened_draft", "plan_responded_draft"],
    ),
    "collab_help": (
        ["help_now", "negotiate_timing", "decline", "acknowledge_only", "ignore"],
        ["promised_t_min", "is_specific"],
        ["message"],
        ["collab_help_offered", "collab_help_kept_promise"],
    ),
    "collab_disagree": (
        ["explain_with_reason", "accept", "dismiss", "blame"],
        [],
        ["message"],
        ["collab_disagree_answered", "collab_disagree_reasoned_or_accepted"],
    ),
    "responsibility_delay": (
        ["notify_with_alternative", "notify_only", "silent", "ask_colleague"],
        ["mentions_impact", "has_alternative"],
        ["message", "doc_view"],
        [
            "resp_notified_before_release",
            "resp_mentioned_impact",
            "resp_proposed_alternative",
            "resp_told_manager",
        ],
    ),
    "adaptability_change": (
        ["replan_and_apply", "apply_silently", "complain_then_apply", "refuse_or_ignore"],
        ["target_applied", "mentions_scope"],
        ["message", "document", "share", "task_event"],
        [
            "adapt_applied_to_doc",
            "adapt_no_complaint_to_colleague",
            "adapt_redirected_colleague",
            "adapt_raised_scope",
        ],
    ),
    "honesty_report": (
        ["fair_report", "hides_incomplete", "misattributes", "no_report"],
        ["credits_colleague", "claims_colleague_work", "discloses_incomplete"],
        ["message"],
        [
            "honest_credited_colleague",
            "honest_disclosed_incomplete",
            "honest_no_misattribution",
            "honest_reported_within_10m",
        ],
    ),
}


def test_catalog_names_match_rubric_table():
    catalog = load_catalog(SCENARIOS)
    elements = catalog["cards"]["elements"]
    assert [e["id"] for e in elements] == ALL_FIVE
    found = {}
    for element in elements:
        assert sum(len(c["rubric"]) for c in element["cards"]) == 4
        assert element["meaning"] and element["how_we_see"]
        for card in element["cards"]:
            found[card["id"]] = (
                card["labels"],
                card["aux"],
                card["evidence_types"],
                [item["id"] for item in card["rubric"]],
            )
            assert set(card["label_texts"]) == set(card["labels"])
            assert all(
                item["basis"] in ("metric", "label")
                or (item["id"] == "plan_stated_schedule" and item["basis"] == "by_source")
                for item in card["rubric"]
            )
    assert found == RUBRIC_TABLE


def test_catalog_version_hashes_whole_mission_folder(tmp_path):
    copy = tmp_path / "scenarios"
    shutil.copytree(SCENARIOS, copy, ignore=shutil.ignore_patterns("e2e", "__pycache__"))
    before = catalog_version(copy)
    assert before == catalog_version(SCENARIOS)

    # 프롬프트 픽스처 본문만 바뀌어도 버전이 바뀐다
    fixture = copy / "missions" / "planning" / "prompts" / "fixtures" / "manager_dm.yaml"
    fixture.write_text(fixture.read_text(encoding="utf-8") + "\n# 수정\n", encoding="utf-8")
    assert catalog_version(copy) != before
