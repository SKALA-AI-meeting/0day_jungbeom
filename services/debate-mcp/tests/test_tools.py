"""완료 기준: 도구 목록·설명, 계약 픽스처대로의 경로·본문·출력, 오류 코드 매핑, 멱등 키 전달, 문서
제공 실패.
"""

import json
from pathlib import Path

import httpx

from tests.conftest import call

CONTRACTS = Path(__file__).parents[3] / "tests/fixtures/contracts"
FIXTURE = json.loads((CONTRACTS / "mcp_tools.json").read_text())["business"]

# 도구 → (메서드, 내부 경로 접미사). 정본은 docs/common/contracts.md "MCP 도구"
ROUTES = {
    "get_session": ("GET", ""),
    "list_messages": ("GET", "/messages"),
    "get_board": ("GET", "/board"),
    "get_shared_documents": ("GET", "/docs/shared"),
    "post_message": ("POST", "/messages"),
    "set_division": ("PUT", "/division"),
    "update_task": ("PUT", "/tasks/4"),
    "send_document": ("POST", "/docs/send"),
    "release_document": ("POST", "/releases/interview_summary"),
    "record_observation": ("POST", "/observations"),
    "update_observation": ("PATCH", "/observations"),
}
QUERY_TOOLS = {"get_session", "list_messages", "get_board", "get_shared_documents"}


def output_of(name: str):
    out = FIXTURE[name]["output"]
    return json.loads((CONTRACTS / out).read_text()) if isinstance(out, str) else out


async def test_tools_listed_with_descriptions(mcp_client):
    tools = await mcp_client.list_tools()
    assert {t.name for t in tools} == set(FIXTURE) == set(ROUTES)
    for t in tools:
        assert t.description and len(t.description) > 10
        for name, prop in t.input_schema["properties"].items():
            assert prop.get("description") or name == "session_id" or "$ref" in prop, (t.name, name)


async def test_tools_follow_contract_fixture(mcp_client, api):
    """픽스처 입력으로 부르면 계약 경로로 전달하고(세션 id·경로 인자 제외 본문 그대로), api 응답을
    감싼다.
    """
    for name, (method, suffix) in ROUTES.items():
        expected = output_of(name)
        api.handler = lambda r, body=expected: httpx.Response(200, json=body)
        args = FIXTURE[name]["input"]
        out = await call(mcp_client, name, args)
        assert out == {"ok": True, "data": expected}, name
        request = api.requests[-1]
        assert (request.method, request.url.path) == (method, f"/internal/sessions/sess-1{suffix}")
        assert request.headers["x-internal-token"] == "test-token"
        if name in QUERY_TOOLS or name == "release_document":
            continue
        sent = json.loads(request.content)
        path_args = {"session_id", "part_no"} if name == "update_task" else {"session_id"}
        assert sent == {k: v for k, v in args.items() if k not in path_args and v is not None}, name


async def test_error_codes_mapped(mcp_client, api):
    cases = {
        401: "forbidden",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "invalid_input",
    }
    args = {"session_id": "s1", "part_no": 2, "status": "doing", "run_id": "r"}
    for status, code in cases.items():
        api.handler = lambda r, s=status: httpx.Response(
            s, json={"error": {"code": "x", "message": "m"}}
        )
        out = await call(mcp_client, "update_task", args)
        assert out["ok"] is False
        assert out["error"]["code"] == code
        assert out["error"]["retryable"] is False
    assert len(api.requests) == len(cases)  # 4xx는 재시도하지 않는다


async def test_send_document_failure_is_upstream_unavailable(mcp_client, api):
    """최소 테스트 ⑤ 문서 제공 실패(MCP 쪽): api 장애면 1회 재시도 뒤 retryable 오류를 돌려준다.
    그래프는 이 결과로 카드를 실패시키고 RunResult.error=document_missing을 api에 알린다."""
    api.handler = lambda r: httpx.Response(503)
    out = await call(mcp_client, "send_document", FIXTURE["send_document"]["input"])
    assert out["ok"] is False
    assert out["error"] == {
        "code": "upstream_unavailable",
        "message": "api responded 503",
        "retryable": True,
    }
    assert len(api.requests) == 2


async def test_send_document_keys_forwarded_unchanged(mcp_client, api):
    """같은 (doc_id, run_id)·(run_id, seq) 재호출의 중복 판단은 api에 맡기고 키를 그대로 보낸다."""
    api.handler = lambda r: httpx.Response(200, json=output_of("send_document"))
    args = FIXTURE["send_document"]["input"]
    first = await call(mcp_client, "send_document", args)
    second = await call(mcp_client, "send_document", args)
    assert first == second
    bodies = [json.loads(r.content) for r in api.requests]
    assert bodies[0] == bodies[1]
    assert (bodies[0]["run_id"], bodies[0]["seq"], bodies[0]["event_id"]) == ("r-20", 40, "ev-4")


async def test_invalid_input_returned_as_error_result(mcp_client, api):
    api.handler = lambda r: httpx.Response(200, json={})
    out = await call(
        mcp_client,
        "update_task",
        {"session_id": "s1", "part_no": 9, "status": "doing", "run_id": "r"},
    )
    assert out["ok"] is False and out["error"]["code"] == "invalid_input"
    both = {**FIXTURE["send_document"]["input"], "doc_id": "doc-k4"}
    out = await call(mcp_client, "send_document", both)
    assert out["ok"] is False and out["error"]["code"] == "invalid_input"
    assert api.requests == []


async def test_connection_failure_retried_once_then_upstream_unavailable(mcp_client, api):
    def refuse(request):
        raise httpx.ConnectError("down")

    api.handler = refuse
    out = await call(mcp_client, "get_board", {"session_id": "s1"})
    assert out["error"]["code"] == "upstream_unavailable"
    assert out["error"]["retryable"] is True
    assert len(api.requests) == 2


async def test_non_json_success_body_becomes_upstream_unavailable(mcp_client, api):
    api.handler = lambda r: httpx.Response(200, content=b"<html>oops</html>")
    out = await call(mcp_client, "get_board", {"session_id": "s1"})
    assert out["ok"] is False
    assert out["error"]["code"] == "upstream_unavailable"
    assert out["error"]["retryable"] is True
