"""e2e 단언. 함수 이름의 번호는 docs/common/testing.md e2e "단언" 번호 그대로다.

각 함수는 러너가 모은 bundle(run.py Runner.b)을 받아 실패 문장 목록을 돌려준다(빈 목록 = 통과).
check()가 대본에 해당하는 단언만 골라 돌린다. 기대값은 대본 expect와 카탈로그에서 읽고, 판정을
너그럽게 바꾸지 않는다. 텍스트 규칙(선점 금지·금지어)은 정규식 근사라 실패 시 transcript로
재확인한다.
"""

import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from e2e.client import parse_time

REPO_ROOT = Path(__file__).resolve().parents[2]
ON_TIME_SECONDS = 10
DELIVERY_SECONDS = 90
TOKEN_LIMIT = 300_000
EVIDENCE_TYPES = {
    "message",
    "document",
    "share",
    "open",
    "task_event",
    "doc_view",
    "assistant_call",
}
NO_RECORD_REF = {"document", "doc_view"}
TWO_CARDS = {"planning", "collaboration"}
# 합격·순위 표현과 평가표 밖 점수 표현(워커 정규식과 따로 둔다. 업무 문장 "우선순위"는 허용)
FORBIDDEN = re.compile(
    r"합격|불합격|탈락|당락|(?<!우선)순위|등수|석차|(상위|하위)\s*\d+(\.\d+)?\s*%"
)
TEXT_FIELDS = {"observed", "note", "line"}
AI_EVENT_KEYS = {
    "call_id",
    "t_min",
    "request_quote",
    "response_quote",
    "cited_doc_ids",
    "applied_part",
}


# ───────────── 공용 ─────────────


def started(b: dict[str, Any]):
    return parse_time(b["session"]["started_at"])


def minutes(b: dict[str, Any], iso: str | None) -> float | None:
    return None if iso is None else (parse_time(iso) - started(b)).total_seconds() / 60


