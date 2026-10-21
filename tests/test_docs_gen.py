"""scripts/docs_gen.py의 생성 블록 마커 검사."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("docs_gen", ROOT / "scripts" / "docs_gen.py")
docs_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(docs_gen)

OK = "a\n<!-- gen:api -->\nx\n<!-- /gen:api -->\nb\n<!-- gen:tests -->\ny\n<!-- /gen:tests -->\n"


def test_committed_readmes_have_required_marker_pairs():
    for readme, required in docs_gen.REQUIRED_BLOCKS.items():
        text = (ROOT / readme).read_text(encoding="utf-8")
        assert docs_gen.marker_problems(text, required) == [], readme


def test_marker_problems_catch_missing_or_mismatched_markers():
    req = ("api", "tests")
    assert docs_gen.marker_problems(OK, req) == []
    assert docs_gen.marker_problems(OK.replace("<!-- /gen:tests -->", "<!-- /gen:test -->"), req)
    assert docs_gen.marker_problems(OK.replace("<!-- gen:api -->\nx\n<!-- /gen:api -->\n", ""), req)
    swapped = OK.replace("<!-- gen:api -->", "@").replace("<!-- /gen:api -->", "<!-- gen:api -->")
    assert docs_gen.marker_problems(swapped.replace("@", "<!-- /gen:api -->"), req)
