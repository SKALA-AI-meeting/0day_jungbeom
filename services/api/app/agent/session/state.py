"""세션 그래프 State(docs/agent/design.md "세션 그래프"). thread `session:{id}`에 체크포인트된다.

설계의 18필드를 모두 선언한다. division은 확정된 분업의 파트별 담당({"1": "candidate", ...})이고,
work_notes는 동료의 작업 기억이다(요약으로 접히지 않음, 갱신표는 docs/agent/design.md).
"""

from typing import Any, TypedDict

TOKEN_BUDGET = 300_000  # 세션 토큰 예산(입력+출력, 재시도 포함). harness.md Agent Loop


class SessionState(TypedDict, total=False):
    session_id: str
    phase: str  # kickoff → division → work → checkin → review → submit → reporting → done
    negotiate_round: int
    division: dict[str, str] | None  # {"1": "candidate", ...}. 확정 전 None
    scenario: dict[str, Any] | None  # 채용 건 고정 시나리오(회사 문서 본문 제외)
    current_card: str | None  # 열린 관찰 창의 카드 id(요소 카드만)
    window_start: float | None  # 열린 창의 시작(카드 due_at, planning_division은 0, 분)
    report_requested: bool  # 팀장 보고 요청이 이미 나갔는지
    stimulus: dict[str, Any]  # {type, message_id?, event_ids?, classification?}
    run_id: str
    seq: int  # 이번 실행에서 마지막으로 쓴 노드 슬롯(seq.py)
    handled_stimuli: list[str]  # 처리 끝난 message_id·event_id·"end:<run_id>"
    recent_messages: list[dict[str, Any]]  # 최근 메시지(오래된 것부터, 최대 RECENT_KEEP)
    summary: str  # 접힌 오래된 대화 요약
    work_notes: dict[str, Any]  # 동료 작업 기억(요약으로 접히지 않음)
    tool_calls_used: int  # 모델이 고른 도구 호출 누적
    token_budget_left: int
    last_error: str | None


def empty_work_notes() -> dict[str, Any]:
    return {
        "parts": [],  # 확정 분업에서 동료 담당(colleague·both) 파트 번호
        "instructions": [],  # [{t_min, text, keywords, part_no, source_message_id}]
        "agreements": [],
        "progress": {},  # {"4": "사례 후보 추리는 중"}. 말한 것만
        "sent": {},  # {"4": 2}. 파트별 마지막으로 보낸 버전
        "feedback": [],  # [{document_id, version, part_no, text, source_message_id}]
        "disagree_target": None,
        "proposal": None,  # 분업 되돌림 때 동료가 낸 대안(다음 위반이면 이대로 확정)
    }


def defaults(session_id: str) -> SessionState:
    """thread의 첫 실행에서 비어 있는 필드를 채운다."""
    return SessionState(
        session_id=session_id,
        phase="kickoff",
        negotiate_round=0,
        division=None,
        scenario=None,
        current_card=None,
        window_start=None,
        report_requested=False,
        stimulus={},
        run_id="",
        seq=0,
        handled_stimuli=[],
        recent_messages=[],
        summary="",
        work_notes=empty_work_notes(),
        tool_calls_used=0,
        token_budget_left=TOKEN_BUDGET,
        last_error=None,
    )
