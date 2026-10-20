"""리포트 draft 조립(docs/worker-infra/design.md 3단계, 형식은 contracts.md Report).

요소 섹션 안에 카드 소섹션을 두고, 평가표는 카드마다 rubric.evaluate로 계산한다. LLM은 부르지 않는다
(분류는 observe가 이미 했고 리포트 문장은 카탈로그 label_texts). collect가 모은 같은 세션 데이터만
근거로 쓰며, 관찰이나 지표가 가리키는 id가 이 세션 데이터에 없으면(다른 세션 id 등) 뺀다.
텍스트 필드(observed·note·line)는 금지어가 든 문장을 지운다.

근거의 record_ref는 api 전체 기록(GET /admin/sessions/{id}/record)의 ref와 같은 값이다:
같은 type·id와 세션 시작 기준 분(소수 둘째 자리). 기록에 없는 document·doc_view는 null.
alias·position·deliverable·reviewer·notes·connection_gaps·purge_at은 api가 GET 때 붙인다.
"""

import re
from datetime import UTC, datetime
from typing import Any

from report_worker import rubric
from report_worker.llm import LLM, empty_usage

PERSONAS = ("colleague", "manager")
FIRED = ("fired", "done")
# 카드 메시지가 예정 시각보다 이만큼(분) 넘게 늦으면 창을 놓친 것으로 본다(agent/design.md 90초)
DELIVERY_DELAY_MAX_MIN = 1.5
RECORDED = ("message", "share", "open", "task_event", "assistant_call")  # 전체 기록에 있는 타입
REPORT_KINDS = ("team", "manager_dm")

# 합격·순위 표현과 평가표 밖의 점수 표현. 업무 문장("우선순위")은 남긴다.
FORBIDDEN = re.compile(
    r"합격|불합격|탈락|당락|(?<!우선)순위|등수|석차|(상위|하위)\s*\d+(\.\d+)?\s*%"
    r"|\d+\s*위(?!치)|\d+\s*등(?!분)|\d+(\.\d+)?\s*점(?!검)"
    r"|만점|감점|가산점|점수|채용\s*(을\s*)?(추천|권장)",
    re.IGNORECASE,
)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?。])\s+|\n+")
TEXT_FIELDS = ("observed", "note", "line")


def clean_text(text: str | None) -> str | None:
    """금지어가 든 문장을 지운다. 남는 문장이 없으면 null."""
    if text is None:
        return None
    kept = [s for s in SENTENCE_SPLIT.split(text) if s.strip() and not FORBIDDEN.search(s)]
    return " ".join(s.strip() for s in kept) or None


def clean_fields(node: Any) -> Any:
    """observed·note·line 키의 문자열을 재귀로 검사한다."""
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


def _num(value: float | None) -> str:
    """12.0 → "12", 12.5 → "12.5"(요약 문장의 분 표기, api 전체 기록과 같은 표기)."""
    return "" if value is None else f"{value:g}"


# 보드 변경 요약의 필드·값 한국어 표기(contracts.md "n번 <필드> → <새 값>(t분)").
_FIELD_NAMES = {"assignee": "담당", "status": "상태", "order": "순서", "due_min": "언제까지"}
_VALUE_NAMES = {
    "candidate": "지원자",
    "colleague": "동료",
    "both": "함께",
    "todo": "할 일",
    "doing": "진행 중",
    "done": "완료",
}


def _task_summary(part_no: int, field: str, new_value: str | None, t_min: float | None) -> str:
    """ "1번 담당 → 지원자(12분)", "1번 언제까지 → 40분(15분)". 값이 비면 "없음"."""
    if new_value is None:
        value = "없음"
    elif field == "due_min":
        value = f"{new_value}분"
    else:
        value = _VALUE_NAMES.get(new_value, new_value)
    return f"{part_no}번 {_FIELD_NAMES.get(field, field)} → {value}({_num(t_min)}분)"


