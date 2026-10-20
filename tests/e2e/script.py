"""e2e 대본(scenarios/e2e/*.yaml) 읽기. step 키는 scenarios/e2e/README.md 표가 정본이다."""

from pathlib import Path
from typing import Any

import yaml

E2E_DIR = Path(__file__).resolve().parents[2] / "scenarios" / "e2e"

# 한 step에 여러 키가 있으면 이 순서로 실행한다(README 표 순서)
ACTIONS = (
    "board",
    "say",
    "write",
    "share",
    "open",
    "import",
    "view",
    "assistant",
    "submit",
    "restart",
    "disconnect",
    "inject",
)
STEP_KEYS = {"at", "capture_as", *ACTIONS}


def load(name_or_path: str | Path) -> dict[str, Any]:
    """대본 이름(all_five) 또는 경로. 모르는 step 키는 오타일 수 있어 바로 실패시킨다."""
    path = Path(name_or_path)
    if not path.suffix:
        path = E2E_DIR / f"{name_or_path}.yaml"
    script = yaml.safe_load(path.read_text("utf-8"))
    for index, step in enumerate(script["steps"]):
        unknown = set(step) - STEP_KEYS
        if unknown or "at" not in step:
            raise ValueError(f"{path.name} step {index}: unknown keys {sorted(unknown)} or no at")
    return script


def actions(step: dict[str, Any]) -> list[str]:
    return [key for key in ACTIONS if key in step]
