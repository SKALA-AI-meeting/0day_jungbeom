"""AgentRunner 경계(docs/agent/design.md). 자극 하나에 그래프를 한 번 실행한다.

api는 이 Protocol만 알고, 실제 LangGraph 구현(agent-session 트랙)이 같은 시그니처로 갈아 끼운다.
같은 run_id의 재실행은 메시지(run_id, seq) 등 멱등 키로 중복이 생기지 않아야 한다. FakeAgentRunner는
LLM 없이 고정 문장을 post_message 하는 테스트·개발용 구현이다.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

StimulusType = Literal["message", "event", "division", "end"]


@dataclass(frozen=True)
class Stimulus:
    """message: message_id. event: 같은 due_at 행 묶음(card order)의 event_ids. division: 주담당이
    보드로 분업을 확정했거나 재배정한 task_events. end: 없음."""

    type: StimulusType
    message_id: uuid.UUID | None = None
    event_ids: tuple[uuid.UUID, ...] = ()
    task_event_ids: tuple[uuid.UUID, ...] = ()

    @property
    def ref_ids(self) -> list[uuid.UUID]:
        """agent_runs.ref_ids에 남기는 값."""
        if self.message_id:
            return [self.message_id]
        return list(self.event_ids or self.task_event_ids)


# 문서를 보내는 카드에서 send_document가 재시도 뒤에도 실패했을 때 RunResult.error의 접두어.
# 스케줄러가 이 값을 보고 그 이벤트 행에 document_missing=true를 남긴다(docs/common/data-model.md).
DOCUMENT_MISSING = "document_missing"


@dataclass
class RunResult:
    ok: bool = True
    fallback_used: bool = False
    error: str | None = None
    # 지원자 메시지에 대한 페르소나 응답 자체가 LLM 실패로 고정 문장이 됨(분류 폴백은 제외).
    # api가 세션의 llm_failures를 센다(연속 3회 → 세션 failed, 정상 응답이면 0)
    reply_fallback: bool = False
    # agent_runs.usage로 저장(llm_calls, retries, tokens_in, tokens_out, latency_ms, tool_calls)
    usage: dict[str, Any] = field(default_factory=dict)


class AgentRunner(Protocol):
    async def run(
        self, session_id: uuid.UUID, stimulus: Stimulus, run_id: uuid.UUID
    ) -> RunResult: ...


# business-mcp post_message와 같은 인자. 운영에서는 MCP 경유, 테스트·개발에서는 내부 저장을 직접
# 부른다.
PostMessage = Callable[..., Awaitable[Any]]
Broadcast = Callable[[uuid.UUID, str, dict[str, Any]], Awaitable[None]]

FAKE_REPLY = "네, 확인했어요. 이어서 진행할게요."
FAKE_CARD = "[fake] 카드 실행"
# 노드별 고정 seq 슬롯(docs/agent/design.md): respond 응답=1, inject 카드=1
RESPOND_SEQ = 1
INJECT_SEQ = 1


class FakeAgentRunner:
    """message → 동료 고정 응답 1건, event → 이벤트마다 시스템 고정 문장 1건, division·end → 응답
    없음.
    """

    def __init__(
        self,
        post_message: PostMessage,
        broadcast: Broadcast | None = None,
        reply: str = FAKE_REPLY,
        reply_channel: str = "team",
    ) -> None:
        self._post = post_message
        self._broadcast = broadcast
        self._reply = reply
        self._channel = reply_channel
        self.calls: list[tuple[uuid.UUID, Stimulus, uuid.UUID]] = []

    async def _progress(self, session_id: uuid.UUID, run_id: uuid.UUID, status: str) -> None:
        if self._broadcast is not None:
            payload = {"run_id": str(run_id), "actor": "colleague", "node": "respond"}
            await self._broadcast(session_id, "agent.progress", {**payload, "status": status})

    async def run(self, session_id: uuid.UUID, stimulus: Stimulus, run_id: uuid.UUID) -> RunResult:
        self.calls.append((session_id, stimulus, run_id))
        if stimulus.type == "message":
            await self._progress(session_id, run_id, "started")
            await self._post(
                session_id=session_id,
                channel=self._channel,
                sender="colleague",
                content=self._reply,
                run_id=run_id,
                seq=RESPOND_SEQ,
                meta={"model": "fake"},
            )
            await self._progress(session_id, run_id, "finished")
        elif stimulus.type == "event":
            # 묶음 안 카드마다 슬롯이 겹치지 않게 카드 순번을 더한다
            for index, event_id in enumerate(stimulus.event_ids):
                await self._post(
                    session_id=session_id,
                    channel="team",
                    sender="system",
                    content=FAKE_CARD,
                    event_id=event_id,
                    run_id=run_id,
                    seq=INJECT_SEQ + index,
                    meta={"model": "fake"},
                )
        return RunResult(ok=True, usage={"llm_calls": 0})


@dataclass
class AssistantResult:
    """어시스턴트 응답. cited_docs는 인용한 회사 문서 id(공개된 것만)."""

    content: str
    cited_docs: list[str] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)


class AssistantRunner(Protocol):
    """POST /sessions/{id}/assistant의 훅. agent-assistant 트랙이 같은 시그니처로 갈아 끼운다.

    api가 요청·응답 메시지와 assistant_calls를 기록하고 60회 한도를 막으므로, 구현은 답만 만든다.
    """

    async def answer(
        self, session_id: uuid.UUID, prompt: str, call_id: uuid.UUID
    ) -> AssistantResult: ...


FAKE_ASSISTANT = "[fake] 어시스턴트 응답입니다. 공개된 회사 문서를 참고해 답합니다."


class FakeAssistantRunner:
    """LLM 없이 고정 문장을 돌려주는 개발·테스트용 구현."""

    async def answer(
        self, session_id: uuid.UUID, prompt: str, call_id: uuid.UUID
    ) -> AssistantResult:
        return AssistantResult(content=FAKE_ASSISTANT, cited_docs=[])