def events(b: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {e["card_id"]: e for e in b["session"]["events"]}


def element_events(b: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted((e for e in b["session"]["events"] if e["element"]), key=lambda e: e["due_at"])


def persona(b: dict[str, Any], sender: str = "colleague") -> list[dict[str, Any]]:
    return [m for m in b["messages"] if m["sender"] == sender]


def frames(b: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [f for f in b["frames"] if f["type"] == kind]


def report_items(report: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [
        (e["element"], i)
        for e in report["rubric"]["elements"]
        for c in e["cards"]
        for i in c["items"]
    ]


def report_evidence(report: dict[str, Any]) -> list[dict[str, Any]]:
    found = [ev for s in report["sections"] for c in s["cards"] for ev in c.get("evidence") or []]
    found += [ev for _, i in report_items(report) for ev in i.get("evidence") or []]
    return found


def tally(values: list[int | None]) -> dict[str, int]:
    return {
        "met": sum(v == 1 for v in values),
        "unmet": sum(v == 0 for v in values),
        "no_record": sum(v is None for v in values),
    }


def session_rows(b: dict[str, Any]) -> dict[str, set[str]]:
    """근거 타입별 이 세션의 행 id(rubric.md 근거 타입 표의 원천 테이블)."""
    docs = b["docs"]["documents"]
    return {
        "message": {m["id"] for m in b["messages"]},
        "document": {r["id"] for r in b["revisions"]},
        "share": {s["id"] for d in docs for s in d.get("shares") or []},
        "open": {o["id"] for d in docs for o in d.get("opens") or []},
        "task_event": {t["id"] for t in b["task_events"]},
        "doc_view": {v["id"] for v in b["doc_views"]},
        "assistant_call": {a["id"] for a in b["assistant_calls_internal"]},
    }


def near(a: float | None, b_: float | None, tol: float = 0.05) -> bool:
    return a is not None and b_ is not None and abs(a - b_) <= tol


# ───────────── 1·2 ─────────────


def assert_1_cards(b: dict[str, Any]) -> list[str]:
    fails = []
    selected = set(b["elements"])
    rows = b["session"]["events"]
    first_message: dict[str, str] = {}
    for m in sorted(b["messages"], key=lambda m: m["created_at"]):
        if m["event_id"]:
            first_message.setdefault(m["event_id"], m["created_at"])
    seen = {
        f["payload"]["event_id"] for f in frames(b, "message.new") if f["payload"].get("event_id")
    }
    gaps = b["session"].get("connection_gaps") or []

    def in_gap(t: float) -> bool:
        return any(g["from_t_min"] <= t <= (g["to_t_min"] or 1e9) for g in gaps)

    # 러너가 일부러 끊은 구간(재시작·disconnect)의 카드 메시지는 WS 대신 저장된 메시지로 본다
    seen |= {m["event_id"] for m in b["messages"] if m["event_id"] and in_gap(m["t_min"])}
    # 첫 WS 연결 전에 나온 카드 메시지는 연결 직후 /state로 받는다(화면과 같은 따라잡기)
    seen |= set(b.get("caught_up_event_ids") or [])
    for e in rows:
        if e["element"] and e["element"] not in selected:
            fails.append(f"unselected card present: {e['card_id']}")
        if e["status"] == "skipped":
            continue
        if e["status"] != "done":
            fails.append(f"{e['card_id']} status {e['status']}")
            continue
        lag = (parse_time(e["fired_at"]) - parse_time(e["due_at"])).total_seconds()
        if abs(lag) > ON_TIME_SECONDS:
            fails.append(f"{e['card_id']} fired lag {lag:.1f}s")
        if e["id"] not in first_message:
            fails.append(f"{e['card_id']} has no message")
        else:
            delivered = (
                parse_time(first_message[e["id"]]) - parse_time(e["fired_at"])
            ).total_seconds()
            if delivered > DELIVERY_SECONDS:
                fails.append(f"{e['card_id']} message after {delivered:.0f}s")
        if e["id"] not in seen:
            fails.append(f"{e['card_id']} message.new not seen on WS")
    # 문서 카드는 파트별 seq = 파트 번호 × 10
    shared = {m["id"]: m for m in b["messages"] if m["event_id"] and m.get("shared_doc")}
    part_of = {d["doc_id"]: d["part_no"] for d in b["docs"]["documents"]}
    for key in b["db"].get("message_keys") or []:
        m = shared.get(key["id"])
        if m and key["seq"] != part_of.get(m["shared_doc"]["doc_id"], -1) * 10:
            fails.append(f"doc card seq {key['seq']} for {m['content'][:20]}")
    cards = {e["card_id"] for e in rows}
    if "planning" not in selected and not {"division", "midpoint_draft"} <= cards:
        fails.append("planning unselected but division/midpoint_draft missing")
    if "honesty" not in selected and "report_request" not in cards:
        fails.append("honesty unselected but report_request missing")
    return fails


def _check_report(b: dict[str, Any], report: dict[str, Any], label: str) -> list[str]:
    fails = []
    selected = b["elements"]

    def texts(node: Any):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in TEXT_FIELDS and isinstance(v, str):
                    yield v
                else:
                    yield from texts(v)
        elif isinstance(node, list):
            for v in node:
                yield from texts(v)

    for value in texts(report):
        if FORBIDDEN.search(value):
            fails.append(f"{label}: forbidden word in {value[:40]}")
    sections = [s["element"] for s in report["sections"]]
    if sorted(sections) != sorted(selected):
        fails.append(f"{label}: sections {sections} != {selected}")
    rows = session_rows(b)
    record_refs = {(r["ref"]["type"], r["ref"]["id"]): r["ref"] for r in b.get("record") or []}
    for ev in report_evidence(report):
        if ev["type"] not in EVIDENCE_TYPES:
            fails.append(f"{label}: evidence type {ev['type']}")
        elif ev["id"] not in rows[ev["type"]]:
            fails.append(f"{label}: evidence {ev['type']} {ev['id']} not in session")
        if ev["type"] in NO_RECORD_REF:
            if ev.get("record_ref") is not None:
                fails.append(f"{label}: {ev['type']} record_ref not null")
        elif b.get("record") is not None and record_refs.get((ev["type"], ev["id"])) != ev.get(
            "record_ref"
        ):
            fails.append(f"{label}: record_ref mismatch {ev['type']} {ev['id']}")
    summary = {s["element"]: s for s in report["summary"]}
    if sorted(summary) != sorted(selected):
        fails.append(f"{label}: summary {sorted(summary)}")
    expect = (b["script"].get("expect") or {}).get("rubric") or {}
    for element in report["rubric"]["elements"]:
        values = [i["auto"] for c in element["cards"] for i in c["items"]]
        counted = tally(values)
        name = element["element"]
        s = summary.get(name, {})
        if {k: s.get(k) for k in counted} != counted or element["auto"] != counted:
            fails.append(f"{label}: {name} summary/auto {element['auto']} != items {counted}")
        if name in expect and counted != expect[name]:
            fails.append(f"{label}: {name} rubric {counted} != expect {expect[name]}")
        want_cards = 2 if name in TWO_CARDS else 1
        section = next((x for x in report["sections"] if x["element"] == name), {"cards": []})
        if len(section["cards"]) != want_cards:
            fails.append(f"{label}: {name} has {len(section['cards'])} card sections")
        for card in element["cards"]:
            for item in card["items"]:
                if item.get("basis") not in ("metric", "label"):
                    fails.append(f"{label}: {item['id']} basis {item.get('basis')}")
                if item["auto"] == 1 and not item.get("evidence"):
                    fails.append(f"{label}: {item['id']} met without evidence")
                if item["auto"] is None and not item.get("no_record_reason"):
                    fails.append(f"{label}: {item['id']} no_record without reason")
    return fails


def assert_2_report(b: dict[str, Any]) -> list[str]:
    fails = []
    for stage in ("draft", "final"):
        report = b.get(f"report_{stage}")
        if report is None:
            fails.append(f"no report {stage}")
            continue
        fails += _check_report(b, report, stage)
    return fails


def assert_2a_review(b: dict[str, Any]) -> list[str]:
    r = b["review"]
    final = b.get("report_final")
    if not r or final is None:
        return ["review not reached"]
    fails = []
    if r.get("no_memo_status") != 400:
        fails.append(f"memo-less adjustment → {r.get('no_memo_status')}, want 400")
    if r.get("status") != 200:
        fails.append(f"review → {r.get('status')}")
    item = next((i for _, i in report_items(final) if i["id"] == r["item"]["id"]), None)
    if (
        item is None
        or item.get("reviewer") != r["item"]["value"]
        or not item.get("adjusted")
        or item.get("memo") != "e2e 조정 메모"
    ):
        fails.append(f"adjusted item not reflected: {item}")
    auto = final["rubric"]["auto_total"]
    expected = dict(auto)
    for value, delta in ((r["item"]["auto"], -1), (r["item"]["value"], 1)):
        key = {1: "met", 0: "unmet", None: "no_record"}[value]
        expected[key] += delta
    if final["rubric"].get("reviewer_total") != expected:
        fails.append(f"reviewer_total {final['rubric'].get('reviewer_total')} != {expected}")
    if r.get("readjust_status") != 409:
        fails.append(f"readjust after review → {r.get('readjust_status')}, want 409")
    if r.get("notes_status") != 200:
        fails.append(f"notes → {r.get('notes_status')}")
    return fails


# ───────────── 2b: 선점 금지 (정규식 근사) ─────────────

PREEMPT = {
    # 창 카드 → 동료가 먼저 하면 안 되는 말
    "planning_division": re.compile(r"(\d번.{0,12}(먼저|까지|순서))|일정은|순서는|이렇게 나누"),
    "responsibility_delay": re.compile(
        r"팀장님(께|한테).{0,10}(말|보고|전달)|대안으로|그동안 .{0,10}(하시|할게)"
    ),
    "adaptability_change": re.compile(r"48시간|이번 분기|바뀐 (방향|범위)은"),
    "honesty_report": re.compile(r"팀장님(께|한테).{0,10}(말|보고|전달)|제가 (썼|작성했|맡았)"),
}


def _window_messages(b, card_id: str, sender: str) -> list[dict[str, Any]]:
    obs = next((o for o in b["observations"] if o["card_id"] == card_id), None)
    if obs is None:
        return []
    event_id = events(b).get(card_id, {}).get("id")
    return [
        m
        for m in persona(b, sender)
        if obs["window_start"] <= m["t_min"] <= obs["window_end"] and m["event_id"] != event_id
    ]


def assert_2b_no_preempt(b: dict[str, Any]) -> list[str]:
    fails = []
    candidate = [m for m in b["messages"] if m["sender"] == "candidate"]
    for card_id, pattern in PREEMPT.items():
        window = _window_messages(b, card_id, "colleague")
        first_own = min(
            (m["t_min"] for m in candidate if window and m["t_min"] >= window[0]["t_min"] - 10),
            default=1e9,
        )
        for m in window:
            # 주담당이 먼저 말한 뒤의 따라 말하기는 선점이 아니다
            if m["t_min"] <= first_own and pattern.search(m["content"]):
                fails.append(f"{card_id}: colleague preempted: {m['content'][:60]}")
    checkin = _window_messages(b, "planning_checkin", "colleague")
    asks = [m for m in checkin if "2번" in m["content"] and "?" in m["content"]]
    if len(asks) > 1:
        fails.append(f"planning_checkin: colleague asked about 2번 {len(asks)} times")
    ev = events(b).get("collab_disagree")
    if ev:
        card = next(c for c in b["scenario"]["cards"] if c["card_id"] == "collab_disagree")
        opinions = [o["opinion"].strip() for o in card.get("fixed_opinions") or []]
        said = [
            m["content"]
            for m in b["messages"]
            if m["event_id"] == ev["id"] and m["sender"] == "colleague"
        ]
        if not any(o in s for s in said for o in opinions):
            fails.append("collab_disagree opinion not one of fixed_opinions")
    return fails


# ───────────── 3 계열 ─────────────


def assert_3_ai_usage(b: dict[str, Any]) -> list[str]:
    expect = b["script"]["expect"]["ai_usage"]
    final = b.get("report_final") or b.get("report_draft")
    if final is None:
        return ["no report"]
    usage = final["ai_usage"]
    fails = []
    if usage["used"] != expect["used"]:
        fails.append(f"ai_usage.used {usage['used']}")
    if not expect["used"] and usage["events"]:
        fails.append("events not empty")
    for event in usage["events"]:
        if set(event) - AI_EVENT_KEYS:
            fails.append(f"extra ai_usage keys {sorted(set(event) - AI_EVENT_KEYS)}")
    if "applied_part" in expect:
        first = (b.get("assistant_calls") or [None])[0]
        event = next((e for e in usage["events"] if e["call_id"] == first), None)
        if event is None or event["applied_part"] != expect["applied_part"]:
            fails.append(
                f"applied_part {event and event['applied_part']} != {expect['applied_part']}"
            )
    masked = b["script"]["expect"].get("masked")
    if masked:
        # 어시스턴트 요청 본문은 저장 전에 마스킹된다: 원문은 어디에도 없고 마스크 표시가 남는다
        stored = [a["request"] for a in (b.get("state_end") or {}).get("assistant") or []]
        stored += [m["content"] for m in b["messages"] if m["channel"] == "assistant"]
        stored += [e["request_quote"] for e in usage["events"]]
        stored += [r["summary"] for r in b.get("record") or []]
        for raw in masked["raw"]:
            if any(raw in s for s in stored):
                fails.append(f"unmasked text stored: {raw}")
        joined = " ".join(stored)
        for mark in masked["marks"]:
            if mark not in joined:
                fails.append(f"mask mark missing: {mark}")
    return fails


def assert_3a_labels(b: dict[str, Any]) -> list[str]:
    expect = b["script"].get("expect") or {}
    obs = {o["card_id"]: o for o in b["observations"]}
    fails = []
    for card_id, label in (expect.get("labels") or {}).items():
        o = obs.get(card_id)
        if o is None or o["label"] != label:
            fails.append(f"{card_id} label {o and o['label']} != {label}")
        elif not o["evidence"]:
            fails.append(f"{card_id} has no evidence")
    for card_id, types in (expect.get("evidence_types") or {}).items():
        found = {e["type"] for e in (obs.get(card_id) or {}).get("evidence") or []}
        if not set(types) <= found:
            fails.append(f"{card_id} evidence types {sorted(found)} lack {types}")
    if b["name"] == "all_five":
        adapt = {e["type"] for e in (obs.get("adaptability_change") or {}).get("evidence") or []}
        if not adapt & {"document", "share"}:
            fails.append("adaptability evidence has no document/share")
        plan = {
            e["type"]
            for c in ("planning_division", "planning_checkin")
            for e in (obs.get(c) or {}).get("evidence") or []
        }
        if not {"open", "task_event"} <= plan:
            fails.append(f"planning evidence {sorted(plan)} lacks open/task_event")
        final = b.get("report_final") or {}
        told = (
            next((i for _, i in report_items(final) if i["id"] == "resp_told_manager"), None)
            if final
            else None
        )
        if told is None or told["auto"] != 1:
            fails.append(f"resp_told_manager {told and told['auto']}")
    return fails


def _run_tools(b: dict[str, Any], run_id: str | None) -> list[str]:
    return [
        f["payload"].get("tool")
        for f in frames(b, "agent.progress")
        if f["payload"].get("run_id") == run_id and f["payload"]["status"] == "tool_start"
    ]


def assert_3b_tool_choice(b: dict[str, Any]) -> list[str]:
    expect = b["script"]["expect"]["tool_choice"]
    says = {s["content"]: s for s in b["says"]}
    fails = []
    for content in expect.get("search_documents", []):
        tools = _run_tools(b, says.get(content, {}).get("run_id"))
        if "search_documents" not in tools:
            fails.append(f"no search_documents for: {content[:30]} ({tools})")
    for content in expect.get("no_tool", []):
        tools = _run_tools(b, says.get(content, {}).get("run_id"))
        if tools:
            fails.append(f"tool used for greeting: {tools}")
    return fails


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def assert_3c_work_memory(b: dict[str, Any]) -> list[str]:
    memory = b["script"]["expect"]["work_memory"]
    fails = []
    colleague = {d["part_no"]: d for d in b["docs"]["documents"] if d["owner"] == "colleague"}
    versions = {
        p: [v["content"] for v in sorted(d["versions"], key=lambda v: v["version"])]
        for p, d in colleague.items()
    }
    parts = (b["session"].get("division") or {}).get("parts") or {}
    for part, owner in parts.items():
        if owner in ("colleague", "both") and not versions.get(int(part)):
            fails.append(f"no colleague v1 for part {part}")
    for stage, index in (("draft_v1", 0), ("final_v2", 1)):
        for part, words in memory[stage].items():
            have = versions.get(int(part), [])
            text = _squash(have[index]) if len(have) > index else ""
            for word in words:
                if _squash(word) not in text:
                    fails.append(f"part {part} v{index + 1} lacks {word}")
    if len(versions.get(memory["v3_after_reply"], [])) < 3:
        fails.append(f"part {memory['v3_after_reply']} has no v3")
    answers = [m["content"] for m in persona(b) if m["content"].startswith("지금 4번은")]
    if len(answers) != memory["progress_same_answer"] or len(set(answers)) != 1:
        fails.append(f"progress answers {answers}")
    moves = [
        (t["part_no"], t["new_value"])
        for t in b["task_events"]
        if t["by"] == "colleague" and t["field"] == "status"
    ]
    for part, owner in parts.items():
        if owner in ("colleague", "both"):
            mine = [v for p, v in moves if p == int(part)]
            if mine[:1] != ["doing"] or mine[-1:] != ["done"]:
                fails.append(f"board part {part} moves {mine}")
    return fails


def assert_3d_early_submit(b: dict[str, Any]) -> list[str]:
    expect = b["script"]["expect"]
    fails = []
    submit = b.get("submit")
    if (
        not submit
        or submit["response"].get("status") != expect["submit_status"]
        or not submit["response"].get("deadline_at")
    ):
        return [f"submit response {submit and submit['response']}"]
    after = b["frames"][submit["frame_index"] :]
    ev = events(b)
    card = ev.get("honesty_report") or ev.get("report_request")
    if not any(
        f["type"] == "message.new" and f["payload"].get("event_id") == card["id"] for f in after
    ):
        fails.append("no report request message after submit")
    if not any(
        m["sender"] == "system" and "제출하면" in m["content"] and m["event_id"] == card["id"]
        for m in b["messages"]
    ):
        fails.append("no '제출하면 종료' system line")
    ended = [f for f in after if f["type"] == "session.ended"]
    if not ended or ended[-1]["payload"]["reason"] != expect["ended"]:
        fails.append(f"session.ended {ended and ended[-1]['payload']}")
    want = expect.get("after_resume")
    if want:
        got = b["resumes"][-1] if b["resumes"] else {}
        if (
            got.get("status") != want["status"]
            or not got.get("deadline_at")
            or not got.get("new_token")
        ):
            fails.append(f"resume {got}")
    gaps = b["session"].get("connection_gaps") or []
    if len(gaps) < expect.get("connection_gaps", 0):
        fails.append(f"connection_gaps {gaps}")
    last = next((o for o in b["observations"] if o["card_id"] == "honesty_report"), None)
    if last is None or not near(last["window_end"], minutes(b, b["session"]["completed_at"])):
        fails.append("honesty window_end != completed_at")
    return fails


def assert_3e_windows(b: dict[str, Any]) -> list[str]:
    fails = []
    fired = [e for e in element_events(b) if e["status"] in ("fired", "done")]
    obs = Counter(o["card_id"] for o in b["observations"])
    by_card = {o["card_id"]: o for o in b["observations"]}
    dues = [minutes(b, e["due_at"]) for e in fired]
    completed = minutes(b, b["session"]["completed_at"])
    for index, e in enumerate(fired):
        if obs[e["card_id"]] != 1:
            fails.append(f"{e['card_id']} observations {obs[e['card_id']]}")
            continue
        o = by_card[e["card_id"]]
        start = 0.0 if e["card_id"] == "planning_division" else dues[index]
        later = [d for d in dues[index + 1 :] if d > dues[index] + 1e-6]
        end = later[0] if later else completed
        if not near(o["window_start"], start) or not near(o["window_end"], end):
            fails.append(
                f"{e['card_id']} window {o['window_start']}~{o['window_end']} "
                f"!= {start:.2f}~{end:.2f}"
            )
    help_obs = by_card.get("collab_help")
    kept = (help_obs or {}).get("metrics", {}).get("promise_kept") or {}
    if kept.get("value") is True:
        final = b.get("report_final") or {}
        ids = {ev["id"] for ev in report_evidence(final)} if final else set()
        for message_id in kept.get("evidence_ids") or []:
            if message_id not in ids:
                fails.append("promise message not in report evidence")
    return fails


def assert_3f_documents(b: dict[str, Any]) -> list[str]:
    fails = []
    for w in b["writes"]:
        if w["before"] is not None and w["after"] != w["before"] + 1:
            fails.append(f"write part {w['part_no']} revision {w['before']}→{w['after']}")
    shared_new = {
        f["payload"]["id"] for f in frames(b, "message.new") if f["payload"].get("shared_doc")
    }
    for s in b["shares"]:
        if not s["ws_shared"] or s["message_id"] not in shared_new:
            fails.append(f"share part {s['part_no']} WS frames missing")
    docs = {d["doc_id"]: d for d in b["docs"]["documents"]}
    for o in b["opens"]:
        opens = [x for x in docs[o["doc_id"]].get("opens") or [] if x["version"] == o["version"]]
        if len(opens) != 1:
            fails.append(f"open part {o['part_no']} v{o['version']} rows {len(opens)}")
    final = b.get("report_final")
    if final is None:
        return [*fails, "no final report"]
    sections = {s["part_no"]: s for s in final["deliverable"]["final"]["sections"]}
    for imp in b["imports"]:
        s = sections.get(imp["part_no"])
        if (
            s is None
            or s["source_doc_id"] != imp["source_doc_id"]
            or s["source_version"] != imp["version"]
        ):
            fails.append(
                f"final section {imp['part_no']} source "
                f"{s and (s['source_doc_id'], s['source_version'])}"
            )
        elif s.get("edited") and not s.get("source_content"):
            fails.append(f"edited section {imp['part_no']} lacks source_content")
    listed = {d["doc_id"]: d for d in final["deliverable"]["documents"]}
    for doc_id, doc in docs.items():
        if doc.get("final") or not doc.get("shares"):
            continue
        if doc_id not in listed or listed[doc_id]["versions"] != len(doc["versions"]):
            fails.append(
                f"deliverable.documents missing/short for part {doc['part_no']} ({doc['owner']})"
            )
    return fails


def assert_3g_delay_notice(b: dict[str, Any]) -> list[str]:
    fails = []
    ev = events(b)
    card = next(c for c in b["scenario"]["cards"] if c["card_id"] == "responsibility_delay")
    expected = b["scenario"]["vars"]["interview_expected_time"]
    kickoff = [
        m
        for m in b["messages"]
        if m["event_id"] == ev["kickoff"]["id"] and m["sender"] == "manager"
    ]
    if not any(expected in m["content"] for m in kickoff):
        fails.append(f"kickoff does not announce {expected}")
    if card.get("sender_label") != "리서치 담당" or card.get("recipient_label") != "나에게만":
        fails.append("notice labels wrong in scenario")
    notice = [
        m
        for m in b["messages"]
        if m["event_id"] == ev["responsibility_delay"]["id"] and m["channel"] == "notice"
    ]
    if not notice:
        fails.append("no delay notice")
    release_at = card["effects"]["release_at_min"]
    released = [
        f for f in frames(b, "document.released") if f["payload"]["doc_id"] == "interview_summary"
    ]
    if not released:
        fails.append("no document.released")
    if not any(
        m["channel"] == "notice" and "공개" in m["content"] and m["t_min"] >= release_at - 0.1
        for m in b["messages"]
    ):
        fails.append("no '공개됨' notice line")
    docs = {d["doc_id"]: d for d in b["state_start"]["documents"]}
    if not near(docs.get("interview_summary", {}).get("release_at_min"), release_at):
        fails.append(f"state release_at_min {docs.get('interview_summary')} != {release_at}")
    return fails


# ───────────── 4·5·9 ─────────────


def assert_4_report_flow(b: dict[str, Any]) -> list[str]:
    fails = []
    draft, final = b.get("report_draft"), b.get("report_final")
    if not draft or draft["stage"] != "draft" or not final or final["stage"] != "final":
        return ["draft → final not reached"]
    db = b["db"]
    if db.get("hash_draft") is None or db.get("hash_draft") != db.get("hash_final"):
        fails.append(f"content_hash draft {db.get('hash_draft')} != final {db.get('hash_final')}")
    if b["review"].get("again") != 200:
        fails.append(f"duplicate review → {b['review'].get('again')}")
    if db.get("report_checkpoints") == 0:
        fails.append("no worker checkpoint for thread report:<session_id>")
    return fails


def _duplicates(b: dict[str, Any]) -> list[str]:
    fails = []
    keys = Counter(
        (k["run_id"], k["seq"]) for k in b["db"].get("message_keys") or [] if k["run_id"]
    )
    fails += [f"duplicate message run_id·seq {k}" for k, n in keys.items() if n > 1]
    versions = Counter(
        (v["doc_id"], v["run_id"]) for v in b["db"].get("versions") or [] if v["run_id"]
    )
    fails += [f"duplicate doc version doc_id·run_id {k}" for k, n in versions.items() if n > 1]
    return fails


def assert_5_restart(b: dict[str, Any]) -> list[str]:
    info = b.get("restart")
    if not info or info.get("restored_seconds") is None:
        return ["restart not performed or state not restored"]
    fails = []
    if info["restored_seconds"] > 90:
        fails.append(f"state restored after {info['restored_seconds']:.0f}s")
    after = events(b)
    for e in info["events_before"]:
        if e["status"] == "fired":
            fails += _rerun(b, after[e["card_id"]])
    return fails + _duplicates(b)


def _rerun(b: dict[str, Any], event: dict[str, Any], run_id: str | None = None) -> list[str]:
    """재실행된 카드: done이고 카드 메시지의 run_id가 하나(같은 run_id로 재실행)"""
    runs = {m["run_id"] for m in b["messages"] if m["event_id"] == event["id"]}
    fails = []
    if event["status"] != "done":
        fails.append(f"{event['card_id']} status {event['status']} after rerun")
    if len(runs) != 1 or (run_id and runs != {run_id}):
        fails.append(f"{event['card_id']} card messages run_ids {sorted(map(str, runs))}")
    return fails


def assert_6_faults(b: dict[str, Any]) -> list[str]:
    """장애 하나의 결과가 누락·중복 없이 수렴했는지(stack.py 장애 표)."""
    fault = b["fault"]
    name = fault["name"]
    checkin = events(b).get("planning_checkin")
    fails = _duplicates(b)
    if name in ("fired_kill", "tool_kill"):
        if not fault.get("run_id"):
            fails.append("fault was not triggered")
        fails += _rerun(b, checkin, fault.get("run_id") if name == "tool_kill" else None)
    elif name == "doc_fail":
        # C5: 첫 시도 실패로 document_missing=true가 남았다가 재실행 성공으로 done(표시는 지워짐)
        seen = [h for h in b.get("event_history") or [] if h["card_id"] == "planning_checkin"]
        if not any(h["document_missing"] for h in seen):
            fails.append(f"planning_checkin never marked document_missing: {seen}")
        fails += _rerun(b, checkin)
        parts = {d["part_no"]: d for d in b["docs"]["documents"] if d["owner"] == "colleague"}
        for part, doc in parts.items():
            if [v["version"] for v in doc["versions"]] != list(range(1, len(doc["versions"]) + 1)):
                fails.append(
                    f"colleague part {part} versions {[v['version'] for v in doc['versions']]}"
                )
    elif name == "publish_down":
        if not fault.get("enqueued_null"):
            fails.append("report_enqueued_at was not null while broker was down")
    elif name == "final_ack_kill":
        if not fault.get("killed"):
            fails.append("worker was not killed after final")
    elif name == "report_3fail":
        if fault.get("regenerated") != 200:
            fails.append(f"regenerate → {fault.get('regenerated')}")
    if name in ("publish_down", "report_3fail") and b.get("report_draft") is None:
        fails.append("report_ready not reached")
    if name == "final_ack_kill":
        fails += assert_4_report_flow(b)
    return fails


def latencies(b: dict[str, Any]) -> list[float]:
    """지원자 메시지 송신 → 같은 run_id의 첫 페르소나 message.new까지 초."""
    first: dict[str, float] = {}
    for f in frames(b, "message.new"):
        p = f["payload"]
        if p["sender"] in ("colleague", "manager") and p.get("run_id"):
            first.setdefault(p["run_id"], f["_at"])
    return sorted(first[s["run_id"]] - s["sent_at"] for s in b["says"] if s.get("run_id") in first)


def p95(values: list[float]) -> float | None:
    if not values:
        return None
    return values[min(len(values) - 1, int(round(0.95 * (len(values) - 1))))]


def tokens(b: dict[str, Any]) -> int:
    total = 0
    for run in b["db"].get("agent_runs") or []:
        total += (run["usage"] or {}).get("tokens_in", 0) + (run["usage"] or {}).get(
            "tokens_out", 0
        )
    usage = b["db"].get("report_usage") or {}
    return total + usage.get("tokens_in", 0) + usage.get("tokens_out", 0)


def assert_9_cost(b: dict[str, Any]) -> list[str]:
    b["cost"] = {"tokens": tokens(b), "latency_p95": p95(latencies(b))}
    if not b["db"].get("agent_runs"):
        return ["agent_runs not readable (DATABASE_URL)"]
    return (
        []
        if b["cost"]["tokens"] <= TOKEN_LIMIT
        else [f"tokens {b['cost']['tokens']} > {TOKEN_LIMIT}"]
    )


# ───────────── 고르기 ─────────────

Check = Callable[[dict[str, Any]], list[str]]


def plan(b: dict[str, Any]) -> list[tuple[str, Check]]:
    """대본에 해당하는 단언(번호, 함수).

    6은 장애를 건 실행(b["fault"])만, 7·8은 동시 실행·인증 모드가 따로 본다.
    """
    name, expect, selected = b["name"], b["script"].get("expect") or {}, set(b["elements"])
    chosen: list[tuple[str, Check]] = [("1", assert_1_cards), ("2", assert_2_report)]
    chosen += [("2a", assert_2a_review), ("3e", assert_3e_windows), ("4", assert_4_report_flow)]
    if name in ("all_five", "division_refuse"):
        chosen.append(("2b", assert_2b_no_preempt))
    if "ai_usage" in expect:
        chosen.append(("3", assert_3_ai_usage))
    if expect.get("labels") or expect.get("evidence_types"):
        chosen.append(("3a", assert_3a_labels))
    if "tool_choice" in expect:
        chosen.append(("3b", assert_3b_tool_choice))
    if "work_memory" in expect:
        chosen.append(("3c", assert_3c_work_memory))
    if "submit_status" in expect:
        chosen.append(("3d", assert_3d_early_submit))
    if name == "all_five":
        chosen.append(("3f", assert_3f_documents))
    if "responsibility" in selected:
        chosen.append(("3g", assert_3g_delay_notice))
    if any("restart" in s for s in b["script"]["steps"]):
        chosen.append(("5", assert_5_restart))
    if b.get("fault"):
        chosen.append(("6", assert_6_faults))
    chosen.append(("9", assert_9_cost))
    return chosen


def result(number: str, fn: Check, b: dict[str, Any]) -> dict[str, Any]:
    try:
        failures = fn(b)
    except Exception as exc:  # 수집 실패(리포트 없음 등)도 결과로 남겨 다음 단언을 계속 본다
        failures = [f"error: {type(exc).__name__}: {exc}"]
    return {"id": number, "name": fn.__name__, "ok": not failures, "failures": failures}


def check(b: dict[str, Any]) -> list[dict[str, Any]]:
    """단언을 돌려 [{id, name, ok, failures}]. 실패한 step도 한 줄로 남긴다."""
    results = []
    if b["step_errors"]:
        errors = [f"{e.get('at')}: {e.get('error')}" for e in b["step_errors"]]
        results.append({"id": "steps", "name": "대본 진행", "ok": False, "failures": errors})
    return results + [result(number, fn, b) for number, fn in plan(b)]


def passed(results: list[dict[str, Any]], only: tuple[str, ...] | None = None) -> bool:
    return all(r["ok"] for r in results if only is None or r["id"] in only)
