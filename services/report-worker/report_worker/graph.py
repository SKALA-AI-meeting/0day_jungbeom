"""리포트 그래프 `collect → aggregate → evaluate → draft → approval[interrupt] → finalize`.

thread_id = `report:{session_id}:{eval_round}`. 평가 회차마다 thread가 따로라 새 eval_round는
이전 회차의 interrupt 체크포인트(이전 draft)를 재사용하지 않고 collect부터 돈다. 같은 eval_round의
큐 재시도만 그 thread의 체크포인트에서 이어 간다.

draft와 approval을 나눈 이유: LangGraph는 재개할 때 interrupt가 있던 노드를 처음부터 다시
실행하므로, 같은 노드면 draft 조립(근거 맥락 조회)이 다시 돈다. approval은 멈추기만 한다.
draft 저장(POST /report/draft)은 그래프 밖에서 소비자가 한다(체크포인트 → draft 저장 → ack).
"""

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from report_worker.api import InternalApi
from report_worker.assessment import Assessment
from report_worker.evaluate import (
    EvalContext,
    RefIndex,
    pinned_catalog,
    run_evaluation,
)
from report_worker.llm import LLM, empty_usage
from report_worker.report import aggregate, ai_usage, build_draft

DEFAULT_MISSION = "debate"


class ReportState(TypedDict, total=False):
    session_id: str
    eval_round: int
    session: dict[str, Any]
    record: dict[str, Any]
    rubric: dict[str, Any]
    contributions: dict[str, Any]
    aggregated: dict[str, Any]
    ai_usage: dict[str, Any]
    evaluation: dict[str, Any]
    usage: dict[str, Any]
    draft: dict[str, Any]
    final: dict[str, Any]


@dataclass(frozen=True)
class Deps:
    api: InternalApi
    assessment: Assessment
    llm: LLM
    scenarios_dir: Path


def thread_config(session_id: str, eval_round: int) -> dict[str, Any]:
    return {"configurable": {"thread_id": f"report:{session_id}:{eval_round}"}}


def evaluation_run_id(session_id: str, eval_round: int) -> str:
    """`uuid5(session_id, "evaluate:" + eval_round)`. 큐 재시도는 같은 round라 같은 run_id."""
    try:
        namespace = uuid.UUID(str(session_id))
    except ValueError:  # 픽스처의 "sess-1" 같은 id
        namespace = uuid.uuid5(uuid.NAMESPACE_URL, str(session_id))
    return str(uuid.uuid5(namespace, f"evaluate:{eval_round}"))


def mission_of(session: dict[str, Any]) -> str:
    position = session.get("position") or {}
    scenario = position.get("scenario") or {}
    return position.get("mission_id") or scenario.get("mission_id") or DEFAULT_MISSION


def scenario_of(session: dict[str, Any]) -> dict[str, Any]:
    return (session.get("position") or {}).get("scenario") or {}


def _evaluation_view(saved: dict[str, Any]) -> dict[str, Any]:
    keys = ("run_id", "rubric_version", "prompt_versions", "model", "elements", "dimensions")
    return {k: saved[k] for k in keys}


def build_graph(deps: Deps, checkpointer: Any):
    api, assessment, llm = deps.api, deps.assessment, deps.llm

    async def collect(state: ReportState) -> ReportState:
        session_id = state["session_id"]
        return {
            "record": await assessment.get_session_record(session_id),
            "rubric": await assessment.get_rubric(session_id),
            "contributions": await assessment.get_contributions(session_id),
            "session": await api.get_session(session_id),
        }

    async def aggregate_node(state: ReportState) -> ReportState:
        session_id, record = state["session_id"], state["record"]
        calls = await api.assistant_calls(session_id)
        started_at = (record.get("session") or {}).get("started_at")
        return {
            "aggregated": aggregate(state["session"], record, state["contributions"]),
            "ai_usage": ai_usage(calls, record.get("facts", {}), started_at),
        }

    async def evaluate(state: ReportState) -> ReportState:
        session_id = state["session_id"]
        run_id = evaluation_run_id(session_id, state["eval_round"])
        usage = empty_usage(llm.model)
        # 같은 run_id로 저장된 평가가 있으면 LLM을 다시 부르지 않는다(재전달 멱등, 저장 직후
        # 체크포인트 전에 죽어도 요소 요약까지 복구)
        saved = await api.get_evaluation(session_id, run_id)
        if saved is not None:
            return {"evaluation": _evaluation_view(saved), "usage": {**usage, "reused": True}}
        mission = mission_of(state["session"])
        prompts, forbidden = pinned_catalog(
            scenario_of(state["session"]), deps.scenarios_dir, mission
        )
        ctx = EvalContext(
            record=state["record"],
            rubric=state["rubric"],
            refs=RefIndex(state["record"], state["contributions"]),
            prompts=prompts,
            forbidden=forbidden,
        )
        body = await run_evaluation(llm, ctx, usage)
        result = await assessment.save_evaluation(
            {"session_id": session_id, "run_id": run_id, **body}
        )
        evaluation = {"run_id": run_id, **body}
        if result.get("existing"):  # 다른 실행이 먼저 저장했다. 저장된 값이 정본
            stored = await api.get_evaluation(session_id, run_id)
            if stored is not None:
                evaluation = _evaluation_view(stored)
        return {"evaluation": evaluation, "usage": {**usage, "reused": False}}

    async def draft(state: ReportState) -> ReportState:
        session_id = state["session_id"]

        async def span(message_id: str) -> dict[str, Any]:
            return await assessment.get_transcript_span(session_id, message_id, 5, 3)

        content = await build_draft(
            session=state["session"],
            record=state["record"],
            rubric=state["rubric"],
            contributions=state["contributions"],
            aggregated=state["aggregated"],
            evaluation=state["evaluation"],
            usage_ai=state["ai_usage"],
            span=span,
            forbidden=pinned_catalog(
                scenario_of(state["session"]), deps.scenarios_dir, mission_of(state["session"])
            )[1],
        )
        return {"draft": content}

    def approval(state: ReportState) -> ReportState:
        # 검토 완료(report.approve)가 Command(resume=True)로 같은 thread를 재개한다
        interrupt({"session_id": state["session_id"], "eval_round": state["eval_round"]})
        return {}

    async def finalize(state: ReportState) -> ReportState:
        # 승인한 draft content를 그대로 보낸다(해시 동일). 조정은 api가 GET 때 병합한다
        return {"final": await api.save_final(state["session_id"], state["draft"])}

    builder = StateGraph(ReportState)
    for name, node in (
        ("collect", collect),
        ("aggregate", aggregate_node),
        ("evaluate", evaluate),
        ("draft", draft),
        ("approval", approval),
        ("finalize", finalize),
    ):
        builder.add_node(name, node)
    builder.add_edge(START, "collect")
    builder.add_edge("collect", "aggregate")
    builder.add_edge("aggregate", "evaluate")
    builder.add_edge("evaluate", "draft")
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
