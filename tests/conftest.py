"""저장소 루트 tests/(연결·e2e) 공용 픽스처.

서비스 단위 테스트는 각 services/<이름>/tests/에 있다.
"""

import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = REPO_ROOT / "tests" / "fixtures" / "contracts"


def load_contract(name: str) -> Any:
    """tests/fixtures/contracts/<name>.json (contracts.md 예시)."""
    return json.loads((CONTRACTS / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def contract():
    return load_contract


@pytest.fixture(scope="session")
def scenarios_dir() -> Path:
    return REPO_ROOT / "scenarios"
