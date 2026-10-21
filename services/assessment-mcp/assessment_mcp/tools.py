"""assessment-mcp 도구 6개(변경 2, 조회 4). api 내부 REST로 전달·조립만 하고 판단은 api가 한다.

반환은 `{ok, data}` 또는 `{ok:false, error:{code, message, retryable}}`. 목록·입출력 정본은
docs/common/contracts.md "assessment-mcp". 멱등 키((session_id, card_id), (session_id, run_id))는
가공 없이 그대로 보낸다. 토큰 검사는 server.py 미들웨어가 한다.
"""

import asyncio
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from assessment_mcp import client
from assessment_mcp.server import mcp

SessionId = Annotated[str, Field(description="세션 ID. 호출 코드가 주입한다.")]
RunId = Annotated[str, Field(min_length=1, description="실행 run ID(멱등 키)")]
Phase = Literal["keyword", "problem", "solution", "proposal"]
SLOT_PHASES = ("keyword", "problem", "solution")
PHASES = (*SLOT_PHASES, "proposal")
# completed 이후 상태. 이 밖이면(실패 세션 포함) 평가 입력을 만들지 않는다(conflict)
AFTER_COMPLETED = {"completed", "report_ready", "approving", "reviewed"}
MESSAGE_PAGE = 1000


def _base(session_id: str) -> str:
    return f"/internal/sessions/{session_id}"


# ───────────── 변경 ─────────────


@mcp.tool
async def record_observation(
    session_id: SessionId,
    card_id: Annotated[str, Field(min_length=1, description="발동한 카드 ID")],
    phase: Annotated[Phase, Field(description="카드가 속한 단계")],
    run_id: RunId,
    trigger_message_id: Annotated[
        str | None, Field(description="카드 첫 발언 메시지 ID(honesty_credit은 단계 시작 안내)")
    ] = None,
) -> dict[str, Any]:
    """카드 발동을 기록한다. 카드 첫 발언이 게시된 뒤 카드마다 한 번 부른다.

    (session_id, card_id)로 멱등이라 다시 불러도 기존 기록을 돌려준다. element는 api가 카드에서
    정한다. 결과는 {observation_id, fired_at, t_min}.
    """
    body: dict[str, Any] = {"card_id": card_id, "phase": phase, "run_id": run_id}
    if trigger_message_id is not None:
        body["trigger_message_id"] = trigger_message_id
    return await client.call("POST", f"{_base(session_id)}/observations", json=body)


class DimensionEvaluation(BaseModel):
    dimension_id: str = Field(description="평가표 차원 ID(19개 중 하나)")
    level: int | None = Field(ge=1, le=5, description="수준 1~5, 기록 없음이면 null")
    no_record_reason: str | None = Field(
        default=None, description="level이 null일 때만: 기록 없음 사유 코드"
    )
    evidence_refs: list[str] = Field(description="근거 참조(msg:<id> 등)")
    rationale: str = Field(description="판단 이유 1~3문장")
    confidence: Literal["high", "medium", "low"] | None = Field(
        description="확신도, 기록 없음이면 null"
    )


class ElementSummary(BaseModel):
    element: str = Field(description="요소 ID")
    level: int | None = Field(ge=1, le=5, description="차원 평균 반올림, 모두 기록 없음이면 null")
    summary: str = Field(description="요소 요약 1~2줄")
    dimension_count: int = Field(ge=0, description="차원 수")
    no_record_count: int = Field(ge=0, description="기록 없음 차원 수")


