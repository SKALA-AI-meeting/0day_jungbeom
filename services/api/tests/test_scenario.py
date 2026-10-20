"""완료 기준: 조립 결과가 docs/common/scenario-model.md 수치와 일치."""

from app.services.scenario import build_scenario

from tests.conftest import SCENARIOS

ALL_FOUR = ["cooperation", "responsibility", "flexibility", "respect"]


def _timeline(scenario):
    return [(c["card_id"], c["at_min"]) for c in scenario["cards"]]


def test_assembled_timeline_matches_scenario_model():
    scenario, version = build_scenario(SCENARIOS, ALL_FOUR, 120)

    # L=120, 4개 선택: 저장 형식 예시 그대로
    assert scenario["session_minutes"] == 120
    assert _timeline(scenario) == [
        ("kickoff", 0),
        ("division", 10),
        ("cooperation", 30),
        ("responsibility", 50),
        ("midpoint_draft", 60),
        ("flexibility", 70),
        ("review", 90),
        ("respect", 90),
        ("report_request", 110),
    ]
    cards = {c["card_id"]: c for c in scenario["cards"]}
    assert cards["responsibility"]["effects"] == {
        "release_document": "interview_summary",
        "at_min": 65,
    }
    assert cards["midpoint_draft"]["texture"] is True
    assert cards["respect"]["element"] == "respect"
    assert cards["respect"]["attach_to"] == "review"
    assert scenario["releases_at_start"] == ["company_intro", "metrics", "policy", "meeting_notes"]
    assert len(version) == 16

    # L=120, 3개(협력·책임·유연): 30, 50, 70
    three, _ = build_scenario(SCENARIOS, ["flexibility", "cooperation", "responsibility"], 120)
    assert [(c["card_id"], c["at_min"]) for c in three["cards"] if c.get("element")] == [
        ("cooperation", 30),
        ("responsibility", 50),
        ("flexibility", 70),
    ]

    # L=6, 4개: 1.5, 2.5, 3.5, 4.5분
    short, _ = build_scenario(SCENARIOS, ALL_FOUR, 6)
    assert [c["at_min"] for c in short["cards"] if c.get("element")] == [1.5, 2.5, 3.5, 4.5]