class SessionData:
    """collect 결과를 타입·id로 찾는 색인. 근거 검증의 기준(이 세션의 실제 행)."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.session = data["session"]
        self.scenario = self.session["position"]["scenario"]
        self.started = _parse(self.session.get("started_at"))
        self.events = {e["card_id"]: e for e in self.session.get("events") or []}
        self.observations = {o["card_id"]: o for o in data.get("observations") or []}
        self.honesty_facts = data.get("honesty_facts")
        company = self.scenario.get("company") or {}
        self.names = {
            "colleague": (company.get("colleague") or {}).get("name") or "동료",
            "manager": (company.get("manager") or {}).get("display")
            or (company.get("manager") or {}).get("name")
            or "팀장",
        }
        self.doc_titles = {d["doc_id"]: d["title"] for d in self.scenario.get("documents") or []}

        self.messages = {m["id"]: m for m in data.get("messages") or []}
        self.ordered_messages = sorted(
            self.messages.values(), key=lambda m: (m.get("t_min") is None, m.get("t_min") or 0)
        )
        docs = (data.get("docs") or {}).get("documents") or []
        self.docs = {d["doc_id"]: d for d in docs}
        self.shares, self.opens = {}, {}
        for d in docs:
            for s in d.get("shares") or []:
                self.shares[s["id"]] = {**s, "doc": d, "t_min": self.minutes(s["created_at"])}
            for o in d.get("opens") or []:
                self.opens[o["id"]] = {**o, "doc": d, "t_min": self.minutes(o["created_at"])}
        self.revisions = {r["id"]: r for r in data.get("document_revisions") or []}
        self.task_events = {
            e["id"]: {**e, "t_min": self.minutes(e["created_at"])}
            for e in data.get("task_events") or []
        }
        self.views = {
            v["id"]: {**v, "t_min": self.minutes(v["viewed_at"])}
            for v in data.get("doc_views") or []
        }
        self.calls = {}
        for call in data.get("assistant_calls") or []:
            request = self.messages.get(call.get("request_message_id")) or {}
            response = self.messages.get(call.get("response_message_id")) or {}
            self.calls[call["id"]] = {
                **call,
                "t_min": self.minutes(call["created_at"]),
                "request": request.get("content", ""),
                "response": response.get("content", ""),
            }
        self.reuse = [r for r in data.get("assistant_reuse") or [] if r["call_id"] in self.calls]
        self.by_type: dict[str, dict[str, Any]] = {
            "message": self.messages,
            "document": self.revisions,
            "share": self.shares,
            "open": self.opens,
            "task_event": self.task_events,
            "doc_view": self.views,
            "assistant_call": self.calls,
        }

    def minutes(self, value: str | None) -> float | None:
        moment = _parse(value)
        if moment is None or self.started is None:
            return None
        return round((moment - self.started).total_seconds() / 60, 2)

    def type_of(self, item_id: str) -> str | None:
        for kind, rows in self.by_type.items():
            if item_id in rows:
                return kind
        return None

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
        actual = sent[0] if sent else self.minutes(event.get("fired_at"))
        due = self.minutes(event.get("due_at"))
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
        return f"{self.names[prev['sender']]} · {_num(prev['t_min'])}분: {prev.get('content', '')}"


def _evidence(kind: str, item_id: str, data: SessionData, card_at: float | None) -> dict[str, Any]:
    """contracts.md evidence 타입별 표현과 맥락·record_ref."""
    row = data.by_type[kind][item_id]
    t_min = row.get("t_min")
    item: dict[str, Any] = {"type": kind, "id": item_id, "t_min": t_min}
    if kind == "message":
        item.update(channel=row.get("channel"), quote=row.get("content", ""))
        reply = (row.get("meta") or {}).get("reply_to_doc") or row.get("reply_to_doc")
        if reply:
            item["reply_to_doc"] = reply
    elif kind == "assistant_call":
        item["quote"] = row["request"]
    elif kind == "document":
        part = row.get("part_no")
        where = "최종본" if part == "final" else f"{part}번 파트"
        item.update(
            doc_id=row["doc_id"],
            part_no=part,
            revision=row["revision"],
            summary=f"{where} 편집({_num(t_min)}분)",
        )
    elif kind == "share":
        doc = row["doc"]
        item.update(
            doc_id=doc["doc_id"],
            part_no=doc["part_no"],
            version=row["version"],
            summary=f"{doc['part_no']}번 파트 v{row['version']} 보냄({_num(t_min)}분)",
        )
    elif kind == "open":
        doc = row["doc"]
        item.update(
            doc_id=doc["doc_id"],
            version=row["version"],
            summary=f"동료 {doc['part_no']}번 v{row['version']} 열람({_num(t_min)}분)",
        )
    elif kind == "task_event":
        item.update(
            part_no=row["part_no"],
            field=row["field"],
            summary=_task_summary(row["part_no"], row["field"], row.get("new_value"), t_min),
        )
    elif kind == "doc_view":
        title = data.doc_titles.get(row["doc_id"], row["doc_id"])
        item.update(doc_id=row["doc_id"], summary=f"{title} 열람({_num(t_min)}분)")
    item["context"] = {
        "prev_persona_message": data.prev_persona_message(t_min),
        "card_at_t_min": card_at,
    }
    item["record_ref"] = {"type": kind, "id": item_id, "t_min": t_min} if kind in RECORDED else None
    return item


def _refs(ids: list[str], data: SessionData, allowed: set[str]) -> list[tuple[str, str]]:
    """이 세션에 있고 항목이 허용하는 타입의 (타입, id)만. 순서 유지·중복 제거."""
    out = []
    for item_id in dict.fromkeys(str(i) for i in ids):
        kind = data.type_of(item_id)
        if kind in allowed:
            out.append((kind, item_id))
    return out


def _window(
    card: dict[str, Any],
    observation: dict[str, Any] | None,
    data: SessionData,
    card_at: float | None,
):
    """관찰 창 {start_min, end_min}. 관찰 행이 없으면 실제 시각으로 계산한다: 이 카드의 실제
    시각부터 다음에 실제로 실행된 요소 카드 또는 실제 종료까지. 조기 제출로 보고 요청이 당겨져도
    창이 역전되지 않는다. 미발생 카드는 예정 시각(종료 뒤면 종료 시각)의 빈 창."""
    if observation is not None:
        return {"start_min": observation["window_start"], "end_min": observation["window_end"]}
    end = data.minutes(data.session.get("completed_at"))
    if card_at is None:
        at = card["at_min"] if end is None else min(card["at_min"], end)
        return {"start_min": at, "end_min": at}
    start = card.get("window_start_min", card_at)
    for other in data.scenario["cards"]:
        if not other.get("element") or other["card_id"] == card["card_id"]:
            continue
        fired, at, _ = data.card_timing(other)
        if fired and at is not None and at > card_at and (end is None or at < end):
            end = at
    return {"start_min": start, "end_min": end}


def _label_messages(observation: dict[str, Any] | None, data: SessionData) -> list[str]:
    """label 판정에 쓰인 지원자 활동: 관찰 evidence와 aux.related_message_ids."""
    if observation is None:
        return []
    ids = [str(e["id"]) for e in observation.get("evidence") or []]
    ids += [str(i) for i in (observation.get("aux") or {}).get("related_message_ids") or []]
    return ids


def build_card(card: dict[str, Any], data: SessionData) -> tuple[dict[str, Any], dict[str, Any]]:
    """(섹션의 카드 소섹션, 평가표의 카드)."""
    observation = data.observations.get(card["card_id"])
    fired, card_at, delayed = data.card_timing(card)
    missed = fired and (delayed or rubric.missed_window(observation))
    event = data.events.get(card["card_id"]) or {}
    missing = bool(event.get("document_missing"))
    values = rubric.evaluate(
        card,
        observation,
        event_fired=fired,
        window_missed=missed,
        document_missing=missing,
    )
    label_ids = _label_messages(observation, data)
    labels = (card.get("label_texts") or {}) if observation else {}
    state = rubric.label_state(card, observation)

    items, scored = [], {}  # scored: 항목 근거로 실린 것(점수·판정에 쓰임, flag 없음)
    for value, item_def in zip(values, card.get("rubric") or [], strict=True):
        allowed = set(item_def.get("evidence_types") or data.by_type)
        if value["auto"] == 1:
            refs = _refs(value["evidence_ids"], data, allowed)
        elif item_def["basis"] == "label" and value["auto"] == 0:
            # label 항목은 판정 창의 지원자 활동을 met·unmet과 무관하게 싣는다(contracts.md)
            refs = _refs(label_ids, data, allowed)
        else:
            refs = []
        auto, reason = value["auto"], value["no_record_reason"]
        if item_def["basis"] == "label" and auto is not None and not refs:
            auto, reason = None, rubric.CLASSIFY_FAILED  # 근거 없는 분류 결과는 쓰지 않는다
        basis = item_def["basis"]
        if basis == "by_source":
            # 충족시킨 근거가 보드면 기록 기반, 채팅(분류 aux)이면 AI 분류 기반
            basis = "metric" if any(k == "task_event" for k, _ in refs) or not refs else "label"
        evidence = [_evidence(k, i, data, card_at) for k, i in refs]
        for e in evidence:
            scored[(e["type"], e["id"])] = e
        item = {
            "id": item_def["id"],
            "text": item_def["text"],
            "basis": basis,
            "auto": auto,
            "reviewer": None,
            "memo": None,
            "adjusted": False,
            "no_record_reason": reason,
            "evidence": evidence,
        }
        if item_def.get("when", {}).get("metric") == "response_minutes":
            # 실제 분. 관련 메시지가 없으면(0점 처리) null로 두어 0분과 구분한다
            item["minutes"] = rubric.metric_value(observation, "response_minutes")[0]
        items.append(item)

    # 소섹션 근거: 항목 근거(flag 없음) + 그 밖의 관찰 근거·aux 사실·창 밖 관련 메시지.
    # 항목 근거가 아닌 것은 중복 여부와 따로 판정해 aux 사실이면 aux_fact, 창 밖이면 out_of_window
    window = _window(card, observation, data, card_at)
    every = set(data.by_type)
    aux_ids = {
        ref
        for name in card.get("aux_facts") or []
        for ref in _refs(rubric.metric_value(observation, name)[1], data, every)
    }

    def outside(kind: str, item_id: str) -> bool:
        t_min = data.by_type[kind][item_id].get("t_min")
        end = window["end_min"]
        return t_min is not None and not (
            window["start_min"] <= t_min and (end is None or t_min < end)
        )

    related = [
        ("message", m["id"])
        for m in data.ordered_messages
        if m.get("sender") == "candidate"
        and ((m.get("meta") or {}).get("classification") or {}).get("related_card")
        == card["card_id"]
    ]
    others = _refs(label_ids, data, every) + sorted(aux_ids) + related
    section_evidence = list(scored.values())
    seen = set(scored)
    for kind, item_id in dict.fromkeys(others):
        if (kind, item_id) in seen:
            continue
        seen.add((kind, item_id))
        flag = None
        if (kind, item_id) in aux_ids:
            flag = "aux_fact"
        elif kind == "message" and outside(kind, item_id):
            flag = "out_of_window"
        elif (kind, item_id) in related:
            continue  # 창 안의 관련 메시지는 관찰 근거로 오지 않았으면 싣지 않는다
        item = _evidence(kind, item_id, data, card_at)
        section_evidence.append({**item, "flag": flag} if flag else item)
    section_evidence.sort(key=lambda e: (e["t_min"] is None, e["t_min"] or 0))

    reason = _card_reason(state, fired, missed, missing, items)
    no_record_texts = (data.scenario.get("rubric_rules") or {}).get("no_record_reasons") or {}
    section = {
        "card_id": card["card_id"],
        "name": card["name"],
        "situation": card.get("situation"),
        "event_fired": fired,
        "card_at_t_min": card_at,
        "window": window,
        # 항목이 전부 기록 없음이면(미발생·창 놓침·문서 미제공 등) 관찰 문장도 싣지 않는다
        "observed": labels.get(observation.get("label"))
        if state == "labeled" and reason is None
        else None,  # reason은 항목이 하나라도 값을 가지면 None이다
        "no_record_reason": reason,
        "note": no_record_texts.get(reason) if reason else None,
        "evidence": section_evidence if reason in (None, rubric.CLASSIFY_FAILED) else [],
    }
    if card["card_id"] == "honesty_report":
        section["facts"] = data.honesty_facts
    rubric_card = {"card_id": card["card_id"], "name": card["name"], "items": items}
    return section, rubric_card


def _card_reason(state: str, fired: bool, missed: bool, missing: bool, items) -> str | None:
    """카드 소섹션의 기록 없음 사유. 근거 검사까지 마친 최종 항목 값으로 계산하며, 항목이 모두
    기록 없음일 때만 값이 있다."""
    if any(i["auto"] is not None for i in items):
        return None
    if not fired:
        return rubric.EVENT_NOT_FIRED
    if missed:
        return rubric.WINDOW_MISSED
    if missing:
        return rubric.DOCUMENT_MISSING
    if state in ("missing", rubric.NO_ACTIVITY):
        return rubric.NO_ACTIVITY
    if state == rubric.UNCLASSIFIED:
        return rubric.CLASSIFY_FAILED
    reasons = {i["no_record_reason"] for i in items}
    if len(reasons) == 1:
        return reasons.pop()  # 예: 초안이 끝내 오지 않아 두 항목 모두 document_missing
    if rubric.CLASSIFY_FAILED in reasons:
        return rubric.CLASSIFY_FAILED
    return items[0]["no_record_reason"]


def build_ai_usage(data: SessionData) -> dict[str, Any]:
    """시간순 사실만(분류 라벨·비율 없음). applied_part는 반영된(applied) 파트 중 반영 비율이
    가장 큰 것: 내부 API가 호출마다 비율 큰 순으로 주므로 첫 applied 행이다."""
    calls = sorted(data.calls.values(), key=lambda c: (c["t_min"] is None, c["t_min"] or 0))
    applied: dict[str, int | str] = {}
    for row in data.reuse:
        if row.get("applied") and row["call_id"] not in applied:
            applied[row["call_id"]] = row["part_no"]
    return {
        "used": bool(calls),
        "events": [
            {
                "call_id": c["id"],
                "t_min": c["t_min"],
                "request_quote": c["request"],
                "response_quote": c["response"],
                "cited_doc_ids": list(c.get("cited_doc_ids") or []),
                "applied_part": applied.get(c["id"]),
            }
            for c in calls
        ],
    }


async def build_draft(
    raw: dict[str, Any], llm: LLM, *, now: datetime | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """(draft content, usage). 선택 요소만, 요소 섹션 안에 카드 소섹션을 둔다. LLM 호출은 없다."""
    data = SessionData(raw)
    selected = set(data.session["position"]["elements"])
    meta = {e["id"]: e for e in data.scenario.get("element_meta") or []}
    order = [e["id"] for e in data.scenario.get("element_meta") or [] if e["id"] in selected]
    cards_by_element: dict[str, list[dict[str, Any]]] = {e: [] for e in order}
    for card in data.scenario["cards"]:
        if card.get("element") in cards_by_element:
            cards_by_element[card["element"]].append(card)

    summary, sections, rubric_elements = [], [], []
    for element in order:
        name = meta[element]["name"]
        built = [build_card(card, data) for card in cards_by_element[element]]
        auto = rubric.tally([i["auto"] for _, c in built for i in c["items"]])
        observed = [s["observed"] for s, _ in built if s["observed"]]
        summary.append(
            {"element": element, "name": name, "line": ". ".join(observed) or None, **auto}
        )
        sections.append({"element": element, "name": name, "cards": [s for s, _ in built]})
        rubric_elements.append(
            {"element": element, "name": name, "auto": auto, "cards": [c for _, c in built]}
        )

    content = {
        "session_id": data.session["id"],
        "stage": "draft",
        "summary": summary,
        "rubric": {
            "elements": rubric_elements,
            "auto_total": rubric.total([e["auto"] for e in rubric_elements]),
            "reviewer_total": None,
            "review": None,
        },
        "sections": sections,
        "ai_usage": build_ai_usage(data),
        "generated_at": (now or datetime.now(UTC)).isoformat(),
        "reviewed_at": None,
    }
    return clean_fields(content), empty_usage(llm.model)
