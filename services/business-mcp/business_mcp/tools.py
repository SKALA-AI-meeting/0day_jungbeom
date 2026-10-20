"""business-mcp 도구 10개. 모두 api 내부 REST로 전달만 하고 판단은 api가 한다.

반환은 `{ok, data}` 또는 `{ok:false, error:{code, message, retryable}}`.
멱등 키(run_id·seq, element·window_start)는 가공 없이 그대로 보낸다.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from business_mcp import client
from business_mcp.server import mcp

SessionId = Annotated[str, Field(description="세션 ID. 그래프가 주입하며 모델이 바꾸지 않는다.")]
RunId = Annotated[
    str, Field(description="이 실행의 run ID. 같은 키로 다시 호출해도 중복 생성되지 않는다.")
]


class Evidence(BaseModel):
    type: Literal["message", "revision", "doc_view", "assistant_call"] = Field(
        description="근거 종류"
    )
    id: str = Field(description="이 세션에 속한 해당 종류 행의 ID")


def _base(session_id: str) -> str:
    return f"/internal/sessions/{session_id}"


@mcp.tool
async def get_session(session_id: SessionId) -> dict[str, Any]:
    """세션 상태를 조회한다.

    상태, 시나리오 위치(elements·catalog_version), 분업, 시작·종료 시각,
    현재 시각(t_min_now), 현재 요소를 돌려준다.
    """
    return await client.call("GET", _base(session_id))


@mcp.tool
async def list_messages(
    session_id: SessionId,
    since_t_min: Annotated[
        float | None, Field(description="이 시각(분) 이후 메시지만. 생략하면 처음부터")
    ] = None,
    channel: Annotated[
        str | None, Field(description="채널 필터: team, dm, notice 등. 생략하면 전체")
    ] = None,
    limit: Annotated[int, Field(ge=1, le=50, description="최대 개수(기본·상한 50)")] = 50,
) -> dict[str, Any]:
    """세션의 메시지 목록을 시간순으로 조회한다. 시각·채널로 거를 수 있다."""
    params = {"since_t_min": since_t_min, "channel": channel, "limit": limit}
    return await client.call("GET", f"{_base(session_id)}/messages", params=params)


@mcp.tool
async def get_board(session_id: SessionId) -> dict[str, Any]:
    """업무 보드(파트별 담당자와 todo·doing·done 상태)를 조회한다."""
    return await client.call("GET", f"{_base(session_id)}/board")


@mcp.tool
async def get_document_state(session_id: SessionId) -> dict[str, Any]:
    """기획안 문서의 파트별 현재 내용(content, revision, updated_by)을 조회한다."""
    return await client.call("GET", f"{_base(session_id)}/document")


@mcp.tool
async def post_message(
    session_id: SessionId,
    channel: Annotated[str, Field(description="메시지 채널: team 또는 dm")],
    sender: Annotated[Literal["colleague", "manager", "system"], Field(description="보내는 사람")],
    content: Annotated[str, Field(min_length=1, description="메시지 본문")],
    run_id: RunId,
    seq: Annotated[
        int, Field(ge=0, description="run 안의 순번. (run_id, seq)가 같으면 기존 메시지를 돌려준다")
    ],
    event_id: Annotated[str | None, Field(description="이벤트 카드 실행 결과일 때 카드 ID")] = None,
    meta: Annotated[
        dict[str, Any] | None, Field(description="토큰·지연·모델 등 응답 메타. 그대로 저장된다")
    ] = None,
) -> dict[str, Any]:
    """세션에 동료·팀장·시스템 메시지를 저장하고 지원자 화면에 전달한다.

    같은 run_id와 seq로 다시 부르면 새로 만들지 않고 기존 메시지를 돌려준다.
    """
    body = {"channel": channel, "sender": sender, "content": content, "run_id": run_id, "seq": seq}
    if event_id is not None:
        body["event_id"] = event_id
    if meta is not None:
        body["meta"] = meta
    return await client.call("POST", f"{_base(session_id)}/messages", json=body)


@mcp.tool
async def set_division(
    session_id: SessionId,
    parts: Annotated[dict[str, Any], Field(description="파트 번호별 담당자 분업안")],
    decided_by: Annotated[
        Literal["candidate", "colleague_default"], Field(description="분업을 정한 쪽")
    ],
) -> dict[str, Any]:
    """파트 분업을 확정한다. 세션이 진행 중이 아니거나 최소 조건을 어기면 api가 거부한다."""
    return await client.call(
        "PUT", f"{_base(session_id)}/division", json={"parts": parts, "decided_by": decided_by}
    )


@mcp.tool
async def update_task(
    session_id: SessionId,
    part_no: Annotated[int, Field(ge=1, le=5, description="파트 번호(1~5)")],
    status: Annotated[Literal["todo", "doing", "done"], Field(description="새 상태")],
) -> dict[str, Any]:
    """동료가 맡은 파트의 보드 상태를 바꾼다. 동료 담당이 아니면 api가 forbidden으로 거부한다."""
    return await client.call("PUT", f"{_base(session_id)}/tasks/{part_no}", json={"status": status})


@mcp.tool
async def write_document_part(
    session_id: SessionId,
    part_no: Annotated[int, Field(ge=1, le=5, description="파트 번호(1~5)")],
    content: Annotated[str, Field(description="파트 본문 전체")],
    run_id: RunId,
) -> dict[str, Any]:
    """동료가 맡은 기획안 파트를 쓴다.

    같은 part_no와 run_id로 다시 부르면 기존 revision을 돌려준다. 동료 담당이 아니면 forbidden.
    """
    body = {"content": content, "by": "colleague", "run_id": run_id}
    return await client.call("PUT", f"{_base(session_id)}/document/{part_no}", json=body)


@mcp.tool
async def release_document(
    session_id: SessionId,
    doc_id: Annotated[str, Field(min_length=1, description="공개할 문서 ID")],
) -> dict[str, Any]:
    """고정 문서를 지원자에게 공개한다. 이미 공개된 문서면 기존 공개 시각을 돌려준다."""
    return await client.call("POST", f"{_base(session_id)}/releases/{doc_id}")


@mcp.tool
async def record_observation(
    session_id: SessionId,
    element: Annotated[str, Field(min_length=1, description="관찰 대상 요소 이름")],
    window_start: Annotated[
        float, Field(description="관찰 창 시작(분). (element, window_start)가 같으면 기존 행")
    ],
    window_end: Annotated[float, Field(description="관찰 창 끝(분)")],
    metrics: Annotated[dict[str, Any], Field(description="규칙으로 센 지표")],
    label: Annotated[str | None, Field(description="분류 레이블. 관찰 없음이면 null")],
    evidence: Annotated[
        list[Evidence], Field(description="근거 목록. 각 id는 이 세션의 해당 행이어야 한다")
    ],
    run_id: RunId,
) -> dict[str, Any]:
    """요소 관찰 창의 지표·레이블·근거를 기록한다.

    같은 element와 window_start로 다시 부르면 기존 행의 id를 돌려준다.
    근거 id가 이 세션의 행이 아니면 invalid_input.
    """
    body = {
        "element": element,
        "window_start": window_start,
        "window_end": window_end,
        "metrics": metrics,
        "label": label,
        "evidence": [e.model_dump() for e in evidence],
        "run_id": run_id,
    }
    return await client.call("POST", f"{_base(session_id)}/observations", json=body)
