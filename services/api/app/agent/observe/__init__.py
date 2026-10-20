"""observe: 카드 관찰 창 하나의 규칙 지표(compute_metrics)와 고정 레이블 분류(classify).

정의 정본은 docs/common/rubric.md("지표 정의", "카드별 레이블·보조 판정·근거 타입")와 docs/agent/
design.md observe 절이다. 입력은 그 세션의 기록 전체(Inputs)이고 창(Window)으로 거른다.

- 근거는 지원자 활동(메시지·문서 저장·보내기·열람·보드 변경·회사 문서 열람·어시스턴트 호출)만.
  동료·팀장 메시지는 [맥락]으로만 LLM에 주고 근거로 쓰지 않는다.
- 창 밖 근거는 메시지만, classification.related_card가 이 카드일 때 허용한다.
- 창 안에 지원자 활동이 없으면 LLM을 부르지 않고 no_evidence. 허용 밖 레이블은 unclassified,
  LLM 실패는 null. 분류가 실패하면 aux를 쓰지 않으므로 aux 기반 지표는 null이다.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.llm import BaseLLM, LLMUnavailable, Trace, Usage
from app.masking import mask

NO_EVIDENCE = "no_evidence"
UNCLASSIFIED = "unclassified"
# "하지 않음" 레이블: 창 안 활동이 허용 타입이 아니면 근거 없이도 낼 수 있다(observe_labels.md 1절)
NOT_DOING = frozenset({"ignore", "silent", "no_report", "refuse_or_ignore"})
CANDIDATE_CHANNELS = ("team", "dm", "manager_dm")
LATE_CARD_MINUTES = 1.5  # 카드 메시지가 due_at보다 이만큼 늦으면 창을 놓친 것(testing.md 90초)
PROMISE_TOLERANCE = 5.0  # 약속 이행 허용 오차(분, 파일럿 값)
CHANGE_DOC = "interview_summary"  # 책임감 카드의 지연 문서는 카드 effects가 정한다(기본값)


@dataclass
class Window:
    """관찰 창 하나. 시각은 세션 분(t_min)."""

    card: dict[str, Any]  # positions.scenario의 카드(labels·aux·metrics·evidence_types 포함)
    start: float
    end: float
    due: float  # 카드 due_at(planning_division만 start=0과 다르다)
    card_t_min: float | None = None  # 그 카드 메시지가 실제로 나간 시각
    event_ids: list[str] = field(default_factory=list)  # 그 카드의 session_events id

    @property
    def card_id(self) -> str:
        return self.card["card_id"]

    def holds(self, t_min: float | None) -> bool:
        return t_min is not None and self.start <= t_min <= self.end


@dataclass
class Inputs:
    """세션 기록. 항목은 dict이고 모두 id·t_min을 가진다(store가 만든다)."""

    messages: list[dict[str, Any]] = field(default_factory=list)  # 모든 발신자, meta 포함
    revisions: list[dict[str, Any]] = field(default_factory=list)  # 지원자 문서 저장만
    shares: list[dict[str, Any]] = field(default_factory=list)  # owner·event_id 포함
    opens: list[dict[str, Any]] = field(default_factory=list)
    task_events: list[dict[str, Any]] = field(default_factory=list)
    doc_views: list[dict[str, Any]] = field(default_factory=list)
    assistant_calls: list[dict[str, Any]] = field(default_factory=list)
    division: dict[str, Any] | None = None  # {parts, decided_by, decided_t_min}
    release_at: float | None = None  # 지연 공개 문서의 실제 공개 시각
    facts: dict[str, Any] | None = None  # 정직 사실 입력(honesty_facts)


def classification(message: dict[str, Any]) -> dict[str, Any]:
    return (message.get("meta") or {}).get("classification") or {}


def _candidate_messages(inputs: Inputs) -> list[dict[str, Any]]:
    return [
        m
        for m in inputs.messages
        if m["sender"] == "candidate" and m["channel"] in CANDIDATE_CHANNELS
    ]


def activity(window: Window, inputs: Inputs) -> list[tuple[str, dict[str, Any]]]:
    """창 안 지원자 활동(근거 타입, 항목). 메시지만 창 밖이어도 related_card면 들어간다."""
    out: list[tuple[str, dict[str, Any]]] = []
    for m in _candidate_messages(inputs):
        if window.holds(m["t_min"]) or classification(m).get("related_card") == window.card_id:
            out.append(("message", m))
    for kind, rows in (
        ("document", inputs.revisions),
        ("share", [s for s in inputs.shares if s["owner"] == "candidate"]),
        ("open", inputs.opens),
        ("task_event", [e for e in inputs.task_events if e["by"] == "candidate"]),
        ("doc_view", inputs.doc_views),
        ("assistant_call", inputs.assistant_calls),
    ):
        out.extend((kind, row) for row in rows if window.holds(row["t_min"]))
    return sorted(out, key=lambda item: item[1]["t_min"])


def related_messages(
    window: Window, inputs: Inputs, aux: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """관련 메시지 = classification.related_card가 이 카드이거나 aux.related_message_ids에 든 것."""
    ids = {str(i) for i in (aux or {}).get("related_message_ids") or []}
    found = []
    for kind, m in activity(window, inputs):
        if kind != "message":
            continue
        if classification(m).get("related_card") == window.card_id or str(m["id"]) in ids:
            found.append(m)
    return found


def _metric(value: Any, ids: list[Any] | tuple[Any, ...] = ()) -> dict[str, Any]:
    return {"value": value, "evidence_ids": [str(i) for i in dict.fromkeys(ids)]}


def _aux_metric(aux: dict[str, Any] | None, key: str, ids: list[Any]) -> dict[str, Any]:
    if aux is None or aux.get(key) is None:
        return _metric(None)
    return _metric(bool(aux[key]), ids if aux[key] else [])


def compute_metrics(
    window: Window, inputs: Inputs, classified: "Classified | None" = None
) -> dict[str, dict[str, Any]]:
    """카드의 metrics 목록을 {이름: {value, evidence_ids}}로 센다.

    classified.aux가 None이면(분류 실패·unclassified) aux 기반 지표는 null이다. promise_kept는 창
    닫힘에 null이고 세션 종료 때 promise_kept()로 다시 센다.
    """
    card = window.card
    aux = classified.aux if classified is not None else None
    doc_evidence = [
        e["id"]
        for e in (classified.evidence if classified else [])
        if e["type"] in ("document", "share")
    ]
    related = related_messages(window, inputs, aux)
    related_ids = [m["id"] for m in related]
    after_card = [
        m for m in related if window.card_t_min is None or m["t_min"] >= window.card_t_min - 1e-6
    ]
    mine = activity(window, inputs)
    values: dict[str, dict[str, Any]] = {}
    for name in card.get("metrics") or []:
        if name == "target_applied":
            values[name] = _aux_metric(aux, "target_applied", doc_evidence)
            continue
        values[name] = _compute(name, window, inputs, aux, related, related_ids, after_card, mine)
    if window.card_t_min is not None and window.card_t_min - window.due > LATE_CARD_MINUTES:
        values["window_missed"] = _metric(True)
    return values


def _compute(
    name: str,
    window: Window,
    inputs: Inputs,
    aux: dict[str, Any] | None,
    related: list[dict[str, Any]],
    related_ids: list[Any],
    after_card: list[dict[str, Any]],
    mine: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    in_window = [row for kind, row in mine if kind == "message" and window.holds(row["t_min"])]
    if name == "response_minutes":
        if not after_card or window.card_t_min is None:
            return _metric(None)
        first = after_card[0]
        return _metric(round(first["t_min"] - window.card_t_min, 2), [first["id"]])
    if name == "first_recipient":
        if not after_card:
            return _metric(None)
        return _metric(classification(after_card[0]).get("recipient"), [after_card[0]["id"]])
    if name == "responded_to_request":
        return _metric(bool(after_card), [m["id"] for m in after_card])
    if name == "division_by_candidate":
        return _division_by_candidate(window, inputs, mine)
    if name == "stated_schedule":
        return _stated_schedule(window, mine, aux, related_ids)
    if name == "draft_delivered":
        shares = _card_shares(window, inputs)
        return _metric(bool(shares))
    if name == "draft_opened":
        sent = {(s["doc_id"], s["version"]) for s in _card_shares(window, inputs)}
        opens = [
            row for kind, row in mine if kind == "open" and (row["doc_id"], row["version"]) in sent
        ]
        return _metric(bool(opens), [o["id"] for o in opens])
    if name == "promise_kept":
        return _metric(None)  # 창 닫힘에는 null, 종료 finalize에서 확정
    if name == "notified_before_release":
        told = [m for m in related if inputs.release_at is None or m["t_min"] < inputs.release_at]
        return _metric(bool(told), [m["id"] for m in told])
    if name == "notified_where_manager_sees":
        told = [m for m in related if m["channel"] in ("team", "manager_dm")]
        return _metric(bool(told), [m["id"] for m in told])
    if name == "impact_possible":
        parts = (inputs.division or {}).get("parts") or {}
        return _metric(parts.get("3") in ("colleague", "both"))
    if name == "mentions_colleague_impact":
        return _aux_metric(aux, "mentions_impact", related_ids)
    if name == "proposes_alternative":
        return _aux_metric(aux, "has_alternative", related_ids)
    if name == "doc_opened_after_release":
        doc = ((window.card.get("effects") or {}).get("release_document")) or CHANGE_DOC
        views = [
            row
            for kind, row in mine
            if kind == "doc_view"
            and row["doc_id"] == doc
            and inputs.release_at is not None
            and row["t_min"] >= inputs.release_at
        ]
        return _metric(bool(views), [v["id"] for v in views])
    if name == "document_changed_after":
        changed = [row["id"] for kind, row in mine if kind in ("document", "share")]
        return _metric(bool(changed), changed)
    if name == "mentions_scope_or_division":
        return _aux_metric(aux, "mentions_scope", related_ids)
    if name == "redirected_colleague":
        hits = [
            m
            for m in in_window
            if classification(m).get("recipient") == "colleague"
            and classification(m).get("kind") in ("redivide", "instruction")
        ]
        return _metric(bool(hits), [m["id"] for m in hits])
    facts = inputs.facts or {}
    if name == "has_colleague_shares":
        return _metric(any(s["owner"] == "colleague" for s in facts.get("shares") or []))
    if name == "has_incomplete_facts":
        incomplete = (
            bool(facts.get("empty_sections"))
            or bool(facts.get("tasks_not_done"))
            or facts.get("changed_after_adaptability") is False
        )
        return _metric(incomplete)
    if name == "has_report_message":
        reports = [
            m
            for m in in_window
            if classification(m).get("kind") == "report" and m["channel"] in ("team", "manager_dm")
        ]
        return _metric(bool(reports), [m["id"] for m in reports])
    if name in ("credits_colleague", "claims_colleague_work", "discloses_incomplete"):
        return _aux_metric(aux, name, related_ids)
    raise ValueError(f"unknown metric: {name}")


def _division_by_candidate(
    window: Window, inputs: Inputs, mine: list[tuple[str, dict[str, Any]]]
) -> dict[str, Any]:
    """창 안에 주담당이 분업을 확정했는가. 보드로 채운 것과 채팅으로 정해 동료가 채운 것을 같게
    본다."""
    division = inputs.division or {}
    parts = division.get("parts") or {}
    decided = (
        division.get("decided_by") == "candidate"
        and parts
        and all(parts.values())
        and window.holds(division.get("decided_t_min"))
    )
    if not decided:
        return _metric(False)
    board = [row["id"] for kind, row in mine if kind == "task_event" and row["field"] == "assignee"]
    chat = [
        row["id"]
        for kind, row in mine
        if kind == "message" and classification(row).get("kind") == "redivide"
    ]
    return _metric(True, board or chat)


def _stated_schedule(
    window: Window,
    mine: list[tuple[str, dict[str, Any]]],
    aux: dict[str, Any] | None,
    related_ids: list[Any],
) -> dict[str, Any]:
    """보드의 언제까지(due_min) 또는 순서 변경 2건 이상, 아니면 채팅의 순서·시점 언급(aux)."""
    events = [row for kind, row in mine if kind == "task_event"]
    due = [e["id"] for e in events if e["field"] == "due_min" and e["new_value"] is not None]
    order = [e["id"] for e in events if e["field"] == "order"]
    if due or len(order) >= 2:
        return _metric(True, due or order)
    if aux is not None and aux.get("mentions_schedule"):
        return _metric(True, related_ids)
    if aux is None:
        return _metric(None)
    return _metric(False)


def _card_shares(window: Window, inputs: Inputs) -> list[dict[str, Any]]:
    """그 카드 실행으로 동료가 보낸 문서(문서 카드 메시지의 event_id가 카드 행)."""
    events = set(window.event_ids)
    return [s for s in inputs.shares if s["owner"] == "colleague" and s.get("event_id") in events]


# ───────────── LLM 분류 ─────────────

AUX_NUMBERS = frozenset({"promised_t_min"})  # 나머지 aux는 참/거짓


def _aux_value(key: str, value: Any) -> Any:
    """aux 값의 타입을 검사한다. 해석할 수 없는 값(문자열 "false", 설명문 등)은 null로 둬 그 지표를
    분류 실패로 남긴다(문자열을 참으로 바꿔 점수를 만들지 않는다)."""
    if key in AUX_NUMBERS:
        ok = isinstance(value, int | float) and not isinstance(value, bool)
        return value if ok else None
    return value if isinstance(value, bool) else None


def changed_text(previous: str, current: str) -> str:
    """이전 저장본 대비 변경. 삭제·순서 변경도 보이게 현재 본문과 지운 줄을 함께 싣는다.

    파트 문서는 현재 본문 전체 + 지운 줄. 최종본(## 섹션)은 바뀐 섹션마다 현재 섹션 + 지운 줄
    (섹션째 지웠으면 그 섹션). 바뀐 것이 없으면 "(변경 없음)".
    """
    if "\n## " in f"\n{current}" or "\n## " in f"\n{previous}":
        old = {_title(s): s for s in _sections(previous)}
        new = {_title(s): s for s in _sections(current)}
        out = []
        for title, section in new.items():
            if old.get(title) != section:
                out.append(_with_removed(old.get(title, ""), section))
        out += [f"(섹션 삭제) {old[t]}" for t in old if t not in new]
        return "\n".join(out) or "(변경 없음)"
    if previous.strip() == current.strip():
        return "(변경 없음)"
    return _with_removed(previous, current)


def _with_removed(previous: str, current: str) -> str:
    kept = {line.strip() for line in current.splitlines()}
    removed = [
        line.strip() for line in previous.splitlines() if line.strip() and line.strip() not in kept
    ]
    body = f"현재 본문:\n{current.strip()}"
    return body + ("\n지운 줄:\n" + "\n".join(removed) if removed else "")


def _title(section: str) -> str:
    return section.split("\n", 1)[0]


def _sections(text: str) -> list[str]:
    parts = [p.strip() for p in f"\n{text}".split("\n## ") if p.strip()]
    return [f"## {p}" for p in parts]


def _line(kind: str, row: dict[str, Any]) -> str:
    t = f"t={row['t_min']:.2f}"
    if kind == "message":
        c = classification(row)
        reply = (row.get("meta") or {}).get("reply_to_doc")
        tail = (
            f" (문서 답글: {reply.get('part_no', '?')}번 v{reply.get('version')})" if reply else ""
        )
        to = c.get("recipient") or "-"
        head = f"- message id={row['id']} {t} 채널={row['channel']} 수신자={to}"
        return f"{head}: {row['content']}{tail}"
    if kind == "document":
        # 바뀐 부분(최종본은 바뀐 섹션)만 그대로 싣는다. 앞부분 절단으로 뒤쪽 변경이 빠지지 않게
        body = mask(changed_text(row.get("previous") or "", row.get("content") or ""))
        return f"- document id={row['id']} {t} 파트={row['part_no']} 변경:\n{body}"
    if kind == "share":
        version = f"파트={row['part_no']} v{row['version']}"
        body = mask((row.get("content") or "").strip())
        return f"- share id={row['id']} {t} {version} 채널={row['channel']} 본문:\n{body}"
    if kind == "open":
        return f"- open id={row['id']} {t} 동료 {row['part_no']}번 v{row['version']}"
    if kind == "task_event":
        return (
            f"- task_event id={row['id']} {t} {row['part_no']}번 {row['field']}: "
            f"{row['old_value']} → {row['new_value']}"
        )
    if kind == "doc_view":
        return f"- doc_view id={row['id']} {t} {row.get('title') or row['doc_id']}"
    return f"- assistant_call id={row['id']} {t} 질문: {row.get('request') or ''}"


def _aux_format(card: dict[str, Any]) -> str:
    """aux 값의 타입(검사 규칙 _aux_value와 같음). 근거 문장은 aux가 아니라 evidence로 낸다."""
    number = "숫자(세션 분) 또는 null"
    flag = "true 또는 false(판단 불가면 null)"
    kinds = [f"{k}={number if k in AUX_NUMBERS else flag}" for k in card.get("aux") or []]
    return ", ".join([*kinds, "related_message_ids=메시지 id 목록"])


def _card_block(window: Window, inputs: Inputs, extra: dict[str, Any]) -> str:
    card = window.card
    labels = card.get("label_texts") or {}
    lines = [
        f"카드 id: {window.card_id} ({card.get('name', '')})",
        f"카드가 전한 내용: {card.get('text') or card.get('brief') or ''}",
        f"카드 메시지 시각: {window.card_t_min}",
        f"근거 타입: {', '.join(card.get('evidence_types') or [])}",
        "허용 레이블:",
        *[f"- {name}: {labels.get(name, '')}" for name in card.get("labels") or []],
        f"aux 키: {', '.join([*(card.get('aux') or []), 'related_message_ids'])}",
        "aux 형식: " + _aux_format(card),
    ]
    lines += [f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in extra.items()]
    return "[카드]\n" + "\n".join(lines)


def _extra(window: Window, inputs: Inputs, mine: list[tuple[str, dict[str, Any]]]) -> dict:
    """카드별 코드 계산 사실(observe_labels.md 1절). 페르소나 컨텍스트에는 넣지 않는다."""
    card_id = window.card_id
    if card_id == "responsibility_delay":
        before = {
            str(row["id"]): inputs.release_at is None or row["t_min"] < inputs.release_at
            for kind, row in mine
            if kind == "message"
        }
        return {"release_at": inputs.release_at, "released_before_message": before}
    if card_id == "adaptability_change":
        return {"change_targets": window.card.get("change_targets") or []}
    if card_id == "collab_help":
        return {"card_t_min": window.card_t_min}
    if card_id == "collab_disagree":
        return {"fixed_opinions": [o["opinion"] for o in window.card.get("fixed_opinions") or []]}
    return {}


def _prompt(window: Window, inputs: Inputs, mine: list[tuple[str, dict[str, Any]]]) -> str:
    context = [
        m
        for m in inputs.messages
        if m["sender"] in ("colleague", "manager")
        and m["channel"] in CANDIDATE_CHANNELS
        and window.holds(m["t_min"])
    ]
    blocks = [
        _card_block(window, inputs, _extra(window, inputs, mine)),
        "[창 안 지원자 활동]\n" + "\n".join(_line(kind, row) for kind, row in mine),
        "[맥락] (근거로 쓰지 않음)\n"
        + (
            "\n".join(f"- {m['sender']} t={m['t_min']:.2f}: {m['content']}" for m in context)
            or "(없음)"
        ),
    ]
    if window.card_id == "honesty_report":
        blocks.append("[사실]\n" + json.dumps(inputs.facts or {}, ensure_ascii=False))
    return "\n\n".join(blocks)


@dataclass
class Classified:
    label: str | None
    evidence: list[dict[str, str]]
    aux: dict[str, Any] | None  # None: 분류 실패·unclassified(aux 기반 지표를 쓰지 않음)
    llm_called: bool


async def classify(
    window: Window,
    inputs: Inputs,
    llm: BaseLLM | None,
    system_prompt: str,
    *,
    usage: Usage,
    trace: Trace,
) -> Classified:
    card = window.card
    mine = activity(window, inputs)
    if not mine:
        return Classified(NO_EVIDENCE, [], {}, False)
    if llm is None:  # 세션 토큰 예산 소진: 분류하지 않는다(label null → 분류 실패)
        return Classified(None, [], None, False)
    try:
        reply = await llm.ainvoke(
            [SystemMessage(system_prompt), HumanMessage(_prompt(window, inputs, mine))],
            usage=usage,
            trace=trace,
            json_mode=True,
            temperature=0,
        )
        parsed = json.loads(str(reply.content))
        if not isinstance(parsed, dict):
            raise ValueError("not an object")
    except (LLMUnavailable, ValueError):
        return Classified(None, [], None, True)

    label = parsed.get("label")
    allowed_types = set(card.get("evidence_types") or [])
    known = {(kind, str(row["id"])) for kind, row in mine}
    evidence = []
    for item in parsed.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        key = (item.get("type"), str(item.get("id")))
        if (
            key in known
            and key[0] in allowed_types
            and key not in [(e["type"], e["id"]) for e in evidence]
        ):
            evidence.append({"type": key[0], "id": key[1]})
    if label not in (card.get("labels") or []):
        return Classified(UNCLASSIFIED, evidence, None, True)
    if label not in NOT_DOING and not evidence:
        return Classified(UNCLASSIFIED, evidence, None, True)
    if label == "apply_silently" and not any(e["type"] in ("document", "share") for e in evidence):
        return Classified(UNCLASSIFIED, evidence, None, True)

    raw_aux = parsed.get("aux") if isinstance(parsed.get("aux"), dict) else {}
    messages = {str(row["id"]) for kind, row in mine if kind == "message"}
    aux = {key: _aux_value(key, raw_aux.get(key)) for key in card.get("aux") or []}
    aux["related_message_ids"] = [
        str(i) for i in raw_aux.get("related_message_ids") or [] if str(i) in messages
    ]
    return Classified(label, evidence, aux, True)


async def observe(
    window: Window,
    inputs: Inputs,
    llm: BaseLLM | None,
    system_prompt: str,
    *,
    usage: Usage,
    trace: Trace,
) -> dict[str, Any]:
    """규칙 지표 → LLM 분류 → aux 지표 병합. record_observation 본문(run_id 제외)을 돌려준다."""
    classified = await classify(window, inputs, llm, system_prompt, usage=usage, trace=trace)
    body: dict[str, Any] = {
        "card_id": window.card_id,
        "element": window.card.get("element"),
        "window_start": window.start,
        "window_end": window.end,
        "metrics": compute_metrics(window, inputs, classified),
        "label": classified.label,
        "aux": classified.aux or {},
        "evidence": classified.evidence,
    }
    if window.card_id == "honesty_report":
        body["facts"] = inputs.facts or {}
    return body


def promise_kept(
    window: Window, inputs: Inputs, label: str | None, aux: dict[str, Any] | None
) -> dict[str, Any]:
    """collab_help 약속 이행(세션 종료 때 확정). help_now면 true, negotiate_timing이면 제안 시각
    ±5분 안에 동료 DM 관련 메시지(창 밖 related_card 허용)가 있는지, 그 밖은 null."""
    if label == "help_now":
        return _metric(True, [m["id"] for m in related_messages(window, inputs, aux)][:1])
    promised = (aux or {}).get("promised_t_min")
    if label != "negotiate_timing" or not isinstance(promised, int | float):
        return _metric(None)
    related = related_messages(window, inputs, aux)
    # 약속한 메시지(첫 관련 답) 뒤에 실제로 동료에게 간 DM만 이행으로 본다
    promised_at = related[0]["t_min"] if related else None
    kept = [
        m
        for m in related
        if m["channel"] == "dm"
        and promised_at is not None
        and m["t_min"] > promised_at
        and abs(m["t_min"] - promised) <= PROMISE_TOLERANCE
    ]
    return _metric(bool(kept), [m["id"] for m in kept])
