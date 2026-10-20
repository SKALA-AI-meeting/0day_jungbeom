"""평가표 계산. 순수 함수이고 LLM을 부르지 않는다. 규칙 정본은 docs/common/rubric.md.

카드의 `rubric[].when`(조건 문법 label_in·metric eq/lte·all, 그리고 only_if)을 관찰 행의
label·metrics에 대입해 항목마다 1(충족)·0(미충족)·None(기록 없음 + 사유)을 낸다.

| 관찰 상태 | label_in 조건 | metric 조건 |
|---|---|---|
| 카드 레이블 | 조건대로 | 조건대로 |
| unclassified·null(LLM 실패) | 기록 없음 classify_failed | 조건대로(값이 null이면 기록 없음) |
| no_evidence·관찰 행 없음 | 기록 없음 no_activity | 기록 없음 no_activity |

카드 미발생은 event_not_fired, 창을 놓친 카드(전달 지연 또는 관찰의 `metrics.window_missed`)는
window_missed, only_if 불충족은 not_applicable. aux 판정 지표(AUX_METRICS)가 null이면 레이블이
정상이어도 classify_failed다. response_minutes가 null인데 창 안 활동이 있으면 0이다.
근거는 충족 항목에만 붙인다.
"""

from typing import Any

NO_ACTIVITY = "no_activity"
CLASSIFY_FAILED = "classify_failed"
EVENT_NOT_FIRED = "event_not_fired"
NOT_APPLICABLE = "not_applicable"
WINDOW_MISSED = "window_missed"

NO_EVIDENCE = "no_evidence"
# LLM 분류의 aux에서 오는 지표. null이면 분류가 그 값을 내지 못한 것이다
AUX_METRICS = frozenset({"response_specific", "proposes_alternative", "proposes_fix"})
UNCLASSIFIED = "unclassified"

# (값, 기록 없음 사유, 근거 id). 값이 None일 때만 사유가 있다.
Result = tuple[int | None, str | None, list[str]]


def label_state(card: dict[str, Any], observation: dict[str, Any] | None) -> str:
    """missing(관찰 행 없음) · no_activity · unclassified(null·허용 밖 포함) · labeled."""
    if observation is None:
        return "missing"
    label = observation.get("label")
    if label == NO_EVIDENCE:
        return NO_ACTIVITY
    if label in (card.get("labels") or []):
        return "labeled"
    return UNCLASSIFIED


def metric_value(observation: dict[str, Any], name: str) -> tuple[Any, list[str]]:
    """metrics[name]은 observe가 남긴 {value, evidence_ids}. 값만 있는 행도 받는다."""
    raw = (observation.get("metrics") or {}).get(name)
    if isinstance(raw, dict) and "value" in raw:
        return raw["value"], [str(i) for i in raw.get("evidence_ids") or []]
    return raw, []


def _atoms(cond: dict[str, Any]) -> list[dict[str, Any]]:
    """한 조건을 원자 조건 목록으로 편다. label_in과 metric이 함께 있으면 둘 다 충족해야 한다."""
    atoms: list[dict[str, Any]] = []
    for sub in cond.get("all") or []:
        atoms.extend(_atoms(sub))
    if "label_in" in cond:
        atoms.append({"label_in": cond["label_in"]})
    if "metric" in cond:
        atoms.append({k: cond[k] for k in ("metric", "eq", "lte") if k in cond})
    return atoms


def _atom(atom: dict[str, Any], card: dict[str, Any], observation: dict[str, Any]) -> Result:
    state = label_state(card, observation)
    if "label_in" in atom:
        if state != "labeled":
            return None, CLASSIFY_FAILED, []
        value = int(observation["label"] in atom["label_in"])
        ids = [str(e["id"]) for e in observation.get("evidence") or []]
        return value, None, ids

    name = atom["metric"]
    value, ids = metric_value(observation, name)
    if value is None:
        if name == "response_minutes":
            return 0, None, []  # 창 안 활동은 있는데 관련 메시지가 없음
        failed = state == UNCLASSIFIED or name in AUX_METRICS
        return None, CLASSIFY_FAILED if failed else NO_ACTIVITY, []
    if "eq" in atom:
        return int(value == atom["eq"]), None, ids
    if "lte" in atom:
        return int(isinstance(value, int | float) and value <= atom["lte"]), None, ids
    raise ValueError(f"unknown metric condition: {atom}")


def _condition(cond: dict[str, Any], card: dict[str, Any], observation: dict[str, Any]) -> Result:
    results = [_atom(a, card, observation) for a in _atoms(cond)]
    if not results:
        raise ValueError(f"empty condition: {cond}")
    for value, reason, _ in results:
        if value is None:
            return None, reason, []
    value = min(v for v, _, _ in results)
    ids = [i for _, _, found in results for i in found] if value == 1 else []
    return value, None, list(dict.fromkeys(ids))


def evaluate_item(
    item: dict[str, Any],
    card: dict[str, Any],
    observation: dict[str, Any] | None,
    *,
    event_fired: bool = True,
    window_missed: bool = False,
) -> dict[str, Any]:
    def no_record(reason: str) -> dict[str, Any]:
        return {"id": item["id"], "auto": None, "no_record_reason": reason, "evidence_ids": []}

    if not event_fired:
        return no_record(EVENT_NOT_FIRED)
    if window_missed or missed_window(observation):
        return no_record(WINDOW_MISSED)
    if label_state(card, observation) in ("missing", NO_ACTIVITY):
        return no_record(NO_ACTIVITY)
    if item.get("only_if"):
        value, reason, _ = _condition(item["only_if"], card, observation)
        if value is None:
            return no_record(reason)
        if value == 0:
            return no_record(NOT_APPLICABLE)
    value, reason, ids = _condition(item["when"], card, observation)
    return {"id": item["id"], "auto": value, "no_record_reason": reason, "evidence_ids": ids}


def missed_window(observation: dict[str, Any] | None) -> bool:
    """observe가 남긴 `metrics.window_missed`({value: true, evidence_ids: []} 또는 bool)."""
    return observation is not None and metric_value(observation, "window_missed")[0] is True


def tally(values: list[int | None]) -> dict[str, int]:
    return {
        "met": sum(1 for v in values if v == 1),
        "judged": sum(1 for v in values if v in (0, 1)),
        "no_record": sum(1 for v in values if v is None),
    }


def evaluate(
    card: dict[str, Any],
    observation: dict[str, Any] | None,
    *,
    event_fired: bool = True,
    window_missed: bool = False,
) -> dict[str, Any]:
    """요소 하나의 항목 값과 합계.

    {items: [{id, auto, no_record_reason, evidence_ids}], auto: {met, judged, no_record}}
    """
    items = [
        evaluate_item(item, card, observation, event_fired=event_fired, window_missed=window_missed)
        for item in card.get("rubric") or []
    ]
    return {"items": items, "auto": tally([i["auto"] for i in items])}


def total(elements: list[dict[str, int]]) -> dict[str, int]:
    """선택 요소 합계. 가중치·정규화 없음."""
    return {key: sum(e[key] for e in elements) for key in ("met", "judged", "no_record")}
