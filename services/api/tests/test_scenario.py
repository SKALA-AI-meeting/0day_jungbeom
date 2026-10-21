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


def _edit(path, old, new):
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


def test_catalog_reads_position_snapshot_not_current_files(tmp_path, scenarios_dir, caplog):
    """채용 건 생성 뒤 미션 YAML이 바뀌어도 그 채용 건은 생성 때 입장·카드·후보로 진행한다."""
    import logging
    import shutil

    from app.agent.catalog import Catalog

    root = tmp_path / "scenarios"
    shutil.copytree(scenarios_dir, root)
    mission = root / "missions" / "debate"
    old = sc.assemble(root, "debate", 15)

    _edit(mission / "personas.yaml", "keyword: { push: fire }", "keyword: { push: water }")
    _edit(mission / "keywords.yaml", "label: 노후 주택·전통시장 화재", "label: 바뀐 후보")
    cards = mission / "cards.yaml"
    first_card = Catalog.from_dir(mission).cards["cards"][0]["card_id"]
    _edit(cards, f"card_id: {first_card}", "card_id: renamed_card")
    new = sc.assemble(root, "debate", 15)

    pinned = Catalog.from_scenario(old, root)
    assert pinned.persona("p1")["stances"]["keyword"]["push"] == "fire"
    assert pinned.label_of("fire_p1") == "노후 주택·전통시장 화재"
    assert pinned.card(first_card) is not None and pinned.card("renamed_card") is None

    fresh = Catalog.from_scenario(new, root)
    assert fresh.persona("p1")["stances"]["keyword"]["push"] == "water"
    assert fresh.label_of("fire_p1") == "바뀐 후보"
    assert fresh.card("renamed_card") is not None

    # 옛 채용 건(catalog 없음): 스케줄러·합의가 읽는 기존 복사본과 같은 기준으로 재구성한다
    legacy = {k: v for k, v in old.items() if k != "catalog"}
    with caplog.at_level(logging.INFO, logger="app.agent.catalog"):
        rebuilt = Catalog.from_scenario(legacy, root)
    assert rebuilt.persona("p1")["stances"]["keyword"]["push"] == "fire"
    assert rebuilt.label_of("fire_p1") == "노후 주택·전통시장 화재"
    assert [c["card_id"] for c in rebuilt.cards["cards"]] == [c["card_id"] for c in old["cards"]]
    assert rebuilt.mission["lead_option"] == old["lead_option"]
    assert rebuilt.mission["consensus_fill"]["filler_priority"] == old["fill_priority"]
    assert not any("scenario copy lacks" in r.message for r in caplog.records)  # 파일을 읽지 않음

    # 복사본에 없는 부분(프롬프트)만 현재 파일에서 채우고, 카탈로그 버전이 다르면 경고
    caplog.clear()
    no_prompts = {k: v for k, v in legacy.items() if k != "prompts"}
    with caplog.at_level(logging.INFO, logger="app.agent.catalog"):
        filled = Catalog.from_scenario(no_prompts, root)
    assert filled.persona("p1")["stances"]["keyword"]["push"] == "fire"
    assert filled.prompts["intent.md"] == old["prompts"]["intent.md"]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "catalog_version" in warnings[0].message
