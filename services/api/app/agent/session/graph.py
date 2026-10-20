"""세션 그래프 조립(docs/agent/design.md 전이표).

START → route → classify → (negotiate | respond)   지원자 메시지
              → inject → observe                   카드 묶음(카드 실행 뒤 직전 관찰 창 닫기)
              → division                           보드 확정·재배정
              → close                              종료(열린 창 닫기·약속 이행 확정)
  (분류 뒤 노드·카드·종료 모두 마지막에 account가 이번 실행 토큰을 세션 예산에서 뺀다)
체크포인터는 PostgresSaver(thread `session:{id}`), 자극마다 한 번 실행한다.
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.session.cards import inject
from app.agent.session.common import RunDeps
from app.agent.session.division import division_node, negotiate
from app.agent.session.nodes import account, classify_node, respond, route
from app.agent.session.observing import close, observe_node
from app.agent.session.state import SessionState

RECURSION_LIMIT = 20


def thread_id(session_id: object) -> str:
    return f"session:{session_id}"


def build_graph(checkpointer: BaseCheckpointSaver | None) -> CompiledStateGraph:
    builder = StateGraph(SessionState, context_schema=RunDeps)
    builder.add_node("route", route)
    builder.add_node("classify", classify_node)
    builder.add_node("negotiate", negotiate)
    builder.add_node("respond", respond)
    builder.add_node("inject", inject)
    builder.add_node("observe", observe_node)
    builder.add_node("division", division_node)
    builder.add_node("close", close)
    builder.add_node("account", account)
    builder.add_edge(START, "route")
    builder.add_edge("inject", "observe")
    for node in ("negotiate", "respond", "observe", "division", "close"):
        builder.add_edge(node, "account")  # 실행 사용량을 세션 예산에 반영
    builder.add_edge("account", END)
    return builder.compile(checkpointer=checkpointer)
