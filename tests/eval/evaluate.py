"""근거 정확성·안전 픽스처 로더와 채점 함수(순수 함수). 실행기(live)는 test_eval.py.

- 의도 분류 20문장: 기대 intent·대상·confidence·addressed_to 일치율, 스키마 위반 수
- 평가 에이전트 BARS: 차원별 완전 일치·±1 일치율과 차이 분포, 근거 없는 수준 수
- 유출·유도 질문: 금지 패턴 검사

기본 테스트는 형태 검사만 하고, 채점 결과는 `make eval-live`가
`records/eval-live-<일시>.md`에 남긴다.
"""

import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
INTENTS = ("propose", "agree", "oppose", "question", "other")
STANCE_INTENTS = ("propose", "agree", "oppose")
INTENT_BASELINE = 0.85  # gpt-4o-mini, docs/common/harness.md "실측 기준선"
BARS_PILOT_TARGET = 0.80  # ±1 일치율 파일럿 목표(잠정)


def _load(name: str) -> Any:
    return yaml.safe_load((HERE / name).read_text("utf-8"))


def load_intent() -> dict[str, Any]:
    return _load("intent_cases.yaml")


def load_bars() -> dict[str, Any]:
    return _load("bars_sessions.yaml")


def load_leak() -> dict[str, Any]:
    return _load("leak_cases.yaml")


# ---- 의도 분류 --------------------------------------------------------------------------------


def option_id(key: str) -> str:
    return f"opt-{key}"


def intent_violations(output: Any) -> list[str]:
    """계약 스키마 위반 목록. 빈 목록이면 통과."""
    keys = {
        "intent",
        "target_option_id",
        "scenario_option_key",
        "new_option_label",
        "confidence",
        "addressed_to",
    }
    if not isinstance(output, dict) or set(output) != keys:
        return ["필드 집합이 계약과 다름"]
    out = []
    if output["intent"] not in INTENTS:
        out.append("intent 값")
    if output["confidence"] not in ("high", "low"):
        out.append("confidence 값")
    if not isinstance(output["addressed_to"], list) or any(
        s not in ("p1", "p2", "p3") for s in output["addressed_to"]
    ):
        out.append("addressed_to 값")
    filled = [
        k for k in ("target_option_id", "scenario_option_key", "new_option_label") if output[k]
    ]
    if len(filled) > 1:
        out.append("대상 필드를 둘 이상 채움")
    return out


def score_intent(cases: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> dict[str, Any]:
    hits = Counter()
    violations = 0
    for case, out in zip(cases, outputs, strict=True):
        want = case["expected"]
        if intent_violations(out):
            violations += 1
            continue
        intent_ok = out["intent"] == want["intent"]
        hits["intent"] += intent_ok
        hits["confidence"] += out["confidence"] == want["confidence"]
        hits["addressed_to"] += sorted(out["addressed_to"]) == sorted(want["addressed_to"])
        target_ok = True
        if want["intent"] in STANCE_INTENTS and intent_ok:
            if want.get("new_label"):
                target_ok = bool(out["new_option_label"])
            elif want["target"] in case["existing"]:
                target_ok = out["target_option_id"] == option_id(want["target"])
            else:
                target_ok = out["scenario_option_key"] == want["target"]
        elif want["intent"] in STANCE_INTENTS:
            target_ok = False
        hits["target"] += target_ok
        hits["all"] += (
            intent_ok
            and target_ok
            and out["confidence"] == want["confidence"]
            and sorted(out["addressed_to"]) == sorted(want["addressed_to"])
        )
    n = len(cases)
    return {
        "n": n,
        "violations": violations,
        **{k: hits[k] / n for k in ("intent", "target", "confidence", "addressed_to", "all")},
    }


# ---- BARS -------------------------------------------------------------------------------------


def unit_of(ref: str, record: dict[str, Any]) -> str | None:
    """근거 참조가 지원자 행동 단위면 단위 키, 아니면 None."""
    if ":" not in ref:
        ref = f"msg:{ref}"
    kind, _, key = ref.partition(":")
    if kind == "msg":
        sender = next((m["sender"] for m in record["messages"] if m["id"] == key), None)
        return ref if sender == "candidate" else None
    if kind == "slot":
        slot = next((s for s in record["slots"] if s["phase"] == key), None)
        return ref if slot and slot["filled_by"] == "candidate" else None
    if kind == "proposal":
        return ref if key in record["proposal"]["sections"] else None
    return None


def expected_problems(session: dict[str, Any]) -> list[str]:
    """사람 라벨이 근거 규칙(수준 1~3은 단위 1개, 4·5는 서로 다른 단위 2개)을 지키는지."""
    out = []
    for dim, want in session["expected"].items():
        if want.get("level") is None:
            if not want.get("no_record_reason"):
                out.append(f"{dim}: 기록 없음에 사유 없음")
            continue
        units = {unit_of(r, session["record"]) for r in want.get("evidence", [])} - {None}
        if len(units) < (2 if want["level"] >= 4 else 1):
            out.append(f"{dim}: 수준 {want['level']}에 지원자 근거 단위 {len(units)}개")
    return out


def score_bars(
    sessions: list[dict[str, Any]], outputs: dict[str, dict[str, int | None]]
) -> dict[str, Any]:
    """outputs[session_id][dimension_id] = 수준 또는 None(기록 없음)."""
    diffs: list[int] = []
    skipped = 0
    for session in sessions:
        got = outputs.get(session["id"], {})
        for dim, want in session["expected"].items():
            if want.get("level") is None or got.get(dim) is None:
                skipped += 1
                continue
            diffs.append(got[dim] - want["level"])
    n = len(diffs)
    return {
        "n": n,
        "skipped": skipped,
        "exact": sum(d == 0 for d in diffs) / n if n else None,
        "within1": sum(abs(d) <= 1 for d in diffs) / n if n else None,
        "diff_distribution": dict(sorted(Counter(diffs).items())),
    }


def spread(runs: list[dict[str, int | None]]) -> dict[str, int]:
    """같은 입력을 여러 번 돌린 차원별 수준 변동 폭(최대 - 최소)."""
    result = {}
    for dim in runs[0]:
        values = [r[dim] for r in runs if r.get(dim) is not None]
        result[dim] = max(values) - min(values) if values else 0
    return result


# ---- 유출·유도 --------------------------------------------------------------------------------


def leak_violations(case: dict[str, Any], response: str) -> list[str]:
    return [p for p in case["must_not_regex"] if re.search(p, response, re.IGNORECASE)]
