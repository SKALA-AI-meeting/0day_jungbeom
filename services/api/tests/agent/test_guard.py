"""완료 기준: guard 예문 48건(guard_patterns.yaml의 hit·miss 45건 + 안내문 3건).

hit은 자기 그룹에 걸리고 apply 결과가 그 그룹의 안내문이 된다. miss와 안내문은 어느 그룹에도 걸리지
않고 apply가 문장을 그대로 둔다(안내문이 다시 치환되지 않음).
"""

import pytest
import yaml
from app.agent.guard import Guard
from app.config import REPO_ROOT

SPEC = yaml.safe_load(
    (
        REPO_ROOT / "scenarios" / "missions" / "planning" / "prompts" / "guard_patterns.yaml"
    ).read_text(encoding="utf-8")
)
GUARD = Guard(SPEC)


def _cases():
    for group in SPEC["groups"]:
        for sentence in group["examples"]["hit"]:
            yield pytest.param(group["id"], sentence, id=f"hit-{group['id']}-{sentence}")
        for sentence in group["examples"]["miss"]:
            yield pytest.param(None, sentence, id=f"miss-{group['id']}-{sentence}")
    for key, notice in SPEC["notices"].items():
        yield pytest.param(None, notice, id=f"notice-{key}")


@pytest.mark.parametrize(("group_id", "sentence"), list(_cases()))
def test_guard_example(group_id, sentence):
    result = GUARD.apply(sentence)
    if group_id is None:
        assert GUARD.groups_hit(sentence) == []
        assert result.text == sentence and result.hits == ()
    else:
        assert group_id in GUARD.groups_hit(sentence)
        replacement = next(g["replacement"] for g in SPEC["groups"] if g["id"] == group_id)
        assert result.text == SPEC["notices"][replacement]
