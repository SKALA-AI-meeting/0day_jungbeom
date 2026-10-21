"""러너 happy path(mock): 계약만으로 만든 가짜 api 위에서 대본을 끝까지 돌려 단언이 통과하는지 본다.

가짜 api(fake_stack.py)는 agent의 결정적 LLM 모드와 같은 규칙으로 말하므로, 여기서 통과한다는 것은
러너의 진행·수집·단언 로직이 계약대로 동작한다는 뜻이다(서비스 구현 검증은 실 스택 실행 몫).
"""

import copy
import json

import pytest

from e2e import asserts, records
from e2e import script as scripts
from e2e.run import Runner


async def run_script(fake, target, name: str, **kwargs):
    runner = Runner(
        scripts.load(name),
        target,
        clock="fake",
        stack=fake,
        transports=fake.transports,
        connector=fake.connector(),
        db=fake.db(),
        typing_hold=0.05,
        poll=0.02,
        report_wait=5,
        **kwargs,
    )
    bundle = await runner.run()
    bundle["results"] = asserts.check(bundle)
    return bundle


def failures(bundle) -> dict[str, list[str]]:
    return {r["id"]: r["failures"] for r in bundle["results"] if not r["ok"]}


@pytest.mark.parametrize("name", ["all_five", "timeout_all", "honesty_claim", "restart"])
async def test_script_passes(fake, target, tmp_path, name):
    bundle = await run_script(fake, target, name)
    assert failures(bundle) == {}
    path = records.write(bundle, tmp_path)
    for file in (
        "transcript.jsonl",
        "turn_decisions.json",
        "evaluations.json",
        "report_draft.json",
        "report_final.json",
        "record.json",
        "summary.md",
    ):
        assert (path / file).is_file(), file
    kinds = {
        json.loads(line)["kind"]
        for line in (path / "transcript.jsonl").read_text("utf-8").splitlines()
    }
    assert {"rest", "ws_in", "ws_out"} <= kinds
    assert "<redacted>" in (path / "transcript.jsonl").read_text("utf-8")
    assert "| 5 | 리포트 | 통과 |" in (path / "summary.md").read_text("utf-8")


async def test_all_five_flow(fake, target):
    """all_five가 실제로 전 흐름을 밟았는지: 칸 3개 조합, 카드 6장, 검토 병합."""
    bundle = await run_script(fake, target, "all_five")
    slots = asserts.slots_by_phase(bundle)
    assert [
        (slots[p]["filled_by"], slots[p]["resolution"]) for p in ("keyword", "problem", "solution")
    ] == [
        ("candidate", "consensus"),
        ("p3", "consensus"),
        ("p3", "consensus"),
    ]
    assert len(bundle["observations"]) == 6
    assert bundle["review"]["approve"] == 200
    assert bundle["final"]["stage"] == "final"
    assert bundle["measure"]["first_persona_p95_sec"] is not None


async def test_broken_contract_is_reported(fake, target):
    """단언이 실제로 걸러 내는지: 근거 없는 수준·총점 필드를 심으면 5가 실패한다."""
    bundle = await run_script(fake, target, "timeout_all")
    draft = bundle["draft"]
    draft["dimensions"][0]["evidence_refs"] = []
    draft["total_score"] = 3.2
    assert not asserts.check(bundle)[5]["ok"]


def _typing(b):
    frame = next(
        f for f in b["frames"] if f["type"] == "message.new" and f["payload"]["sender"] == "p1"
    )
    b["typing_intervals"].append((frame["_at"] - 1, frame["_at"] + 1))


def _three_speakers(b):
    b["runs"][0]["decision"]["speakers"] = [{"seat": "p1"}, {"seat": "p2"}, {"seat": "p3"}]


def _fill_without_candidate(b):
    slot = next(s for s in b["slots"] if s["filled_by"] == "p3")
    slot["support"] = [{"option_id": slot["option_id"], "supporters": ["p1", "p3"]}]


def _drop_card(b):
    b["observations"] = [o for o in b["observations"] if o["card_id"] != "inclusion_silence"]


def _preempt(b):
    quiet_card = next(o for o in b["observations"] if o["card_id"] == "inclusion_silence")
    b["messages"].append(
        {
            "id": "x",
            "sender": "p3",
            "content": "하람님 의견은요?",
            "phase": "solution",
            "t_min": quiet_card["t_min"] + 0.1,
            "is_invite": False,
            "card_ids": [],
            "meta": {},
        }
    )


def _shift_deadline(b):
    b["advances"].append({"at": 0.0, "seconds": 120})


def _readjust_accepted(b):
    b["review"]["readjust"] = 200


def _quiet_unprompted(b):
    b["messages"].append(
        {
            "id": "y",
            "sender": "p2",
            "content": "제 생각은요",
            "phase": "keyword",
            "t_min": 0.1,
            "is_invite": False,
            "card_ids": [],
            "meta": {},
        }
    )


VIOLATIONS = [
    ("2", _typing),
    ("2", _three_speakers),
    ("2", _fill_without_candidate),
    ("2", _quiet_unprompted),
    ("3", _drop_card),
    ("4", _preempt),
    ("1", _shift_deadline),
    ("6", _readjust_accepted),
]


@pytest.mark.parametrize(("number", "mutate"), VIOLATIONS, ids=[m.__name__ for _, m in VIOLATIONS])
async def test_each_assertion_catches_its_violation(fake, target, number, mutate):
    bundle = await run_script(fake, target, "all_five")
    assert failures(bundle) == {}
    broken = copy.deepcopy(bundle)
    mutate(broken)
    assert not {r["id"]: r for r in asserts.check(broken)}[number]["ok"]
