"""평가 에이전트: 요소별 LLM 호출, 워커 검증, 요소 단위 1회 재요청, 확신도 clamp, 요소 수준.

규칙 정본은 `docs/common/rubric.md` 2.2·2.4·7.3과 `contracts.md` EvaluationSave·검증 경계다.

- 요소마다 별도 호출(5회). 입력은 그 요소의 척도·지침과 세션 기록 전체뿐이고 다른 요소의 결과는
  넣지 않는다(후광 방지).
- 형식 오류(파싱·스키마·차원 누락·중복·없는 차원), 근거 부재(수준이 있는데 같은 세션의 실제 행인
  지원자 근거가 최소 개수 미만), 금지어가 하나라도 있으면 그 요소 호출 전체를 실패 사유와 함께
  1회 다시 요청한다. 재요청 결과에서도 실패한 차원만 `evaluate_failed`로 두고 나머지는 재요청
  결과를 쓴다. 워커는 수준·근거를 고쳐 쓰지 않는다.
- 확신도 상한 위반은 거부하지 않고 상한으로 깎는다(clamp).
- LLM 전송 오류·타임아웃은 여기서 잡지 않는다(저장 없이 큐 재시도).
검증·clamp·요소 수준은 순수 함수라 단위 테스트한다.
"""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from report_worker.llm import LLM, complete_tracked

ELEMENTS = ("persuasion", "listening", "inclusion", "flexibility", "honesty")
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
# 모델이 쓸 수 있는 기록 없음 사유. evaluate_failed는 워커만 쓴다
MODEL_REASONS = frozenset(
    {"no_activity", "not_applicable", "event_not_fired", "auto_submitted_blank"}
)
CREDIT_DIMENSION = "hon_credit_record"  # contribution 참조도 근거 개수에 드는 예외(rubric.md 3.5)
FAILED_SUMMARY = "시스템: 판단 실패로 요약이 없습니다"
FAILED_RATIONALE = (
    "형식 오류 또는 근거 부재로 이 요소를 1회 다시 요청했지만 유효한 판단이 나오지 않았습니다."
)
REF_PATTERN = re.compile(r"^(msg|slot|proposal|contribution):(.+)$")


# ---- 프롬프트·금지어 (카탈로그 파일) -------------------------------------------------------------


@dataclass(frozen=True)
class Prompts:
    common: str
    elements: dict[str, str]
    versions: dict[str, str]  # {common: 해시, <element>: 해시}


def _digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def load_prompts(scenarios_dir: Path, mission_id: str) -> Prompts:
    folder = Path(scenarios_dir) / "missions" / mission_id / "prompts" / "evaluator"
    common = (folder / "common.md").read_text(encoding="utf-8")
    elements = {e: (folder / f"{e}.md").read_text(encoding="utf-8") for e in ELEMENTS}
    versions = {"common": _digest(common), **{e: _digest(t) for e, t in elements.items()}}
    return Prompts(common, elements, versions)


def load_forbidden(scenarios_dir: Path, mission_id: str) -> list[re.Pattern]:
    path = Path(scenarios_dir) / "missions" / mission_id / "prompts" / "guard_patterns.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [re.compile(p) for p in data["evaluator_forbidden"]["patterns"]]


def has_forbidden(text: str, forbidden: list[re.Pattern]) -> bool:
    return any(p.search(text) for p in forbidden)


# ---- 근거 참조 ---------------------------------------------------------------------------------


class RefIndex:
    """같은 세션의 실제 행과 근거 개수 규칙(rubric.md 2.2, 3.5 예외)."""

    def __init__(self, record: dict[str, Any], contributions: dict[str, Any]) -> None:
        self.message_sender = {m["id"]: m["sender"] for m in record.get("messages", [])}
        self.slot_filled_by = {s["phase"]: s.get("filled_by") for s in record.get("slots", [])}
        sections = ((record.get("proposal") or {}).get("sections")) or {}
        self.proposal_fields = set(sections)
        self.option_ids = {o["option_id"] for o in contributions.get("options", [])}

    def exists(self, ref: Any) -> bool:
        if not isinstance(ref, str):
            return False
        match = REF_PATTERN.match(ref)
        if not match:
            return False
        kind, key = match.groups()
        if kind == "msg":
            return key in self.message_sender
        if kind == "slot":
            return key in self.slot_filled_by
        if kind == "proposal":
            return key in self.proposal_fields
        return key in self.option_ids

    def counted(self, ref: str, dimension_id: str) -> bool:
        """지원자 행동 단위만 센다. AI·시스템 메시지와 contribution은 맥락(정직 기여 기록 예외)."""
        kind, key = ref.split(":", 1)
        if kind == "msg":
            return self.message_sender.get(key) == "candidate"
        if kind == "slot":
            return self.slot_filled_by.get(key) == "candidate"
        if kind == "proposal":
            return True
        return dimension_id == CREDIT_DIMENSION

    def counted_units(self, refs: list[str], dimension_id: str) -> int:
        return len({r for r in refs if self.exists(r) and self.counted(r, dimension_id)})