@mcp.tool
async def save_evaluation(
    session_id: SessionId,
    run_id: RunId,
    rubric_version: Annotated[str, Field(min_length=1, description="get_rubric의 척도 버전")],
    prompt_versions: Annotated[
        dict[str, str],
        Field(description="평가 프롬프트 해시 맵 {common, <element>: hash}(5요소 모두)"),
    ],
    model: Annotated[str, Field(min_length=1, description="평가 모델 이름")],
    dimensions: Annotated[
        list[DimensionEvaluation], Field(description="차원 평가 행(19개 차원마다 정확히 한 행)")
    ],
    elements: Annotated[list[ElementSummary], Field(description="요소 요약 행(5요소)")],
) -> dict[str, Any]:
    """평가 결과(차원 행·요소 요약·실행 메타)를 저장한다.

    (session_id, run_id)로 멱등이라 같은 run_id 재호출은 저장하지 않고 existing=true와 기존 결과를
    돌려준다. 차원 목록·사유 코드·근거 참조 검증은 api가 하고 위반이면 invalid_input. 결과는
    {run_id, existing, saved}.
    """
    body = {
        "run_id": run_id,
        "rubric_version": rubric_version,
        "prompt_versions": prompt_versions,
        "model": model,
        "dimensions": [d.model_dump(exclude_unset=True) for d in dimensions],
        "elements": [e.model_dump(exclude_unset=True) for e in elements],
    }
    return await client.call("POST", f"{_base(session_id)}/evaluations", json=body)


# ───────────── 조회 ─────────────


@mcp.tool
async def get_rubric(session_id: SessionId) -> dict[str, Any]:
    """세션 채용 건에 복사된 평가 척도를 조회한다.

    5요소·19차원의 정의와 수준 1~5 앵커, 기록 없음 사유 목록, 카드별 관찰 창 규칙, rubric_version을
    돌려준다.
    """
    return await client.call("GET", f"{_base(session_id)}/rubric")


@mcp.tool
async def get_transcript_span(
    session_id: SessionId,
    message_id: Annotated[str, Field(min_length=1, description="근거 메시지 ID")],
    before: Annotated[int, Field(ge=0, le=50, description="앞 메시지 수(기본 5)")] = 5,
    after: Annotated[int, Field(ge=0, le=50, description="뒤 메시지 수(기본 3)")] = 3,
) -> dict[str, Any]:
    """근거 메시지와 그 앞뒤 맥락(기본 앞 5·뒤 3)을 조회한다.

    리포트에 근거 장면을 보여 주는 용도이며 평가 판단 입력을 자르는 용도가 아니다. 결과는
    {target, before, after}이고 메시지마다 의도 분류·발언 경위가 함께 온다.
    """
    params = {"message_id": message_id, "before": before, "after": after}
    return await client.call("GET", f"{_base(session_id)}/transcript_span", params=params)


@mcp.tool
async def get_contributions(session_id: SessionId) -> dict[str, Any]:
    """안별 최초 제안자·채택 여부와 칸별 최초 제안자·채운 자리를 조회한다(정직 대조 근거)."""
    return await client.call("GET", f"{_base(session_id)}/contributions")


@mcp.tool
async def get_session_record(session_id: SessionId) -> dict[str, Any]:
    """평가 입력 묶음(SessionRecord)을 조립한다. 세션이 completed 이후일 때만 된다.

    세션 정보·자리(페르소나 유형 포함)·토론방 대화 전체(의도 분류·발언 경위 포함)·칸 기록·기획안
    제출본·카드 발동 기록(관찰 창 위치 포함)·사실 지표·기여 기록을 돌려준다. completed 전이면
    conflict.
    """
    base = _base(session_id)
    session = await client.call("GET", base)
    if not session["ok"]:
        return session
    s = session["data"]
    if s.get("status") not in AFTER_COMPLETED or not s.get("completed_at"):
        return client.fail("conflict", "session_not_completed")

    messages = await _all_messages(base)
    if not messages["ok"]:
        return messages
    names = ("slots", "proposal", "observations", "facts", "contributions", "rubric")
    results = await asyncio.gather(*(client.call("GET", f"{base}/{n}") for n in names))
    for result in results:
        if not result["ok"]:
            return result
    got = dict(zip(names, (r["data"] for r in results), strict=True))
    return client.ok(_assemble(s, messages["data"], got))


async def _all_messages(base: str) -> dict[str, Any]:
    """내부 GET /messages를 페이지 반복으로 끝까지 읽는다."""
    collected: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = await client.call(
            "GET", f"{base}/messages", params={"limit": MESSAGE_PAGE, "offset": offset}
        )
        if not page["ok"]:
            return page
        collected.extend(page["data"])
        if len(page["data"]) < MESSAGE_PAGE:
            return client.ok(collected)
        offset += MESSAGE_PAGE


# ───────────── SessionRecord 조립 ─────────────


