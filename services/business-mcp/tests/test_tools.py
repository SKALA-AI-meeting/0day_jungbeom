"""완료 기준: 도구 목록·설명, 오류 코드 매핑, 멱등 키 전달."""

import json
from pathlib import Path

import httpx

from tests.conftest import call

MESSAGE = json.loads(
    (Path(__file__).parents[3] / "tests/fixtures/contracts/mcp_ok.json").read_text()
)["data"]
TOOLS = {
    "get_session",
    "list_messages",
    "get_board",
    "get_document_state",
    "post_message",
    "set_division",
    "update_task",
    "write_document_part",
    "release_document",
    "record_observation",
}


async def test_tools_listed_with_descriptions(mcp_client):
    tools = await mcp_client.list_tools()
    assert {t.name for t in tools} == TOOLS
    for t in tools:
        assert t.description and len(t.description) > 10
        for name, prop in t.input_schema["properties"].items():
            assert prop.get("description") or name == "session_id" or "$ref" in prop, (t.name, name)


async def test_get_session_forwards_token_and_wraps_data(mcp_client, api):
    api.handler = lambda r: httpx.Response(200, json={"id": "s1", "status": "in_progress"})
    out = await call(mcp_client, "get_session", {"session_id": "s1"})
    assert out == {"ok": True, "data": {"id": "s1", "status": "in_progress"}}
    request = api.requests[0]
    assert request.url.path == "/internal/sessions/s1"
    assert request.headers["x-internal-token"] == "test-token"


async def test_list_messages_passes_filters(mcp_client, api):
    api.handler = lambda r: httpx.Response(200, json=[MESSAGE])
    out = await call(
        mcp_client, "list_messages", {"session_id": "s1", "since_t_min": 5, "channel": "team"}
    )
    assert out["data"] == [MESSAGE]
    assert dict(api.requests[0].url.params) == {
        "since_t_min": "5.0",
        "channel": "team",
        "limit": "50",
    }


async def test_error_codes_mapped(mcp_client, api):
    cases = {
        401: "forbidden",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "invalid_input",
    }
    for status, code in cases.items():
        api.handler = lambda r, s=status: httpx.Response(
            s, json={"error": {"code": "x", "message": "m"}}
        )
        out = await call(
            mcp_client, "update_task", {"session_id": "s1", "part_no": 2, "status": "doing"}
        )
        assert out["ok"] is False
        assert out["error"]["code"] == code
        assert out["error"]["retryable"] is False
    assert len(api.requests) == len(cases)  # 4xx는 재시도하지 않는다


async def test_connection_failure_retried_once_then_upstream_unavailable(mcp_client, api):
    def refuse(request):
        raise httpx.ConnectError("down")

    api.handler = refuse
    out = await call(mcp_client, "get_board", {"session_id": "s1"})
    assert out["error"]["code"] == "upstream_unavailable"
    assert out["error"]["retryable"] is True
    assert len(api.requests) == 2


async def test_5xx_retry_recovers(mcp_client, api):
    responses = iter([httpx.Response(503), httpx.Response(200, json={"tasks": []})])
    api.handler = lambda r: next(responses)
    out = await call(mcp_client, "get_board", {"session_id": "s1"})
    assert out == {"ok": True, "data": {"tasks": []}}
    assert len(api.requests) == 2


async def test_post_message_forwards_idempotency_keys_and_meta(mcp_client, api):
    api.handler = lambda r: httpx.Response(200, json=MESSAGE)
    args = {
        "session_id": "s1",
        "channel": "team",
        "sender": "colleague",
        "content": "안녕하세요",
        "run_id": "run-1",
        "seq": 3,
        "event_id": "kickoff",
        "meta": {"tokens": 12, "model": "gpt-4o-mini"},
    }
    first = await call(mcp_client, "post_message", args)
    second = await call(mcp_client, "post_message", args)
    assert first == second == {"ok": True, "data": MESSAGE}
    assert len(api.requests) == 2  # 중복 판단은 api에 맡기고 같은 키로 그대로 전달
    for request in api.requests:
        assert request.method == "POST"
        assert json.loads(request.content) == {
            "channel": "team",
            "sender": "colleague",
            "content": "안녕하세요",
            "run_id": "run-1",
            "seq": 3,
            "event_id": "kickoff",
            "meta": {"tokens": 12, "model": "gpt-4o-mini"},
        }


async def test_mutation_tools_hit_contract_routes(mcp_client, api):
    api.handler = lambda r: httpx.Response(200, json={"ok_body": True})
    sid = {"session_id": "s1"}
    calls = [
        (
            "set_division",
            {**sid, "parts": {"1": "colleague"}, "decided_by": "candidate"},
            "PUT",
            "division",
        ),
        (
            "write_document_part",
            {**sid, "part_no": 4, "content": "본문", "run_id": "r"},
            "PUT",
            "document/4",
        ),
        ("release_document", {**sid, "doc_id": "interview"}, "POST", "releases/interview"),
        (
            "record_observation",
            {
                **sid,
                "element": "respect",
                "window_start": 90,
                "window_end": 100,
                "metrics": {"n": 1},
                "label": None,
                "evidence": [{"type": "message", "id": "m1"}],
                "run_id": "r",
            },
            "POST",
            "observations",
        ),
    ]
    for name, args, method, suffix in calls:
        out = await call(mcp_client, name, args)
        assert out["ok"] is True, name
        request = api.requests[-1]
        assert (request.method, request.url.path) == (method, f"/internal/sessions/s1/{suffix}")
    observation = json.loads(api.requests[-1].content)
    assert observation["evidence"] == [{"type": "message", "id": "m1"}]
    assert observation["window_start"] == 90 and observation["run_id"] == "r"
    assert json.loads(api.requests[1].content) == {
        "content": "본문",
        "by": "colleague",
        "run_id": "r",
    }


async def test_invalid_input_returned_as_error_result(mcp_client, api):
    api.handler = lambda r: httpx.Response(200, json={})
    out = await call(
        mcp_client, "update_task", {"session_id": "s1", "part_no": 9, "status": "doing"}
    )
    assert out["ok"] is False and out["error"]["code"] == "invalid_input"
    assert api.requests == []


async def test_non_json_success_body_becomes_upstream_unavailable(mcp_client, api):
    api.handler = lambda r: httpx.Response(200, content=b"<html>oops</html>")
    out = await call(mcp_client, "get_board", {"session_id": "s1"})
    assert out["ok"] is False
    assert out["error"]["code"] == "upstream_unavailable"
    assert out["error"]["retryable"] is True
