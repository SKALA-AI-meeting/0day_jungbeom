"""공용 계약 픽스처(tests/fixtures/contracts/)와 생산자 응답의 비교.

api·report-worker 테스트가 함께 쓴다.

표준 라이브러리만 쓴다. 각 서비스 테스트가 파일 경로로 import한다.

id·본문·시각처럼 세션마다 다른 값은 형태만 본다: 객체는 키 집합이 같고 값의 종류(문자열·수·참거짓·
객체·목록)가 같아야 한다. 채널·상태·타입처럼 계약이 정한 값은 계약 어휘 안의 값이어야 한다(VOCAB).
필수 필드가 null이면 실패다. 진행 단계에 따라 비는 필드만 null을 허용한다(NULLABLE).
없어도 되는 키(계약 표의 `키?`)는 호출마다 optional로 넘긴다.

목록은 실제 원소마다 픽스처의 같은 종류 원소(type·status·owner·card_id·element·sender·id가
같은 것, 없으면 첫 원소)와 비교한다. 채용 건 scenario는 예시가 저장 형식의 일부만 보여 주므로
그 아래에서는 픽스처의 키가 모두 있기만 하면 된다.
meta·metrics·aux·usage 같은 자유 객체는 객체인지만 본다.
"""

import json
from pathlib import Path
from typing import Any

CONTRACTS = Path(__file__).resolve().parent / "fixtures" / "contracts"
_DISCRIMINANTS = ("type", "status", "owner", "card_id", "element", "sender", "id")
SUPERSET = ".scenario"
FREE = {"meta", "metrics", "aux", "usage", "payload"}

_SESSION = {
    "invited",
    "cancelled",
    "in_progress",
    "reporting",
    "completed",
    "report_ready",
    "approving",
    "reviewed",
    "failed",
}
_SENDERS = {"manager", "colleague", "candidate", "assistant", "system"}
VOCAB: dict[str, set] = {
    "channel": {"team", "dm", "manager_dm", "notice", "assistant"},
    "sender": _SENDERS,
    "by": _SENDERS,
    "status": _SESSION | {"pending", "fired", "done", "skipped", "todo", "doing"},
    "display_status": _SESSION | {"expired"},
    "display_group": {"waiting", "in_progress", "needs_review", "done", "problem"},
    "score_source": {"auto", "reviewer"},
    "decided_by": {"candidate", "colleague_default"},
    "division_decided_by": {"candidate", "colleague_default"},
    "owner": {"candidate", "colleague"},
    "source_owner": {"candidate", "colleague"},
    "assignee": {"candidate", "colleague", "both"},
    "field": {"assignee", "status", "order", "due_min"},
    "basis": {"metric", "label"},
    "stage": {"draft", "final"},
    "previous_relation": {"retry", "reissue"},
    "failed_stage": {"session", "report"},
    "kind": {
        "question",
        "instruction",
        "redivide",
        "progress_query",
        "doc_feedback",
        "report",
        "other",
    },
    "recipient": {"manager", "colleague"},
    "element": {"responsibility", "planning", "adaptability", "collaboration", "honesty"},
    "type": {
        "message",
        "document",
        "share",
        "open",
        "task_event",
        "doc_view",
        "assistant_call",
        "notice",
        "connection_gap",
    },
}
_TASK = {"todo", "doing", "done"}
# 상태 어휘는 부모 키로 좁힌다(세션·보드 카드·카드 실행). 부모가 이 밖이면 VOCAB의 합집합
STATUS_BY_PARENT = {
    "session": _SESSION,
    "tasks": _TASK,
    "task": _TASK,
    "events": {"pending", "fired", "done", "skipped", "failed"},
}
# 단계별 필수 값: 객체의 status가 이 값이면 해당 필드는 null일 수 없다
REQUIRED_BY_STATUS = {
    "reporting": {"submitted_at", "deadline_at"},
    "completed": {"completed_at"},
}
# 진행 단계·종류에 따라 비어 있을 수 있는 필드. 그 밖의 필드가 null이면 계약 위반이다
NULLABLE = {
    "division",
    "deadline_at",
    "completed_at",
    "submitted_at",
    "reported_at",
    "started_at",
    "ends_at",
    "remaining_seconds",
    "event_id",
    "run_id",
    "reply_to_doc",
    "shared_doc",
    "source_doc_id",
    "source_version",
    "source_owner",
    "source_content",
    "due_min",
    "assignee",
    "release_at_min",
    "current_card",
    "to_t_min",
    "fired_at",
    "response_message_id",
    "applied_part",
    "part_no",
    "final_report_message",
    "division_decided_by",
    "submitted_version",
    "label",
    "met",
    "unmet",
    "no_record",
    "score_source",
    "by_element",
    "reviewer_total",
    "review",
    "reviewer",
    "memo",
    "reviewed_at",
    "record_ref",
    "line",
    "note",
    "no_record_reason",
    "observed",
    "card_at_t_min",
    "last_activity_at",
    "purge_at",
    "report_ready_at",
    "instruction",
    "related_card",
    "final",
    "final_view_until",
    "persona_note",
    "value",
    "auto",
    "t_min",
    "facts",
    "changed_after_adaptability",
    "minutes",
}
CANDIDATE_OPTIONAL = {
    "started_at",
    "ends_at",
    "last_activity_at",
    "report_ready_at",
    "purge_at",
    "failed_stage",
    "failed_reason",
    "next_action",
    "previous_session_id",
    "previous_relation",
}


