"""완료 기준: 도구 6개 목록·설명, 계약 픽스처대로의 경로·본문·출력 형태, 토큰 검사, 오류 매핑,
멱등 키 전달, get_session_record 조립(completed 전 conflict, 메시지 페이지 반복, 관찰 창),
get_transcript_span 기본 앞 5·뒤 3.
"""

import copy
import inspect
import json

import httpx
from assessment_mcp import tools

from tests.conftest import call, fixture, shape

CASES = fixture("mcp_tools")["assessment"]
SPECS = shape.MCP_TOOLS["assessment"]
BASE = "/internal/sessions/sess-1"

# 단순 전달 도구 → (메서드, 내부 경로 접미사, 내부 응답 픽스처)
ROUTES = {
    "record_observation": ("POST", "/observations", "internal_observation_created"),
    "get_rubric": ("GET", "/rubric", "internal_rubric"),
    "get_transcript_span": ("GET", "/transcript_span", "internal_transcript_span"),
    "get_contributions": ("GET", "/contributions", "internal_contributions"),
    "save_evaluation": ("POST", "/evaluations", "internal_evaluations_saved"),
}


def input_of(name: str):
    value = CASES[name]["input"]
    return fixture(value.removesuffix(".json")) if isinstance(value, str) else value


def completed_session():
    s = fixture("internal_session")
    s.update(
        status="completed",
        phase="completed",
        completed_at="2026-10-21T01:57:00Z",
        connection_gaps=fixture("session_record")["session"]["connection_gaps"],
    )
    return s


def record_routes(session=None, messages=None):
    """get_session_record가 읽는 내부 GET 경로들. 최종 세션 기록 픽스처에 맞춘 값."""
    record = fixture("session_record")
    proposal = fixture("internal_proposal")
    return {
        ("GET", BASE): session or completed_session(),
        ("GET", BASE + "/messages"): messages
        if messages is not None
        else fixture("internal_messages"),
        ("GET", BASE + "/slots"): fixture("internal_slots"),
        ("GET", BASE + "/proposal"): {
            **proposal,
            "submitted_at": record["proposal"]["submitted_at"],
        },
        ("GET", BASE + "/observations"): fixture("internal_observations"),
        ("GET", BASE + "/facts"): fixture("internal_facts"),
        ("GET", BASE + "/contributions"): fixture("internal_contributions"),
        ("GET", BASE + "/rubric"): fixture("internal_rubric"),
    }


def fake_api(routes):
    def handler(request: httpx.Request) -> httpx.Response:
        body = routes.get((request.method, request.url.path))
        if callable(body):
            body = body(request)
        if body is None:
            return httpx.Response(404, json={"error": {"code": "not_found", "message": "x"}})
        return httpx.Response(200, json=body)

    return handler


async def test_six_tools_listed_with_descriptions(mcp_client):
    listed = await mcp_client.list_tools()
    assert {t.name for t in listed} == set(SPECS) == set(CASES)
    for t in listed:
        assert t.description and len(t.description) > 10
        for name, prop in t.input_schema["properties"].items():
            assert prop.get("description") or name == "session_id", (t.name, name)


def test_all_tools_async():
    for name in SPECS:
        assert inspect.iscoroutinefunction(getattr(tools, name)), name


async def test_tools_follow_contract(mcp_client, api):
    for name, (method, suffix, internal) in ROUTES.items():
        api.handler = fake_api({(method, BASE + suffix): fixture(internal)})
        args = input_of(name)
        out = await call(mcp_client, name, args)
        assert out["ok"] is True, (name, out)
        shape.validate(out["data"], SPECS[name][1], f"assessment.{name}")
        request = api.requests[-1]
        assert (request.method, request.url.path) == (method, BASE + suffix)
        assert request.headers["x-internal-token"] == "test-token"
        if method == "POST":
            sent = json.loads(request.content)
            assert sent == {k: v for k, v in args.items() if k != "session_id"}, name


async def test_missing_or_wrong_token_is_forbidden_without_api_call(mcp_client, api, presented):
    api.handler = fake_api({("GET", BASE + "/rubric"): fixture("internal_rubric")})
    for token in (None, "", "wrong-token"):
        presented["token"] = token
        for name in SPECS:
            out = await call(mcp_client, name, input_of(name))
            assert out == {
                "ok": False,
                "error": {
                    "code": "forbidden",
                    "message": "missing or invalid X-Assessment-Token",
                    "retryable": False,
                },
            }, (token, name)
    assert api.requests == []


async def test_empty_server_token_rejects_everything(mcp_client, api, presented):
    from assessment_mcp import client
    from assessment_mcp.config import Settings

    client.configure(
        transport=client._transport,
        settings=Settings(
            api_internal_url="http://api.test", internal_token="t", assessment_token=""
        ),
    )
    presented["token"] = ""
    out = await call(mcp_client, "get_rubric", {"session_id": "sess-1"})
    assert out["error"]["code"] == "forbidden"
    assert api.requests == []


