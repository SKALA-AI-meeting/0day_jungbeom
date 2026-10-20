"""세션 그래프 State(docs/agent/design.md "세션 그래프"). thread `session:{id}`에 체크포인트된다.

설계의 필드를 모두 선언한다. 이번 단계(agent-min)는 respond 경로만 쓰므로 negotiate_round·division·
current_element·window_start·summary 등은 기본값으로 둔다(M2 agent-session이 채운다).
"""

from typing import Any, TypedDict

TOKEN_BUDGET = 300_000  # 세션 토큰 예산(입력+출력, 재시도 포함). harness.md Agent Loop


class SessionState(TypedDict, total=False):
    session_id: str
    phase: str  # kickoff → negotiate → work → review → submit → done
    negotiate_round: int
    division: dict[str, str] | None  # {"1": "candidate", ...}. 확정 전 None
    scenario: dict[str, Any] | None  # 채용 건 고정 시나리오(회사 문서 본문 제외)
    current_element: str | None  # 열린 관찰 창의 요소
    window_start: float | None  # 열린 창의 시작(카드 due_at, 분)
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
        "parts": [],
        "instructions": [],
        "agreements": [],
        "progress": {},
        "draft_written": False,
        "final_written": False,
    }


def defaults(session_id: str) -> SessionState:
    """thread의 첫 실행에서 비어 있는 필드를 채운다."""
    return SessionState(
        session_id=session_id,
        phase="kickoff",
        negotiate_round=0,
        division=None,
        scenario=None,
        current_element=None,
        window_start=None,
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
