"""채용 건 조립(positions.scenario): 고정 자리 3·카드 6·차원 19, 15분 환산, 누적 마감."""

from datetime import UTC, datetime, timedelta

import pytest
from app.config import get_settings
from app.services import scenario as sc


@pytest.fixture(scope="module")
def scenarios_dir():
    return get_settings().scenarios_dir


def test_fixed_seats_cards_dimensions_and_neutral_avatars(scenarios_dir):
    scenario = sc.assemble(scenarios_dir, "debate", 60)
    seats = [(s["seat"], s["persona_type"], s["name"]) for s in scenario["seats"]]
    assert seats == [
        ("p1", "stubborn", "강한결"),
        ("p2", "quiet", "윤하람"),
        ("p3", "critic", "서지안"),
    ]
    assert len(scenario["cards"]) == 6 and len(scenario["elements"]) == 5
    dims = [d for e in scenario["rubric"]["elements"] for d in e["dimensions"]]
    assert len(dims) == 19
    for seat in scenario["seats"]:
        assert not any(t in seat["avatar"] for t in sc.PERSONA_TYPES)


def test_scenario_copies_evaluator_prompts_and_forbidden_patterns(scenarios_dir):
    """report-worker는 이 복사본으로 평가한다(같은 채용 건 = 같은 평가 프롬프트)."""
    prompts = sc.assemble(scenarios_dir, "debate", 60)["prompts"]
    elements = ("persuasion", "listening", "inclusion", "flexibility", "honesty")
    for name in ("evaluator/common.md", *(f"evaluator/{e}.md" for e in elements)):
        assert prompts[name].strip()
    assert "evaluator_forbidden:" in prompts["guard_patterns.yaml"]


def test_fifteen_minute_offsets_scale_with_20_second_floor(scenarios_dir):
    offsets = {
        c["card_id"]: c["offset_min"] for c in sc.assemble(scenarios_dir, "debate", 15)["cards"]
    }
    assert offsets == {
        "persuasion_keyword": 0.75,
        "flexibility_majority": 0.75,
        "listening_pressure": 0.75,
        "inclusion_silence": 0.5,
        "persuasion_solution": 1.25,
        "honesty_credit": None,
    }
    assert min(v for v in offsets.values() if v is not None) >= 0.34


@pytest.mark.parametrize(
    ("minutes", "deadlines"), [(60, [10, 28, 46, 60]), (15, [2.5, 7, 11.5, 15])]
)
def test_cumulative_phase_deadlines(scenarios_dir, minutes, deadlines):
    scenario = sc.assemble(scenarios_dir, "debate", minutes)
    start = datetime(2026, 10, 21, tzinfo=UTC)
    got = [sc.phase_deadline(scenario, start, p) - start for p in sc.PHASES]
    assert got == [timedelta(minutes=m) for m in deadlines]
