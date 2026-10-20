"""SessionAgentRunner: AgentRunner Protocol의 LangGraph 구현(app/agent/runner.py).

실행 하나 = 자극 하나 = 그래프 1회. 두 MCP 연결은 이 함수 안에서 열고 닫는다(같은 task).
결과(ok·fallback_used·error)와 usage는 노드가 RunDeps에 남긴 값으로 RunResult를 만든다.
"""

import asyncio
import uuid
from collections.abc import Mapping
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.agent.llm import BaseLLM, Usage
from app.agent.mcp_client import McpClient
from app.agent.runner import Broadcast, RunResult, Stimulus
from app.agent.session.common import RunDeps
from app.agent.session.graph import RECURSION_LIMIT, build_graph, thread_id
from app.agent.session.store import AgentStore


def checkpoint_conninfo(database_url: str) -> str:
    """SQLAlchemy URL(postgresql+asyncpg://) → psycopg URL."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


class SessionAgentRunner:
    def __init__(
        self,
        *,
        llm: BaseLLM,
        mcp_urls: Mapping[str, str],
        store: AgentStore,
        database_url: str,
        broadcast: Broadcast | None = None,
        roles: Mapping[str, BaseLLM] | None = None,
    ) -> None:
        self.llm = llm  # 역할이 정해지지 않은 호출과 roles에 없는 역할
        self.roles = dict(roles or {})
        self.mcp_urls = dict(mcp_urls)
        self.store = store
        self._conninfo = checkpoint_conninfo(database_url)
        self._broadcast = broadcast
        self._pool: AsyncConnectionPool | None = None
        self._graph: CompiledStateGraph | None = None
        self._init_lock = asyncio.Lock()

    async def graph(self) -> CompiledStateGraph:
        """첫 실행에서 체크포인터 풀을 열고 테이블을 만든다(이후 재사용)."""
        async with self._init_lock:
            if self._graph is None:
                pool = AsyncConnectionPool(
                    self._conninfo,
                    open=False,
                    max_size=4,
                    kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
                )
                await pool.open()
                saver = AsyncPostgresSaver(pool)
                await saver.setup()
                self._pool, self._graph = pool, build_graph(saver)
        return self._graph

    async def aclose(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool, self._graph = None, None

    async def run(self, session_id: uuid.UUID, stimulus: Stimulus, run_id: uuid.UUID) -> RunResult:
        graph = await self.graph()
        usage = Usage()

        async def progress(actor: str, node: str, status: str, tool: str | None) -> None:
            if self._broadcast is None:
                return
            payload: dict[str, Any] = {
                "run_id": str(run_id),
                "actor": actor,
                "node": node,
                "status": status,
            }
            if tool:
                payload["tool"] = tool
            await self._broadcast(session_id, "agent.progress", payload)

        async with McpClient(self.mcp_urls, session_id) as mcp:
            deps = RunDeps(
                llm=self.llm,
                mcp=mcp,
                store=self.store,
                usage=usage,
                progress=progress,
                roles=self.roles,
            )
            config = {
                "configurable": {"thread_id": thread_id(session_id)},
                "recursion_limit": RECURSION_LIMIT,
                "run_name": f"session_graph:{stimulus.type}",
                "tags": [f"run_id:{run_id}"],
                # 메타데이터 키 "run_id"는 LangGraph가 실행 식별자로 써서, 같은 값으로 다시 부르면
                # 끝난
                # 실행으로 보고 아무 노드도 돌리지 않는다(카드 재시도가 안 됨). 그래서 다른 이름을
                # 쓴다.
                # LLM 호출마다의 trace에는 Trace.config()가 run_id 메타데이터를 따로 붙인다
                "metadata": {"agent_run_id": str(run_id), "session_id": str(session_id)},
            }
            await graph.ainvoke(
                {
                    "session_id": str(session_id),
                    "run_id": str(run_id),
                    "stimulus": _stimulus(stimulus),
                },
                config,
                context=deps,
            )
        outcome = deps.outcome
        return RunResult(
            ok=outcome.ok,
            fallback_used=outcome.fallback_used,
            error=outcome.error,
            reply_fallback=outcome.reply_fallback,
            usage=usage.as_dict(),
        )


def _stimulus(stimulus: Stimulus) -> dict[str, Any]:
    body: dict[str, Any] = {"type": stimulus.type}
    if stimulus.message_id is not None:
        body["message_id"] = str(stimulus.message_id)
    if stimulus.event_ids:
        body["event_ids"] = [str(e) for e in stimulus.event_ids]
    if stimulus.task_event_ids:
        body["task_event_ids"] = [str(e) for e in stimulus.task_event_ids]
    return body
