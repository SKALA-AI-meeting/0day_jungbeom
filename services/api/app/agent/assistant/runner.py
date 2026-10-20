"""AssistantGraphRunner: AssistantRunner Protocol의 LangGraph 구현(app/agent/runner.py).

호출 하나 = 그래프 1회. 요청·응답 메시지 저장, assistant_calls, 60회 한도는 api(라우터)가 맡으므로
여기서는 답·인용·usage만 만든다. 체크포인터는 세션 그래프와 같은 PostgresSaver 저장소를 쓰고 thread
만 다르다(`assistant:{session_id}`).

질문은 그래프에 넣기 전에 마스킹하고 토큰 상한으로 자른다(체크포인트·LLM·검색 query 모두 마스킹
뒤 값).
같은 세션의 호출은 세션별 Lock으로 한 번에 하나만 돈다(동시 요청이 history를 덮어쓰지 않게). 세션
그래프 Lock과는 별개라 동료 응답을 기다리지 않는다.
"""

import asyncio
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.assistant import tokens
from app.agent.assistant.graph import (
    QUESTION_TOKENS,
    AssistantDeps,
    Tools,
    build_graph,
    thread_id,
)
from app.agent.llm import BaseLLM, Usage
from app.agent.mcp_client import ASSISTANT_TOOLS, RAG, McpClient
from app.agent.runner import AssistantResult, Broadcast
from app.agent.session.runner import checkpoint_conninfo
from app.masking import mask
from app.models import Invite, Position, Session

RECURSION_LIMIT = 10

RagFactory = Callable[[uuid.UUID], AbstractAsyncContextManager[Tools]]
ScenarioLoader = Callable[[uuid.UUID], Awaitable[dict[str, Any]]]


def mcp_rag(url: str) -> RagFactory:
    """운영 경로: 호출마다 rag-mcp 연결을 열고 어시스턴트 허용 목록으로 고정한다."""

    @asynccontextmanager
    async def open_rag(session_id: uuid.UUID) -> AsyncIterator[Tools]:
        async with McpClient({RAG: url}, session_id) as client:
            yield client.scope(ASSISTANT_TOOLS)

    return open_rag


def db_scenario(factory: async_sessionmaker[AsyncSession]) -> ScenarioLoader:
    """세션의 채용 건에 고정된 scenario(프롬프트·guard 패턴 복사본)를 읽는다."""

    async def load(session_id: uuid.UUID) -> dict[str, Any]:
        async with factory() as db:
            return await db.scalar(
                select(Position.scenario)
                .join(Invite, Invite.position_id == Position.id)
                .join(Session, Session.invite_id == Invite.id)
                .where(Session.id == session_id)
            )

    return load


class AssistantGraphRunner:
    def __init__(
        self,
        *,
        llm: BaseLLM,
        rag: RagFactory,
        scenario: ScenarioLoader,
        database_url: str,
        broadcast: Broadcast | None = None,
    ) -> None:
        self.llm = llm
        self.rag = rag
        self.scenario = scenario
        self._conninfo = checkpoint_conninfo(database_url)
        self._broadcast = broadcast
        self._pool: AsyncConnectionPool | None = None
        self._graph: CompiledStateGraph | None = None
        self._init_lock = asyncio.Lock()
        self._session_locks: defaultdict[uuid.UUID, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def graph(self) -> CompiledStateGraph:
        """첫 호출에서 체크포인터 풀을 열고 테이블을 만든다(이후 재사용)."""
        async with self._init_lock:
            if self._graph is None:
                pool = AsyncConnectionPool(
                    self._conninfo,
                    open=False,
                    min_size=1,
                    max_size=2,
                    kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
                )
                try:
                    await pool.open()
                    saver = AsyncPostgresSaver(pool)
                    await saver.setup()
                except BaseException:
                    # 초기화 실패·취소 때 연 연결을 남기지 않는다(다음 호출이 다시 시도)
                    await pool.close()
                    raise
                self._pool, self._graph = pool, build_graph(saver)
        return self._graph

    async def aclose(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool, self._graph = None, None

    async def answer(
        self, session_id: uuid.UUID, prompt: str, call_id: uuid.UUID
    ) -> AssistantResult:
        async with self._session_locks[session_id]:
            return await self._answer(session_id, prompt, call_id)

    async def _answer(
        self, session_id: uuid.UUID, prompt: str, call_id: uuid.UUID
    ) -> AssistantResult:
        graph = await self.graph()
        question = mask(prompt).strip()
        limited = tokens.truncate(question, QUESTION_TOKENS)
        scenario = await self.scenario(session_id)
        usage = Usage()

        async def progress(node: str, status: str, tool: str | None) -> None:
            # 계약 agent.progress(actor=assistant). run_id 자리에 call_id를 쓴다
            if self._broadcast is None:
                return
            payload: dict[str, Any] = {
                "run_id": str(call_id),
                "actor": "assistant",
                "node": node,
                "status": status,
            }
            if tool:
                payload["tool"] = tool
            await self._broadcast(session_id, "agent.progress", payload)

        async with self.rag(session_id) as rag:
            deps = AssistantDeps(
                llm=self.llm, rag=rag, scenario=scenario, usage=usage, progress=progress
            )
            config = {
                "configurable": {"thread_id": thread_id(session_id)},
                "recursion_limit": RECURSION_LIMIT,
                "run_name": "assistant_graph",
                "tags": [f"call_id:{call_id}"],
                "metadata": {"call_id": str(call_id), "session_id": str(session_id)},
            }
            state = await graph.ainvoke(
                {
                    "session_id": str(session_id),
                    "call_id": str(call_id),
                    "prompt": limited,
                    "prompt_truncated": limited != question,
                },
                config,
                context=deps,
            )
        body = usage.as_dict()
        body["fallback_used"] = bool(state.get("fallback_used"))
        return AssistantResult(content=state["content"], cited_docs=state["cited_docs"], usage=body)
