"""세션 상태 이름·순서와 공용 오류.

session·messages·documents가 서로 import하지 않도록 따로 둔다.
"""

# 진행 순서. 멱등 판단("이미 지났다")에 쓴다. cancelled·failed는 끝 상태라 따로 다룬다.
ORDER = [
    "invited",
    "in_progress",
    "reporting",
    "completed",
    "report_ready",
    "approving",
    "reviewed",
]
# 보고 종료 뒤(디브리핑을 보여 주는 정상 종료 상태)
ENDED_STATUSES = set(ORDER[ORDER.index("completed") :])


class SessionError(Exception):
    """code: not_found(404), conflict(409), expired·cancelled(410), session_ending(409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