def _minutes_between(start: str, end: str) -> float:
    def parse(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    return round((parse(end) - parse(start)).total_seconds() / 60, 2)


def _message(m: dict[str, Any]) -> dict[str, Any]:
    intent = m.get("intent")
    return {
        "id": m["id"],
        "sender": m["sender"],
        "content": m["content"],
        "phase": m["phase"],
        "t_min": m["t_min"],
        "origin": m.get("origin"),
        "is_invite": m.get("is_invite", False),
        "card_ids": m.get("card_ids", []),
        "intent": None
        if intent is None
        else {
            "intent": intent["intent"],
            "target_option_id": intent.get("target_option_id"),
            "addressed_to": intent.get("addressed_to", []),
        },
    }


def _seat(seat: dict[str, Any]) -> dict[str, Any]:
    if seat["seat"] == "candidate":
        return {"seat": "candidate", "display_name": seat["display_name"]}
    return {k: seat[k] for k in ("seat", "display_name", "persona_type") if k in seat}


def stage_bounds(slots: list[dict[str, Any]], end_min: float) -> dict[str, tuple[float, float]]:
    """단계별 (시작, 끝) 세션 분. 토론 단계의 끝은 그 칸 확정 시각, 다음 단계 시작도 같다.
    기획안 단계 끝은 제출 시각(end_min)."""
    confirmed = {s["phase"]: s.get("t_min") for s in slots}
    bounds: dict[str, tuple[float, float]] = {}
    start = 0.0
    for phase in PHASES:
        end = confirmed.get(phase) if phase in SLOT_PHASES else None
        end = end_min if end is None else end
        bounds[phase] = (start, end)
        start = end
    return bounds


def card_window(
    rule: dict[str, Any] | None,
    phase: str,
    fired_t_min: float,
    bounds: dict[str, tuple[float, float]],
) -> dict[str, float]:
    """카드 관찰 창(scenario-model.md 4.2). 핵심 장면 위치 표시용이며 입력 경계가 아니다.

    rule은 cards.yaml window 그대로: start = stage_start∣card_message,
    end = "stage_end:<phase>"∣submit.
    """
    rule = rule or {}
    start = bounds[phase][0] if rule.get("start") == "stage_start" else fired_t_min
    end_rule = str(rule.get("end") or f"stage_end:{phase}")
    end_phase = "proposal" if end_rule == "submit" else end_rule.removeprefix("stage_end:")
    return {"start_min": start, "end_min": bounds[end_phase][1]}


def _assemble(s: dict[str, Any], messages: list[dict[str, Any]], got: dict[str, Any]):
    proposal = got["proposal"]
    position = s.get("position", {})
    scenario = position.get("scenario") or {}
    rubric = got["rubric"]
    elements = scenario.get("elements") or [e["element"] for e in rubric.get("elements", [])]
    submit_at = proposal.get("submitted_at") or s["completed_at"]
    bounds = stage_bounds(got["slots"], _minutes_between(s["started_at"], submit_at))
    rules = {c["card_id"]: c.get("window") for c in rubric.get("cards", [])}
    observations = [
        {
            "card_id": o["card_id"],
            "element": o["element"],
            "phase": o["phase"],
            "t_min": o["t_min"],
            "trigger_message_id": o.get("trigger_message_id"),
            "delivered": o.get("delivered", False),
            "window": card_window(rules.get(o["card_id"]), o["phase"], o["t_min"], bounds),
        }
        for o in got["observations"]
    ]
    return {
        "session": {
            "id": s["id"],
            "elements": elements,
            "session_minutes": position.get("session_minutes"),
            "started_at": s["started_at"],
            "completed_at": s["completed_at"],
            "connection_gaps": s.get("connection_gaps", []),
        },
        "seats": [_seat(seat) for seat in s.get("seats", [])],
        "messages": [_message(m) for m in messages],
        "slots": [
            {k: v for k, v in slot.items() if k not in ("status", "confirmed_at")}
            for slot in got["slots"]
        ],
        "proposal": {
            "sections": proposal["sections"],
            "submitted_at": submit_at,
            "auto_submitted": proposal.get("auto_submitted", False),
        },
        "observations": observations,
        "facts": got["facts"],
        "contributions": got["contributions"],
    }