# ---- 검증 (rubric.md 7.3) ---------------------------------------------------------------------


def check_dimension(row: Any, refs: RefIndex, forbidden: list[re.Pattern]) -> str | None:
    """차원 한 행의 실패 사유. 통과하면 None."""
    if not isinstance(row, dict):
        return "차원 행이 객체가 아님"
    dimension_id = row.get("dimension_id")
    level = row.get("level")
    reason = row.get("no_record_reason")
    evidence = row.get("evidence_refs")
    rationale = row.get("rationale")
    confidence = row.get("confidence")
    if not isinstance(evidence, list) or not all(isinstance(r, str) for r in evidence):
        return "evidence_refs는 문자열 배열이어야 함"
    if not isinstance(rationale, str) or not rationale.strip():
        return "rationale이 비어 있음"
    if has_forbidden(rationale, forbidden):
        return "rationale에 금지어(합격·순위·추천·점수 표현)"
    bad = [r for r in evidence if not refs.exists(r)]
    if bad:
        return f"세션에 없는 근거 참조 {bad}"
    if level is None:
        if reason not in MODEL_REASONS:
            return f"기록 없음 사유가 올바르지 않음: {reason!r}"
        if confidence is not None:
            return "기록 없음이면 confidence는 null"
        return None
    if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 5:
        return f"level은 1~5 정수 또는 null: {level!r}"
    if reason is not None:
        return "level과 no_record_reason을 함께 씀"
    if confidence not in CONFIDENCE_ORDER:
        return f"confidence 값이 올바르지 않음: {confidence!r}"
    units = refs.counted_units(evidence, dimension_id)
    if units < 1:
        return "수준이 있는데 지원자 근거가 없음"
    if level >= 4 and units < 2:
        return "수준 4·5에 서로 다른 지원자 근거가 2개 미만"
    return None


@dataclass
class Validation:
    valid: dict[str, dict[str, Any]]  # dimension_id → 통과한 행
    errors: dict[str, str]  # dimension_id 또는 "_format"·"summary" → 사유
    summary: str | None  # 통과한 summary


def validate_output(
    output: Any,
    dimension_ids: list[str],
    refs: RefIndex,
    forbidden: list[re.Pattern],
) -> Validation:
    result = Validation({}, {}, None)
    if not isinstance(output, dict) or not isinstance(output.get("dimensions"), list):
        result.errors["_format"] = "출력이 {element, summary, dimensions[]} 형식이 아님"
        return result
    summary = output.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        result.errors["summary"] = "summary가 비어 있음"
    elif has_forbidden(summary, forbidden):
        result.errors["summary"] = "summary에 금지어(합격·순위·추천·점수 표현)"
    else:
        result.summary = summary
    seen: dict[str, int] = {}
    for row in output["dimensions"]:
        dimension_id = row.get("dimension_id") if isinstance(row, dict) else None
        if dimension_id not in dimension_ids:
            result.errors["_format"] = f"척도에 없는 차원 {dimension_id!r}"
            continue
        seen[dimension_id] = seen.get(dimension_id, 0) + 1
        error = check_dimension(row, refs, forbidden)
        if error:
            result.errors[dimension_id] = error
        else:
            result.valid[dimension_id] = normalize(row)
    for dimension_id in dimension_ids:
        if seen.get(dimension_id, 0) == 0:
            result.errors[dimension_id] = "차원 누락"
        elif seen[dimension_id] > 1:
            result.errors[dimension_id] = "차원 중복"
            result.valid.pop(dimension_id, None)
    return result


def normalize(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "dimension_id": row["dimension_id"],
        "level": row.get("level"),
        "no_record_reason": row.get("no_record_reason"),
        "evidence_refs": list(row.get("evidence_refs") or []),
        "rationale": row["rationale"],
        "confidence": row.get("confidence"),
    }


def failed_row(dimension_id: str) -> dict[str, Any]:
    return {
        "dimension_id": dimension_id,
        "level": None,
        "no_record_reason": "evaluate_failed",
        "evidence_refs": [],
        "rationale": FAILED_RATIONALE,
        "confidence": None,
    }


# ---- 확신도 상한 (rubric.md 2.4) ---------------------------------------------------------------


def confidence_cap(
    dimension: dict[str, Any],
    units: int,
    element_cards: list[str],
    fired_cards: set[str],
) -> str:
    cap = "high"
    if units <= 1:
        cap = "medium"  # 근거 단위 1개
    if len(element_cards) >= 2 and sum(c in fired_cards for c in element_cards) == 1:
        cap = _lower(cap, "medium")  # 카드가 둘 이상인 요소(설득)에서 하나만 발동
    core = dimension.get("core_cards") or []
    if core and not any(c in fired_cards for c in core):
        cap = _lower(cap, "low")  # 핵심 카드 미발생, 보조 장면만
    return cap


def _lower(a: str, b: str) -> str:
    return a if CONFIDENCE_ORDER[a] <= CONFIDENCE_ORDER[b] else b


