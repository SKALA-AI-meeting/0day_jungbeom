"""리포트 draft 조립(docs/worker-infra/design.md 3단계, 형식은 contracts.md Report).

collect가 모은 같은 세션 데이터만 근거로 쓴다. 관찰 행이나 지표가 가리키는 id가 이 세션
데이터에 없으면(다른 세션 id 등) 근거에서 뺀다. 텍스트 필드(observed·note·summary)는
금지어가 든 문장을 지운다. rubric 숫자 필드는 검사하지 않는다.
alias·position.name·deliverable·reviewer 병합은 api가 GET 때 붙인다.
카드 발생·실제 카드 시각·전달 지연은 세션 조회의 `events`와 같은 event_id의 메시지로 판단한다.
"""

import json
import re
from datetime import UTC, datetime
from typing import Any

from report_worker import rubric
from report_worker.llm import LLM, complete_with_retry, empty_usage

NOTE_NO_RECORD = "해당 상황에서 관련 행동이 기록되지 않음"
NOTE_UNCLASSIFIED = "행동이 기록되었으나 분류하지 않음"
NOTE_NOT_FIRED = "이벤트 미발생(조기 제출)"
AI_UNUSED = "사용하지 않음"
SUMMARY_REMOVED = "요약 문장에 판단 표현이 있어 지웠습니다. 아래 호출 기록을 확인해 주세요."
PERSONAS = ("colleague", "manager")
FIRED = ("fired", "done")
# 카드 메시지가 예정 시각보다 이만큼(분) 넘게 늦으면 창을 놓친 것으로 본다(agent/design.md 90초)
DELIVERY_DELAY_MAX_MIN = 1.5

# 합격·순위 표현과 평가표 밖의 점수 표현. 업무 문장("우선순위")은 남긴다.
FORBIDDEN = re.compile(
    r"합격|불합격|탈락|당락|(?<!우선)순위|등수|석차|(상위|하위)\s*\d+(\.\d+)?\s*%"
    r"|\d+\s*위(?!치)|\d+\s*등(?!분)|\d+(\.\d+)?\s*점(?!검)"
    r"|만점|감점|가산점|점수|채용\s*(을\s*)?(추천|권장)",
    re.IGNORECASE,
)
# 어시스턴트 요청이 결과 확인을 맡긴 것인지(검증). 재사용 행은 위임, 나머지 호출은 맥락
VERIFY_REQUEST = re.compile(r"검토|확인|맞는지|맞나|맞아|검증|틀린|오류|점검|체크")
AUX_FACT_TEXTS = {
    "colleague_revised_after_feedback": (
        "지원자 지적 뒤 동료가 위반 파트를 고침",
        "지원자 지적 뒤 동료의 위반 파트 수정 없음",
    ),
    "policy_doc_opened": ("운영 정책 문서를 열람함", "운영 정책 문서를 열람하지 않음"),
}
SENTENCE_SPLIT = re.compile(r"(?<=[.!?。])\s+|\n+")
TEXT_FIELDS = ("observed", "note", "summary")

SUMMARY_SYSTEM = (
    "너는 채용 담당자가 면접에서 확인할 수 있게 지원자의 AI 어시스턴트 사용 기록을 정리한다. "
    "위임(무엇을 맡겼는지), 맥락(어떤 자료·상황을 함께 줬는지), 검증(결과를 고치거나 확인했는지)을 "
    "한 문단 3~4문장으로 쓴다. 기록에 있는 사실만 쓰고, 잘했다·못했다 같은 판단, 점수, 합격, 순위, "
    "추천 표현은 쓰지 않는다."
)


def clean_text(text: str | None) -> str | None:
    """금지어가 든 문장을 지운다. 남는 문장이 없으면 빈 문자열."""
    if text is None:
        return None
    kept = [s for s in SENTENCE_SPLIT.split(text) if s.strip() and not FORBIDDEN.search(s)]
    return " ".join(s.strip() for s in kept)


def clean_fields(node: Any) -> Any:
    """observed·note·summary 키의 문자열을 재귀로 검사한다."""
    if isinstance(node, list):
        return [clean_fields(v) for v in node]
    if isinstance(node, dict):
        return {
            k: clean_text(v) if k in TEXT_FIELDS and isinstance(v, str) else clean_fields(v)
            for k, v in node.items()
        }
    return node


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _minutes(at: str | None, started: datetime | None) -> float | None:
    moment = _parse(at)
    if moment is None or started is None:
        return None
    return round((moment - started).total_seconds() / 60, 2)


