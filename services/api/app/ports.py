"""SessionPorts: api/agent 경계(R6-d, contracts.md "세션 메일박스"). G-F 동결.

그래프가 api 내부 상태에 닿는 길은 이 네 메서드뿐이고 나머지 읽기·쓰기는 MCP를 거친다.
포트 하나는 세션 하나에 묶인다(api가 세션별로 만들어 그래프에 넘긴다). 모두 메모리 접근이라
동기 메서드다: api는 단일 프로세스이고 generation의 유일한 쓰기 주체이므로 메모리 값을 돌려준다.
메일박스 구현(app/mailbox.py)과 실제 포트는 api 트랙이 만든다.
"""

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from app.agent.runner import Stimulus

TypingState = Literal["start", "stop"]


class SessionPorts(Protocol):
    session_id: uuid.UUID

    def send_typing(self, seat: str, state: TypingState) -> None:
        """hub로 WS `typing{participant: seat, state}`를 보낸다(페르소나 입력 중 표시)."""
        ...

    def get_generation(self) -> int:
        """현재 sessions.generation. 그래프는 게시 직전 실행 시작 값과 비교한다."""
        ...

    def candidate_typing(self) -> bool:
        """지원자 typing이 유효한지(5초 갱신·6초 만료). wait_typing 노드가 읽는다."""
        ...

    def enqueue(self, stimulus: "Stimulus") -> None:
        """이 세션 메일박스에 자극을 넣는다. run_id·agent_runs 행은 api가 새로 만든다."""
        ...


@dataclass
class FakeSessionPorts:
    """테스트용 가짜 포트(가짜 hub). 보낸 typing과 넣은 자극을 기록한다."""

    session_id: uuid.UUID
    generation: int = 0
    typing: bool = False
    typing_sent: list[tuple[str, TypingState]] = field(default_factory=list)
    enqueued: list["Stimulus"] = field(default_factory=list)

    def send_typing(self, seat: str, state: TypingState) -> None:
        self.typing_sent.append((seat, state))

    def get_generation(self) -> int:
        return self.generation

    def candidate_typing(self) -> bool:
        return self.typing

    def enqueue(self, stimulus: "Stimulus") -> None:
        self.enqueued.append(stimulus)
