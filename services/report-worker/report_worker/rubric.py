"""평가표 계산. 순수 함수이고 LLM을 부르지 않는다. 규칙 정본은 docs/common/rubric.md.

카드의 `rubric[].when`(조건 문법 label_in·metric eq/lte·all, 그리고 only_if)을 그 카드 관찰 행의
label·metrics에 대입해 항목마다 1(충족)·0(미충족)·None(기록 없음 + 사유 코드)을 낸다.

| 관찰 상태 | label_in 조건 | metric 조건 |
|---|---|---|
| 카드 레이블 | 조건대로 | 조건대로 |
| unclassified·null(LLM 실패) | classify_failed | aux 지표 classify_failed, 기록 지표 조건대로 |
| no_evidence·관찰 행 없음 | 기록 없음 no_activity | 기록 없음 no_activity |

카드 미발생은 event_not_fired, 창을 놓친 카드는 window_missed, 카드가 보내야 할 동료 문서가 끝내
전송되지 않았으면(이벤트 document_missing 또는 draft_delivered=false) document_missing, 그 밖의
only_if 불충족은 not_applicable. aux에서 오는 지표(AUX_METRICS)가 null이면 classify_failed다.
response_minutes가 null인데 창 안 활동이 있으면 0이다.
"""

from typing import Any

NO_ACTIVITY = "no_activity"
CLASSIFY_FAILED = "classify_failed"
EVENT_NOT_FIRED = "event_not_fired"
NOT_APPLICABLE = "not_applicable"
WINDOW_MISSED = "window_missed"
DOCUMENT_MISSING = "document_missing"

NO_EVIDENCE = "no_evidence"
UNCLASSIFIED = "unclassified"
# LLM 분류의 aux에서 오는 지표(rubric.md 지표 정의). null이면 분류가 그 값을 내지 못한 것이다
AUX_METRICS = frozenset(
    {
        "mentions_colleague_impact",
        "proposes_alternative",
        "target_applied",
        "mentions_scope_or_division",
        "credits_colleague",
        "claims_colleague_work",
        "discloses_incomplete",
    }
)
# only_if가 이 지표로 불충족이면 사유는 not_applicable이 아니라 document_missing이다
DOCUMENT_METRICS = frozenset({"draft_delivered"})

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


def metric_value(observation: dict[str, Any] | None, name: str) -> tuple[Any, list[str]]:
    """metrics[name]은 observe가 남긴 {value, evidence_ids}. 값만 있는 행도 받는다."""
    raw = ((observation or {}).get("metrics") or {}).get(name)
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
    if state == UNCLASSIFIED and name in AUX_METRICS:
        # aux는 레이블과 함께 나온 분류 결과다. 분류가 실패했으면 값이 남아 있어도 쓰지 않는다
        return None, CLASSIFY_FAILED, []
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
    document_missing: bool = False,
) -> dict[str, Any]:
    """{id, auto, no_record_reason, evidence_ids}. 근거 id는 충족시킨 조건의 것."""

    def no_record(reason: str) -> dict[str, Any]:
        return {"id": item["id"], "auto": None, "no_record_reason": reason, "evidence_ids": []}

    if not event_fired:
        return no_record(EVENT_NOT_FIRED)
    if window_missed or missed_window(observation):
        return no_record(WINDOW_MISSED)
    if document_missing:
        return no_record(DOCUMENT_MISSING)
    if label_state(card, observation) in ("missing", NO_ACTIVITY):
        return no_record(NO_ACTIVITY)
    if item.get("only_if"):
        value, reason, _ = _condition(item["only_if"], card, observation)
        if value is None:
            return no_record(reason)
        if value == 0:
            used = {a.get("metric") for a in _atoms(item["only_if"])}
            return no_record(DOCUMENT_MISSING if used & DOCUMENT_METRICS else NOT_APPLICABLE)
    value, reason, ids = _condition(item["when"], card, observation)
    return {"id": item["id"], "auto": value, "no_record_reason": reason, "evidence_ids": ids}


def missed_window(observation: dict[str, Any] | None) -> bool:
    """observe가 남긴 `metrics.window_missed`({value: true, evidence_ids: []} 또는 bool)."""
    return observation is not None and metric_value(observation, "window_missed")[0] is True


def tally(values: list[int | None]) -> dict[str, int]:
    return {
        "met": sum(1 for v in values if v == 1),
        "unmet": sum(1 for v in values if v == 0),
        "no_record": sum(1 for v in values if v is None),
    }


def evaluate(
    card: dict[str, Any],
    observation: dict[str, Any] | None,
    *,
    event_fired: bool = True,
    window_missed: bool = False,
    document_missing: bool = False,
) -> list[dict[str, Any]]:
    """카드 하나의 항목 값들."""
    return [
        evaluate_item(
            item,
            card,
            observation,
            event_fired=event_fired,
            window_missed=window_missed,
            document_missing=document_missing,
        )
        for item in card.get("rubric") or []
    ]


def total(parts: list[dict[str, int]]) -> dict[str, int]:
    """세 수 합계. 가중치·정규화 없음."""
    return {key: sum(p[key] for p in parts) for key in ("met", "unmet", "no_record")}