class SessionData:
    """collect 결과를 id로 찾는 색인. 근거 검증의 기준(이 세션의 실제 행)."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.session = data["session"]
        self.scenario = self.session["position"]["scenario"]
        started = _parse(self.session.get("started_at"))
        self.messages = {m["id"]: m for m in data.get("messages") or []}
        self.ordered_messages = sorted(
            self.messages.values(), key=lambda m: (m.get("t_min") is None, m.get("t_min") or 0)
        )
        titles = {d["doc_id"]: d["title"] for d in self.scenario.get("documents") or []}
        self.revisions = {
            r["id"]: {**r, "t_min": _minutes(r.get("created_at"), started)}
            for r in data.get("document_revisions") or []
        }
        self.views = {
            v["id"]: {
                **v,
                "t_min": _minutes(v.get("viewed_at"), started),
                "title": titles.get(v["doc_id"], v["doc_id"]),
            }
            for v in data.get("doc_views") or []
        }
        self.calls = {}
        for call in data.get("assistant_calls") or []:
            request = self.messages.get(call.get("request_message_id")) or {}
            response = self.messages.get(call.get("response_message_id")) or {}
            t_min = request.get("t_min")
            if t_min is None:
                t_min = _minutes(call.get("created_at"), started)
            self.calls[call["id"]] = {
                **call,
                "t_min": t_min,
                "quote": request.get("content", ""),
                "response": response.get("content", ""),
            }
        self.reuse = [r for r in data.get("assistant_reuse") or [] if r["call_id"] in self.calls]
        self.started = started
        self.events = {e["card_id"]: e for e in self.session.get("events") or []}
        company = self.scenario.get("company") or {}
        self.names = {
            "colleague": (company.get("colleague") or {}).get("name") or "동료",
            "manager": (company.get("manager") or {}).get("name") or "팀장",
        }
        self.observations = {o["element"]: o for o in data.get("observations") or []}
        self.by_type = {
            "message": self.messages,
            "revision": self.revisions,
            "doc_view": self.views,
            "assistant_call": self.calls,
        }

    def type_of(self, item_id: str) -> str | None:
        for kind, rows in self.by_type.items():
            if item_id in rows:
                return kind
        return None

    def t_min(self, kind: str, item_id: str) -> float | None:
        return self.by_type[kind][item_id].get("t_min")

    def card_timing(self, card: dict[str, Any]) -> tuple[bool, float | None, bool]:
        """(발생, 실제 카드 시각(분), 전달 지연). 실제 시각은 이 이벤트 id의 첫 메시지 시각."""
        event = self.events.get(card["card_id"])
        if event is None or event.get("status") not in FIRED:
            return False, None, False
        sent = [
            m["t_min"]
            for m in self.ordered_messages
            if m.get("event_id") == event["id"] and m.get("t_min") is not None
        ]
        actual = sent[0] if sent else _minutes(event.get("fired_at"), self.started)
        due = _minutes(event.get("due_at"), self.started)
        delayed = actual is not None and due is not None and actual - due > DELIVERY_DELAY_MAX_MIN
        return True, actual if actual is not None else due, delayed

    def prev_persona_message(self, t_min: float | None) -> str | None:
        """근거 직전의 동료·팀장 메시지 1개를 "<보낸이> · <t>분: <본문>"으로(맥락, 점수 아님)."""
        if t_min is None:
            return None
        prev = None
        for m in self.ordered_messages:
            if m.get("t_min") is None or m["t_min"] > t_min:
                break
            if m.get("sender") in PERSONAS:
                prev = m
        if prev is None:
            return None
        return f"{self.names[prev['sender']]} · {prev['t_min']:g}분: {prev.get('content', '')}"


def _card(scenario: dict[str, Any], element: str) -> dict[str, Any]:
    return next(c for c in scenario["cards"] if c.get("element") == element)


def _evidence(kind: str, item_id: str, data: SessionData, card_at: float | None) -> dict[str, Any]:
    """타입별 표현: 메시지·호출은 원문 인용, revision은 파트·시각·변화율, doc_view는 문서명"""
    row = data.by_type[kind][item_id]
    t_min = row.get("t_min")
    item: dict[str, Any] = {"type": kind, "id": item_id, "t_min": t_min}
    if kind == "message":
        item.update(channel=row.get("channel"), quote=row.get("content", ""))
    elif kind == "assistant_call":
        item["quote"] = row["quote"]
    elif kind == "revision":
        item.update(
            part_no=row["part_no"],
            summary=f"{row['part_no']}번 파트 수정({t_min}분)",
            change_ratio=row.get("diff_ratio"),
        )
    elif kind == "doc_view":
        item.update(doc_id=row["doc_id"], summary=f"{row['title']} 열람({t_min}분)")
    item["context"] = {
        "prev_persona_message": data.prev_persona_message(t_min),
        "card_at_t_min": card_at,
    }
    return item


def _section_reason(state: str, fired: bool, missed: bool) -> str | None:
    if not fired:
        return rubric.EVENT_NOT_FIRED
    if missed:
        return rubric.WINDOW_MISSED
    if state in ("missing", rubric.NO_ACTIVITY):
        return rubric.NO_ACTIVITY
    if state == rubric.UNCLASSIFIED:
        return rubric.CLASSIFY_FAILED
    return None


def _out_of_window(element: str, observation: dict[str, Any] | None, data: SessionData) -> list:
    """related_card가 이 카드인데 창 밖에 있는 지원자 메시지(점수 무관, 사실 표시)."""
    if observation is None:
        return []
    start, end = _parse(observation.get("window_start")), _parse(observation.get("window_end"))
    out = []
    for m in data.ordered_messages:
        related = ((m.get("meta") or {}).get("classification") or {}).get("related_card")
        if m.get("sender") != "candidate" or related != element:
            continue
        at = _parse(m.get("created_at"))
        if at is not None and start is not None and end is not None and start <= at < end:
            continue
        out.append(
            {"t_min": m.get("t_min"), "channel": m.get("channel"), "quote": m.get("content")}
        )
    return out


def _aux_facts(card: dict[str, Any], observation: dict[str, Any] | None) -> list[str]:
    """점수에 쓰지 않는 지표를 사실 문장으로. 값이 없으면 빼고, 빈 배열도 허용한다."""
    facts = []
    for name in card.get("aux_facts") or []:
        value = rubric.metric_value(observation, name)[0] if observation else None
        if value is None:
            continue
        yes, no = AUX_FACT_TEXTS.get(name, (f"{name}: 예", f"{name}: 아니오"))
        facts.append(yes if value is True else no if value is False else f"{name}: {value}")
    return facts


def build_element(element: str, data: SessionData) -> tuple[dict[str, Any], dict[str, Any]]:
    """(섹션, 평가표 요소)."""
    card = _card(data.scenario, element)
    observation = data.observations.get(element)
    fired, card_at, delayed = data.card_timing(card)
    missed = fired and (delayed or rubric.missed_window(observation))
    state = rubric.label_state(card, observation)

    evidence = []
    if observation is not None and state in ("labeled", rubric.UNCLASSIFIED):
        for ref in observation.get("evidence") or []:
            kind, item_id = ref.get("type"), str(ref.get("id"))
            if kind in data.by_type and item_id in data.by_type[kind]:
                evidence.append(_evidence(kind, item_id, data, card_at))

    section: dict[str, Any] = {
        "element": element,
        "name": card.get("name"),
        "situation": card.get("situation"),
        "observed": None,
        "evidence": evidence,
        "event_fired": fired,
        "no_record_reason": _section_reason(state, fired, missed),
        "aux_facts": _aux_facts(card, observation),
        "out_of_window_messages": _out_of_window(element, observation, data),
    }
    if not fired:
        section["note"] = NOTE_NOT_FIRED
    elif state == "labeled":
        section["observed"] = (card.get("label_texts") or {}).get(observation["label"])
    elif state == rubric.UNCLASSIFIED and observation.get("label") == rubric.UNCLASSIFIED:
        section["note"] = NOTE_UNCLASSIFIED
    else:  # no_evidence, 관찰 행 없음, null(LLM 실패)
        section["note"] = NOTE_NO_RECORD
        section["evidence"] = []

    result = rubric.evaluate(card, observation, event_fired=fired, window_missed=missed)
    defs = {i["id"]: i for i in card.get("rubric") or []}
    items = []
    for value in result["items"]:
        item_def = defs[value["id"]]
        allowed = set(item_def.get("evidence_types") or data.by_type)
        refs = []
        for item_id in value["evidence_ids"]:
            kind = data.type_of(item_id)
            if kind in allowed:
                refs.append({"type": kind, "id": item_id, "t_min": data.t_min(kind, item_id)})
        item = {
            "id": value["id"],
            "text": item_def.get("text"),
            "auto": value["auto"],
            "no_record_reason": value["no_record_reason"],
            "reviewer": None,
            "memo": None,
            "evidence": refs if value["auto"] == 1 else [],
        }
        if item_def.get("when", {}).get("metric") == "response_minutes":
            # 실제 분. 관련 메시지가 없으면(0점 처리) null로 두어 0분과 구분한다
            item["minutes"] = (
                rubric.metric_value(observation, "response_minutes")[0] if observation else None
            )
        items.append(item)
    rubric_element = {
        "element": element,
        "name": card.get("name"),
        "auto": result["auto"],
        "reviewer": None,
        "items": items,
    }
    return section, rubric_element


async def build_ai_usage(data: SessionData, llm: LLM, usage: dict[str, Any]) -> dict[str, Any]:
    if not data.calls:
        return {"used": False, "summary": AI_UNUSED, "evidence": []}
    calls = sorted(data.calls.values(), key=lambda c: c.get("t_min") or 0)
    evidence: list[dict[str, Any]] = [
        {
            "call_id": c["id"],
            "t_min": c["t_min"],
            "quote": c["quote"],
            "category": "verify" if VERIFY_REQUEST.search(c["quote"] or "") else "context",
        }
        for c in calls
    ]
    for row in data.reuse:
        if row.get("reuse") in ("verbatim", "edited"):
            evidence.append(
                {
                    "call_id": row["call_id"],
                    "t_min": data.calls[row["call_id"]]["t_min"],
                    "part_no": row["part_no"],
                    "reuse": row["reuse"],
                    "ratio": row.get("ratio"),
                    "category": "delegate",
                }
            )
    record = {
        "calls": [
            {
                "t_min": c["t_min"],
                "request": c["quote"],
                "response": c["response"][:1000],
                "cited_docs": c.get("cited_doc_ids") or [],
            }
            for c in calls
        ],
        "reuse_in_document": [
            {"part_no": r["part_no"], "reuse": r["reuse"], "ratio": r.get("ratio")}
            for r in data.reuse
        ],
    }
    summary = await complete_with_retry(
        llm, SUMMARY_SYSTEM, json.dumps(record, ensure_ascii=False), usage
    )
    return {"used": True, "summary": summary, "evidence": evidence}


async def build_draft(
    raw: dict[str, Any], llm: LLM, *, now: datetime | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """(draft content, usage). 선택 요소만 섹션·평가표에 넣는다."""
    data = SessionData(raw)
    usage = empty_usage(llm.model)
    elements = data.session["position"]["elements"]
    ordered = [e for e in data.scenario.get("elements") or elements if e in elements]
    sections, rubric_elements = [], []
    for element in ordered:
        section, rubric_element = build_element(element, data)
        sections.append(section)
        rubric_elements.append(rubric_element)

    ai_usage = await build_ai_usage(data, llm, usage)
    content = {
        "session_id": data.session["id"],
        "stage": "draft",
        "position": {"elements": ordered},
        "rubric": {
            "elements": rubric_elements,
            "auto_total": rubric.total([e["auto"] for e in rubric_elements]),
            "reviewer_total": None,
            "review": None,
            "history": [],
        },
        "sections": sections,
        "ai_usage": ai_usage,
        "generated_at": (now or datetime.now(UTC)).isoformat(),
        "reviewed_at": None,
    }
    content = clean_fields(content)
    if content["ai_usage"]["used"] and not content["ai_usage"]["summary"]:
        content["ai_usage"]["summary"] = SUMMARY_REMOVED
    return content, usage