async def test_save_evaluation_idempotent_pass_through(mcp_client, api):
    """같은 (session_id, run_id) 재호출은 api가 existing=true로 돌려주고 MCP는 그대로 전달한다."""
    saved = iter(
        [
            {"run_id": "run-eval-sess-1-r1", "existing": False, "saved": 19},
            {"run_id": "run-eval-sess-1-r1", "existing": True, "saved": 0},
        ]
    )
    api.handler = lambda r: httpx.Response(200, json=next(saved))
    args = input_of("save_evaluation")
    first = await call(mcp_client, "save_evaluation", args)
    second = await call(mcp_client, "save_evaluation", args)
    assert (first["data"]["existing"], second["data"]["existing"]) == (False, True)
    bodies = [json.loads(r.content) for r in api.requests]
    assert bodies[0] == bodies[1]
    assert bodies[0]["run_id"] == args["run_id"]
    assert set(bodies[0]["prompt_versions"]) == {
        "common",
        "persuasion",
        "listening",
        "inclusion",
        "flexibility",
        "honesty",
    }
    # 기록 없음이 아닌 차원에는 no_record_reason 키를 만들지 않는다
    assert bodies[0]["dimensions"] == args["dimensions"]


async def test_save_evaluation_api_validation_error_is_invalid_input(mcp_client, api):
    api.handler = lambda r: httpx.Response(
        422, json={"error": {"code": "invalid_input", "message": "unknown dimension_id"}}
    )
    out = await call(mcp_client, "save_evaluation", input_of("save_evaluation"))
    assert out["error"]["code"] == "invalid_input"
    assert len(api.requests) == 1


async def test_save_evaluation_bad_shape_rejected_before_api(mcp_client, api):
    args = copy.deepcopy(input_of("save_evaluation"))
    args["dimensions"][0]["level"] = 9
    out = await call(mcp_client, "save_evaluation", args)
    assert out["error"]["code"] == "invalid_input"
    assert api.requests == []


async def test_record_observation_idempotency_pass_through(mcp_client, api):
    api.handler = lambda r: httpx.Response(200, json=fixture("internal_observation_created"))
    args = input_of("record_observation")
    first = await call(mcp_client, "record_observation", args)
    second = await call(mcp_client, "record_observation", args)
    assert first == second
    assert json.loads(api.requests[0].content) == json.loads(api.requests[1].content)


async def test_transcript_span_defaults_before_5_after_3(mcp_client, api):
    api.handler = lambda r: httpx.Response(200, json=fixture("internal_transcript_span"))
    await call(mcp_client, "get_transcript_span", {"session_id": "sess-1", "message_id": "m-15"})
    params = api.requests[-1].url.params
    assert (params["message_id"], params["before"], params["after"]) == ("m-15", "5", "3")


async def test_session_record_assembled_in_contract_shape(mcp_client, api):
    api.handler = fake_api(record_routes())
    out = await call(mcp_client, "get_session_record", {"session_id": "sess-1"})
    assert out["ok"] is True, out
    data = out["data"]
    shape.validate(data, SPECS["get_session_record"][1], "assessment.get_session_record")
    record = fixture("session_record")
    for key in ("session", "seats", "slots", "proposal", "observations", "facts", "contributions"):
        assert data[key] == record[key], key
    # 메시지는 내부 응답 그대로(시간순)이고 created_at·meta는 빠진다
    assert [m["id"] for m in data["messages"]] == [m["id"] for m in fixture("internal_messages")]
    assert "meta" not in data["messages"][0] and "created_at" not in data["messages"][0]


async def test_session_record_pages_messages_until_short_page(mcp_client, api):
    def page(request):
        offset = int(request.url.params["offset"])
        assert request.url.params["limit"] == "1000"
        base = fixture("internal_messages")[0]
        count = 1000 if offset == 0 else 2
        return [{**base, "id": f"m-{offset + i}"} for i in range(count)]

    routes = record_routes()
    routes[("GET", BASE + "/messages")] = page
    api.handler = fake_api(routes)
    out = await call(mcp_client, "get_session_record", {"session_id": "sess-1"})
    assert len(out["data"]["messages"]) == 1002
    offsets = [r.url.params["offset"] for r in api.requests if r.url.path.endswith("/messages")]
    assert offsets == ["0", "1000"]


async def test_session_record_before_completed_is_conflict(mcp_client, api):
    api.handler = fake_api(record_routes(session=fixture("internal_session")))  # in_progress
    out = await call(mcp_client, "get_session_record", {"session_id": "sess-1"})
    assert out["ok"] is False and out["error"]["code"] == "conflict"
    assert len(api.requests) == 1


async def test_session_record_upstream_error_propagates(mcp_client, api):
    routes = record_routes()
    del routes[("GET", BASE + "/facts")]
    api.handler = fake_api(routes)
    out = await call(mcp_client, "get_session_record", {"session_id": "sess-1"})
    assert out["error"]["code"] == "not_found"


async def test_error_mapping_and_retry(mcp_client, api):
    api.handler = lambda r: httpx.Response(
        409, json={"error": {"code": "conflict", "message": "m"}}
    )
    out = await call(mcp_client, "record_observation", input_of("record_observation"))
    assert out["error"] == {"code": "conflict", "message": "conflict", "retryable": False}
    shape.assert_contract(out, "mcp_error")

    api.requests.clear()
    api.handler = lambda r: httpx.Response(500)
    out = await call(mcp_client, "get_rubric", {"session_id": "sess-1"})
    assert out["error"]["code"] == "upstream_unavailable" and out["error"]["retryable"] is True
    assert len(api.requests) == 2
