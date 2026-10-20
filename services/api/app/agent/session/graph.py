"""세션 그래프 조립. START → route → (classify → respond | inject | close) → END.

체크포인터는 PostgresSaver(thread `session:{id}`), 자극마다 한 번 실행한다.
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.session.nodes import RunDeps, classify_node, close, inject, respond, route
from app.agent.session.state import SessionState

RECURSION_LIMIT = 20


def thread_id(session_id: object) -> str:
    return f"session:{session_id}"


def build_graph(checkpointer: BaseCheckpointSaver | None) -> CompiledStateGraph:
    builder = StateGraph(SessionState, context_schema=RunDeps)
    builder.add_node("route", route)
    builder.add_node("classify", classify_node)
    builder.add_node("respond", respond)
    builder.add_node("inject", inject)
    builder.add_node("close", close)
    builder.add_edge(START, "route")
    builder.add_edge("classify", "respond")
    builder.add_edge("respond", END)
    builder.add_edge("inject", END)
    builder.add_edge("close", END)
    return builder.compile(checkpointer=checkpointer)
