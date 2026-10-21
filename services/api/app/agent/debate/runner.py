"""DebateGraphRunner: AgentRunner Protocol의 LangGraph 구현(app/agent/runner.py, G-F 동결 시그니처).

자극 하나 = 그래프 1회. api 메일박스가 세션마다 직렬로 부른다. 그래프가 api에 기대는 것은
SessionPorts
(typing·generation·enqueue)뿐이고 나머지 읽기·쓰기는 MCP(debate·rag·assessment)를 거친다.
thread는 `debate:{session_id}`, LangGraph config 메타데이터 키는 `agent_run_id`다.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from app.agent.catalog import Catalog
from app.agent.debate.graph import DebateDeps, DebateLLMs, Sleep, build_graph
from app.agent.llm import Usage
from app.agent.mcp_client import McpRunTools, RunTools
from app.agent.runner import PortsFor, RunResult, Stimulus
from app.ports import SessionPorts, TypingState

log = logging.getLogger(__name__)

RECURSION_LIMIT = 20  # harness.md Agent Loop

ToolsFactory = Callable[[uuid.UUID], AbstractAsyncContextManager[RunTools]]
ScenarioLoader = Callable[[uuid.UUID], Awaitable[dict[str, Any]]]


def thread_id(session_id: object) -> str:
    return f"debate:{session_id}"


def mcp_tools(
    *, debate_url: str, rag_url: str, assessment_url: str, assessment_token: str
) -> ToolsFactory:
    """운영 경로: 실행마다 debate+rag 연결과 assessment 연결(토큰 분리)을 연다."""

    def open_tools(session_id: uuid.UUID) -> AbstractAsyncContextManager[RunTools]:
        return McpRunTools(
            session_id,
            debate_url=debate_url,
            rag_url=rag_url,
            assessment_url=assessment_url,
            assessment_token=assessment_token,
        )

    return open_tools


class DebateGraphRunner:
    def __init__(
        self,
        *,
        llms: DebateLLMs,
        tools: ToolsFactory,
        scenario: ScenarioLoader,
        ports_for: PortsFor,
        checkpointer: BaseCheckpointSaver | None = None,
        scenarios_dir: Path | None = None,
        sleep: Sleep = asyncio.sleep,
        typing_wait: float = 10.0,
        typing_poll: float = 0.5,
        speaker_gap: tuple[float, float] = (1.0, 3.0),
    ) -> None:
        self.llms = llms
        self.tools = tools
        self.scenario = scenario
        self.ports_for = ports_for
        self.scenarios_dir = scenarios_dir
        self.sleep = sleep
        self.typing_wait = typing_wait
        self.typing_poll = typing_poll
        self.speaker_gap = speaker_gap
        self.graph: CompiledStateGraph = build_graph(checkpointer)
        self._catalogs: dict[uuid.UUID, Catalog] = {}
        self.snapshots: list[dict[str, Any]] | None = (
            None  # 테스트에서 리스트를 넣으면 페르소나 입력 기록
        )

    async def catalog(self, session_id: uuid.UUID) -> Catalog:
        if session_id not in self._catalogs:
            scenario = await self.scenario(session_id)
            self._catalogs[session_id] = Catalog.from_scenario(scenario, self.scenarios_dir)
        return self._catalogs[session_id]

    async def run(self, session_id: uuid.UUID, stimulus: Stimulus, run_id: uuid.UUID) -> RunResult:
        started = time.monotonic()
        usage = Usage()
        try:
            catalog = await self.catalog(session_id)
        except Exception as exc:
            log.exception("scenario load failed")
            return RunResult(
                ok=False, status="failed", error=f"scenario: {exc!r}", usage=usage.as_dict()
            )
        state_in = {
            "session_id": str(session_id),
            "run_id": str(run_id),
            "stimulus": {
                "type": stimulus.type,
                "phase": stimulus.phase,
                "generation": stimulus.generation,
                "message_id": str(stimulus.message_id) if stimulus.message_id else None,
                "card_id": stimulus.card_id,
            },
            "phase": stimulus.phase,
        }
        config = {
            "configurable": {"thread_id": thread_id(session_id)},
            "recursion_limit": RECURSION_LIMIT,
            "run_name": "debate_graph",
            "tags": [f"agent_run_id:{run_id}", f"stimulus:{stimulus.type}"],
            "metadata": {"agent_run_id": str(run_id), "session_id": str(session_id)},
        }
        ports = _TypingTracker(self.ports_for(session_id))
        try:
            async with self.tools(session_id) as tools:
                deps = DebateDeps(
                    catalog=catalog,
                    tools=tools,
                    ports=ports,
                    llms=self.llms,
                    usage=usage,
                    sleep=self.sleep,
                    typing_wait=self.typing_wait,
                    typing_poll=self.typing_poll,
                    speaker_gap=self.speaker_gap,
                    snapshots=self.snapshots,
                )
                state = await self.graph.ainvoke(state_in, config, context=deps)
        except Exception as exc:
            log.exception("debate graph failed")
            ports.stop_open()  # 예외로 끊긴 화자의 입력 중 표시를 남기지 않는다
            body = usage.as_dict()
            body["latency_ms"] = int((time.monotonic() - started) * 1000)
            return RunResult(
                ok=False, status="failed", fallback_used=True, error=repr(exc), usage=body
            )
        body = usage.as_dict()
        body["latency_ms"] = int((time.monotonic() - started) * 1000)
        status = state.get("status") or "finished"
        error = state.get("last_error")
        return RunResult(
            ok=status != "failed",
            status=status,
            fallback_used=bool(state.get("fallback_used")),
            error=error,
            decision=state.get("decision"),
            usage=body,
        )


class _TypingTracker:
    """SessionPorts를 그대로 넘기되 typing start 뒤 stop이 오지 않은 자리를 기억한다."""

    def __init__(self, ports: SessionPorts) -> None:
        self._ports = ports
        self.session_id = ports.session_id
        self._open: set[str] = set()

    def send_typing(self, seat: str, state: TypingState) -> None:
        (self._open.add if state == "start" else self._open.discard)(seat)
        self._ports.send_typing(seat, state)

    def get_generation(self) -> int:
        return self._ports.get_generation()

    def candidate_typing(self) -> bool:
        return self._ports.candidate_typing()

    def enqueue(self, stimulus: Stimulus) -> None:
        self._ports.enqueue(stimulus)

    def stop_open(self) -> None:
        for seat in sorted(self._open):
            self.send_typing(seat, "stop")
