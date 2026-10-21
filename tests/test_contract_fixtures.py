"""계약 픽스처 검사(G-C): 모든 픽스처가 contract_shape의 형태에 맞고 web mock 복사본과 같다."""

import importlib.util
import json
from pathlib import Path

import pytest

# tests/는 패키지가 아니라 서비스 테스트와 같은 방식(파일 경로)으로 읽는다
_spec = importlib.util.spec_from_file_location(
    "contract_shape", Path(__file__).resolve().parent / "contract_shape.py"
)
cs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cs)

WEB_FIXTURES = Path(__file__).resolve().parents[1] / "apps" / "web" / "mocks" / "fixtures"
WEB_ONLY = {"office_script.json", "debate_script.json"}  # mock-candidate 소유 재생 대본
NAMES = sorted(p.stem for p in cs.CONTRACTS.glob("*.json"))


def test_every_fixture_has_a_shape():
    assert set(NAMES) == set(cs.SHAPES) | {"mcp_tools"}


@pytest.mark.parametrize("name", sorted(cs.SHAPES))
def test_fixture_matches_contract(name):
    cs.validate(cs.load_contract(name), cs.SHAPES[name], name)


def test_mcp_tools_match_contract():
    cs.validate_mcp_tools(cs.load_contract("mcp_tools"))


def test_report_and_evaluation_cover_all_dimensions():
    for dims in (
        cs.load_contract("report")["dimensions"],
        cs.load_contract("evaluation_save")["dimensions"],
    ):
        assert [d["dimension_id"] for d in dims] == list(cs.DIMENSION_IDS)
        for d in dims:
            assert (d["level"] is None) == (d.get("no_record_reason") is not None)
    assert len(cs.load_contract("report")["elements"]) == 5


def test_ws_seq_is_continuous():
    seqs = [f["seq"] for f in cs.load_contract("ws_events")]
    assert seqs == list(range(1, len(seqs) + 1))


def test_web_mock_copies_are_identical():
    web = {p.name for p in WEB_FIXTURES.glob("*.json")} - WEB_ONLY
    assert web == {f"{n}.json" for n in NAMES}
    for name in NAMES:
        assert json.loads((WEB_FIXTURES / f"{name}.json").read_text(encoding="utf-8")) == (
            cs.load_contract(name)
        ), name


def test_persona_type_hidden_from_candidate_fixtures():
    prefixes = ("entry", "state_", "material", "assistant", "proposal", "ws_", "slot_")
    candidate = [n for n in NAMES if n.startswith(prefixes) or n in ("consent", "resume", "start")]
    for name in candidate:
        text = (cs.CONTRACTS / f"{name}.json").read_text(encoding="utf-8")
        for word in ("stubborn", "quiet", "critic", "agreeable", "divergent"):
            assert word not in text, f"{name}: {word}"
