"""business-mcp 도구 11개(조회 4, 변경 7). 모두 api 내부 REST로 전달만 하고 판단은 api가 한다.

반환은 `{ok, data}` 또는 `{ok:false, error:{code, message, retryable}}`. 목록·입출력 정본은
docs/common/contracts.md "MCP 도구". 멱등 키(run_id·seq, doc_id·run_id, card_id·window_start)는 가공
없이 그대로 보낸다.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from business_mcp import client
from business_mcp.server import mcp

SessionId = Annotated[str, Field(description="세션 ID. 그래프가 주입하며 모델이 바꾸지 않는다.")]
RunId = Annotated[
    str, Field(description="이 실행의 run ID. 같은 키로 다시 호출해도 중복 생성되지 않는다.")
]
PartNo = Annotated[int, Field(ge=1, le=5, description="파트 번호(1~5)")]
Assignee = Literal["candidate", "colleague", "both"]


class Evidence(BaseModel):
    type: Literal[
        "message", "document", "share", "open", "task_event", "doc_view", "assistant_call"
    ] = Field(description="근거 종류(rubric.md 근거 타입 7개)")
    id: str = Field(description="이 세션에 속한 해당 종류 행의 ID")


def _base(session_id: str) -> str:
    return f"/internal/sessions/{session_id}"


def _drop_none(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if v is not None}


# ───────────── 조회 ─────────────


@mcp.tool
async def get_session(session_id: SessionId) -> dict[str, Any]:
    """세션 상태를 조회한다.

    상태, 채용 건 시나리오(mission_id·elements·catalog_version), 분업, 시작·제출·보고·종료 시각,
    현재 시각(t_min_now), 열린 관찰 창의 카드(current_card), 이벤트 목록을 돌려준다.
    """
    return await client.call("GET", _base(session_id))


@mcp.tool
async def list_messages(
    session_id: SessionId,
    since_t_min: Annotated[
        float | None, Field(description="이 시각(분) 이후 메시지만. 생략하면 처음부터")
    ] = None,
    channel: Annotated[
        str | None,
        Field(description="채널 필터: team, dm, manager_dm, notice 등. 생략하면 전체"),
    ] = None,
    limit: Annotated[int, Field(ge=1, le=50, description="최대 개수(기본·상한 50)")] = 50,
) -> dict[str, Any]:
    """세션의 메시지 목록을 시간순으로 조회한다. 시각·채널로 거를 수 있다."""
    params = {"since_t_min": since_t_min, "channel": channel, "limit": limit}
    return await client.call("GET", f"{_base(session_id)}/messages", params=params)


@mcp.tool
async def get_board(session_id: SessionId) -> dict[str, Any]:
    """태스크 보드(파트별 담당·상태·순서·언제까지·의존)를 조회한다. 미배정 담당은 null이다."""
    return await client.call("GET", f"{_base(session_id)}/board")


@mcp.tool
async def get_shared_documents(session_id: SessionId) -> dict[str, Any]:
    """주고받은 파트 문서를 조회한다.

    지원자 문서는 지원자가 보낸 버전만, 동료 문서는 보낸 버전 전부를 돌려준다. 지원자가 보내지 않은
    문서·버전은 결과에 없다.
    """
    return await client.call("GET", f"{_base(session_id)}/docs/shared")


# ───────────── 변경 ─────────────


@mcp.tool
async def post_message(
    session_id: SessionId,
    channel: Annotated[
        Literal["team", "dm", "manager_dm", "notice"],
        Field(description="메시지 채널: team, dm(동료), manager_dm(팀장), notice(지원자에게만)"),
    ],
    sender: Annotated[Literal["colleague", "manager", "system"], Field(description="보내는 사람")],
    content: Annotated[str, Field(min_length=1, description="메시지 본문")],
    run_id: RunId,
    seq: Annotated[
        int,
        Field(ge=0, description="노드별 고정 슬롯. (run_id, seq)가 같으면 기존 메시지를 돌려준다"),
    ],
    event_id: Annotated[str | None, Field(description="카드 실행 결과일 때 그 이벤트 ID")] = None,
    meta: Annotated[
        dict[str, Any] | None, Field(description="토큰·지연·모델 등 응답 메타. 그대로 저장된다")
    ] = None,
) -> dict[str, Any]:
    """세션에 동료·팀장·시스템 메시지를 저장하고 지원자 화면에 전달한다.

    같은 run_id와 seq로 다시 부르면 새로 만들지 않고 기존 메시지를 돌려준다.
    """
    body = {"channel": channel, "sender": sender, "content": content, "run_id": run_id, "seq": seq}
    body.update(_drop_none({"event_id": event_id, "meta": meta}))
    return await client.call("POST", f"{_base(session_id)}/messages", json=body)


@mcp.tool
async def set_division(
    session_id: SessionId,
    parts: Annotated[
        dict[str, Assignee],
        Field(description='파트 번호별 담당. 예: {"1": "candidate", "3": "both"}'),
    ],
    decided_by: Annotated[
        Literal["candidate", "colleague_default"],
        Field(description="candidate(주담당이 채팅으로 정함) 또는 colleague_default(기본안)"),
    ],
    run_id: RunId,
) -> dict[str, Any]:
    """분업을 확정하고 보드 담당을 채운다.

    전 파트를 지정해야 하고 최소 조건(2번 주담당, 3번 동료 또는 같이, 4·5 중 하나는 동료 혼자)을
    어기면 api가 invalid_input으로 거부한다. 같은 내용의 재호출은 저장된 값을 돌려준다.
    """
    body = {"parts": parts, "decided_by": decided_by, "run_id": run_id}
    return await client.call("PUT", f"{_base(session_id)}/division", json=body)


@mcp.tool
async def update_task(
    session_id: SessionId,
    part_no: PartNo,
    status: Annotated[Literal["todo", "doing", "done"], Field(description="새 상태")],
    run_id: RunId,
) -> dict[str, Any]:
    """동료가 맡은 파트의 보드 상태만 바꾼다(담당·순서·언제까지는 못 바꿈).

    동료 담당(혼자·같이)이 아니면 api가 forbidden으로 거부한다. (part_no, run_id)로 멱등이다.
    """
    body = {"status": status, "run_id": run_id}
    return await client.call("PUT", f"{_base(session_id)}/tasks/{part_no}", json=body)


@mcp.tool
async def send_document(
    session_id: SessionId,
    content: Annotated[str, Field(min_length=1, description="보낼 문서 본문 전체")],
    channel: Annotated[Literal["team", "dm"], Field(description="문서 카드를 올릴 채널")],
    run_id: RunId,
    seq: Annotated[int, Field(ge=0, description="문서 카드 메시지 슬롯. 파트 번호×10")],
    doc_id: Annotated[str | None, Field(description="이미 있는 동료 문서 ID")] = None,
    part_no: Annotated[
        int | None, Field(ge=1, le=5, description="동료 문서가 아직 없으면 파트 번호(1~5)")
    ] = None,
    event_id: Annotated[str | None, Field(description="카드 실행 결과일 때 그 이벤트 ID")] = None,
) -> dict[str, Any]:
    """동료 문서를 쓰고 새 버전으로 보낸다(문서 카드 메시지 1건).

    doc_id 또는 part_no 하나를 준다. 같은 문서·run_id로 다시 부르면 버전을 늘리지 않고 기존 버전과
    메시지를 돌려준다. 동료 담당이 아닌 파트·동료 문서가 아닌 doc_id는 forbidden.
    """
    if (doc_id is None) == (part_no is None):
        return client.fail("invalid_input", "exactly one of doc_id or part_no")
    body = {"content": content, "channel": channel, "run_id": run_id, "seq": seq}
    body.update(_drop_none({"doc_id": doc_id, "part_no": part_no, "event_id": event_id}))
    return await client.call("POST", f"{_base(session_id)}/docs/send", json=body)


@mcp.tool
async def release_document(
    session_id: SessionId,
    doc_id: Annotated[str, Field(min_length=1, description="공개할 회사 문서 ID")],
) -> dict[str, Any]:
    """회사 문서를 지원자에게 공개한다. 이미 공개된 문서면 기존 공개 시각을 돌려준다."""
    return await client.call("POST", f"{_base(session_id)}/releases/{doc_id}")


@mcp.tool
async def record_observation(
    session_id: SessionId,
    card_id: Annotated[str, Field(min_length=1, description="관찰 창을 연 카드 ID")],
    element: Annotated[str, Field(min_length=1, description="카드의 요소 ID")],
    window_start: Annotated[
        float, Field(description="관찰 창 시작(세션 분). (card_id, window_start)가 같으면 기존 행")
    ],
    window_end: Annotated[float, Field(description="관찰 창 끝(세션 분)")],
    metrics: Annotated[
        dict[str, Any], Field(description="규칙으로 센 지표 {이름: {value, evidence_ids}}")
    ],
    label: Annotated[str | None, Field(description="분류 레이블. 분류 실패면 null")],
    evidence: Annotated[
        list[Evidence], Field(description="근거 목록. 각 id는 이 세션의 해당 행이어야 한다")
    ],
    run_id: RunId,
    aux: Annotated[dict[str, Any] | None, Field(description="레이블과 함께 낸 보조 판정")] = None,
    facts: Annotated[
        dict[str, Any] | None, Field(description="정직 카드의 사실 입력(honesty_facts)")
    ] = None,
) -> dict[str, Any]:
    """카드 관찰 창의 지표·레이블·근거를 기록한다.

    같은 card_id와 window_start로 다시 부르면 기존 행의 id를 돌려준다. 근거 id가 이 세션의 행이
    아니면 invalid_input.
    """
    body = {
        "card_id": card_id,
        "element": element,
        "window_start": window_start,
        "window_end": window_end,
        "metrics": metrics,
        "label": label,
        "evidence": [e.model_dump() for e in evidence],
        "run_id": run_id,
    }
    body.update(_drop_none({"aux": aux, "facts": facts}))
    return await client.call("POST", f"{_base(session_id)}/observations", json=body)


@mcp.tool
async def update_observation(
    session_id: SessionId,
    card_id: Annotated[str, Field(min_length=1, description="갱신할 관찰의 카드 ID")],
    window_start: Annotated[float, Field(description="갱신할 관찰 창 시작(세션 분)")],
    metrics_patch: Annotated[
        dict[str, Any], Field(description="바꿀 지표만 {이름: {value, evidence_ids}}")
    ],
    run_id: RunId,
) -> dict[str, Any]:
    """기록된 관찰의 지정한 지표만 갱신한다(세션 종료 때 약속 이행 promise_kept 확정).

    같은 (card_id, window_start, run_id) 재호출은 멱등이다. 관찰 행이 없으면 not_found.
    """
    body = {
        "card_id": card_id,
        "window_start": window_start,
        "metrics_patch": metrics_patch,
        "run_id": run_id,
    }
    return await client.call("PATCH", f"{_base(session_id)}/observations", json=body)
