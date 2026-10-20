"""리포트 그래프 `collect → draft → approval[interrupt] → finalize`. thread `report:{session_id}`.

draft 생성과 interrupt를 다른 노드로 둔다. LangGraph는 재개할 때 interrupt가 있던 노드를
처음부터 다시 실행하므로, 같은 노드면 LLM 요약이 다시 돈다. approval은 멈추기만 한다.
draft 저장(POST /report/draft)은 그래프 밖에서 소비자가 한다(체크포인트 → draft 저장 → ack).
"""

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from report_worker.api import InternalApi
from report_worker.llm import LLM
from report_worker.report import build_draft


class ReportState(TypedDict, total=False):
    session_id: str
    data: dict[str, Any]
    draft: dict[str, Any]
    usage: dict[str, Any]
    final: dict[str, Any]


def thread_config(session_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": f"report:{session_id}"}}


def build_graph(api: InternalApi, llm: LLM, checkpointer: Any):
    async def collect(state: ReportState) -> ReportState:
        return {"data": await api.collect(state["session_id"])}

    async def draft(state: ReportState) -> ReportState:
        content, usage = await build_draft(state["data"], llm)
        return {"draft": content, "usage": usage}

    def approval(state: ReportState) -> ReportState:
        # 검토 완료(report.approve)가 Command(resume=True)로 같은 thread를 재개한다
        interrupt(state["draft"])
        return {}

    async def finalize(state: ReportState) -> ReportState:
        # 승인한 draft를 그대로 보낸다. api가 정규화 해시로 draft와 같은지 확인한다
        return {"final": await api.save_final(state["session_id"], state["draft"])}

    builder = StateGraph(ReportState)
    builder.add_node("collect", collect)
    builder.add_node("draft", draft)
    builder.add_node("approval", approval)
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "collect")
    builder.add_edge("collect", "draft")
    builder.add_edge("draft", "approval")
    builder.add_edge("approval", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)


def is_paused(snapshot: Any) -> bool:
    """approval의 interrupt에 멈춰 있음."""
    return snapshot.next == ("approval",) and any(t.interrupts for t in snapshot.tasks)


def is_done(snapshot: Any) -> bool:
    return not snapshot.next and "final" in snapshot.values


def has_checkpoint(snapshot: Any) -> bool:
    return bool(snapshot.values) or bool(snapshot.next)