def clamp(row: dict[str, Any], cap: str) -> dict[str, Any]:
    """상한보다 높은 확신도만 상한으로 바꾼다. rationale은 그대로."""
    if row["level"] is None or row["confidence"] is None:
        return row
    return {**row, "confidence": _lower(row["confidence"], cap)}


# ---- 요소 수준 ---------------------------------------------------------------------------------


def element_level(rows: list[dict[str, Any]]) -> int | None:
    """수준이 있는 차원 평균을 반올림(.5 올림). 모두 기록 없음이면 None."""
    levels = [r["level"] for r in rows if r["level"] is not None]
    if not levels:
        return None
    return math.floor(sum(levels) / len(levels) + 0.5)


def element_summary(element: str, rows: list[dict[str, Any]], summary: str) -> dict[str, Any]:
    return {
        "element": element,
        "level": element_level(rows),
        "summary": summary,
        "dimension_count": len(rows),
        "no_record_count": sum(r["level"] is None for r in rows),
    }


# ---- 호출 ---------------------------------------------------------------------------------------


def user_prompt(
    element_rubric: dict[str, Any],
    no_record_reasons: list[dict[str, Any]],
    guide: str,
    record: dict[str, Any],
) -> str:
    rubric_block = {**element_rubric, "no_record_reasons": no_record_reasons}
    return "\n\n".join(
        [
            f"[요소] {element_rubric['element']}",
            "[요소 척도]\n" + json.dumps(rubric_block, ensure_ascii=False),
            "[요소 지침]\n" + guide,
            "[세션 기록]\n" + json.dumps(record, ensure_ascii=False),
        ]
    )


def retry_block(errors: dict[str, str]) -> str:
    lines = [f"- {key}: {reason}" for key, reason in errors.items()]
    return (
        "\n\n[재요청]\n직전 출력에 아래 문제가 있었습니다. "
        "같은 출력 형식으로 이 요소의 차원 전부를 다시 판단해 JSON 하나만 내 주세요.\n"
        + "\n".join(lines)
    )


def parse_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except ValueError:
        return None


@dataclass(frozen=True)
class EvalContext:
    record: dict[str, Any]
    rubric: dict[str, Any]
    refs: RefIndex
    prompts: Prompts
    forbidden: list[re.Pattern]

    @property
    def fired_cards(self) -> set[str]:
        return {o["card_id"] for o in self.record.get("observations", [])}

    def element_cards(self, element: str) -> list[str]:
        return [c["card_id"] for c in self.rubric.get("cards", []) if c.get("element") == element]


async def evaluate_element(
    llm: LLM, ctx: EvalContext, element_rubric: dict[str, Any], usage: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """요소 하나: (차원 행 목록, 요소 요약). 전송 오류는 그대로 올린다."""
    element = element_rubric["element"]
    dimensions = element_rubric["dimensions"]
    dimension_ids = [d["dimension_id"] for d in dimensions]
    user = user_prompt(
        element_rubric,
        ctx.rubric.get("no_record_reasons", []),
        ctx.prompts.elements[element],
        ctx.record,
    )
    text = await complete_tracked(llm, ctx.prompts.common, user, usage)
    checked = validate_output(parse_json(text), dimension_ids, ctx.refs, ctx.forbidden)
    if checked.errors:
        usage["element_retries"] += 1
        text = await complete_tracked(
            llm, ctx.prompts.common, user + retry_block(checked.errors), usage
        )
        checked = validate_output(parse_json(text), dimension_ids, ctx.refs, ctx.forbidden)
    rows = []
    for dimension in dimensions:
        dimension_id = dimension["dimension_id"]
        row = checked.valid.get(dimension_id)
        if row is None:
            rows.append(failed_row(dimension_id))
            continue
        units = ctx.refs.counted_units(row["evidence_refs"], dimension_id)
        cap = confidence_cap(dimension, units, ctx.element_cards(element), ctx.fired_cards)
        rows.append(clamp(row, cap))
    if all(r["no_record_reason"] == "evaluate_failed" for r in rows):
        summary = FAILED_SUMMARY
    else:
        summary = checked.summary or FAILED_SUMMARY
    return rows, element_summary(element, rows, summary)


async def run_evaluation(llm: LLM, ctx: EvalContext, usage: dict[str, Any]) -> dict[str, Any]:
    """5요소를 순서대로 평가해 save_evaluation 본문(session_id·run_id 제외)을 만든다."""
    dimensions: list[dict[str, Any]] = []
    elements: list[dict[str, Any]] = []
    for element_rubric in ctx.rubric["elements"]:
        rows, summary = await evaluate_element(llm, ctx, element_rubric, usage)
        dimensions.extend(rows)
        elements.append(summary)
    return {
        "rubric_version": ctx.rubric["rubric_version"],
        "prompt_versions": ctx.prompts.versions,
        "model": llm.model,
        "dimensions": dimensions,
        "elements": elements,
    }