def load_contract(name: str) -> Any:
    return json.loads((CONTRACTS / f"{name}.json").read_text(encoding="utf-8"))


def _kind(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int | float):
        return "number"
    return type(value).__name__


def _pick(item: Any, examples: list[Any]) -> Any:
    if isinstance(item, dict):
        for key in _DISCRIMINANTS:
            match = [
                e
                for e in examples
                if isinstance(e, dict) and key in e and e.get(key) == item.get(key)
            ]
            if match:
                return match[0]
    return examples[0]


def assert_shape(
    actual: Any, expected: Any, path: str = "$", optional: frozenset[str] = frozenset()
) -> None:
    parts = [p.split("[")[0] for p in path.split(".")]
    key, parent = parts[-1], parts[-2] if len(parts) > 1 else ""
    if actual is None:
        assert expected is None or key in NULLABLE, f"{path}: required field is null"
        return
    if key in VOCAB and isinstance(actual, str):
        vocab = STATUS_BY_PARENT.get(parent, VOCAB[key]) if key == "status" else VOCAB[key]
        assert actual in vocab, f"{path}: {actual!r} is not a contract value"
    if isinstance(actual, dict) and isinstance(expected, dict):
        for name in REQUIRED_BY_STATUS.get(actual.get("status"), set()) & set(expected):
            assert actual.get(name) is not None, f"{path}.{name}: required in {actual['status']}"
    if expected is None:
        return
    assert _kind(actual) == _kind(expected), f"{path}: {_kind(actual)} != {_kind(expected)}"
    if isinstance(expected, dict) and key in FREE:
        return
    if isinstance(expected, dict):
        missing, extra = set(expected) - set(actual), set(actual) - set(expected)
        if SUPERSET in path:
            extra = set()
        missing, extra = missing - optional, extra - optional
        assert not missing and not extra, (
            f"{path}: missing {sorted(missing)}, extra {sorted(extra)}"
        )
        for name in expected:
            if name in actual:
                assert_shape(actual[name], expected[name], f"{path}.{name}", optional)
    elif isinstance(expected, list) and expected:
        for index, item in enumerate(actual):
            assert_shape(item, _pick(item, expected), f"{path}[{index}]", optional)


def assert_contract(
    actual: Any, name: str, optional: set[str] | frozenset[str] = frozenset()
) -> None:
    assert_shape(actual, load_contract(name), name, frozenset(optional))
