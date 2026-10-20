"""완료 기준: 도구 목록·설명, 검색 응답, 미공개 문서 차단, 재색인(미션 폴더 해시 키), 오류
매핑·재시도.
"""

import shutil

import httpx
from rag_mcp import documents

from tests.conftest import SCENARIOS, call, make_settings

TOOLS = {"search_documents", "get_document", "list_documents", "reindex_documents"}
VERSION = documents.catalog_version(SCENARIOS)


def content(doc_id: str, scenarios=SCENARIOS) -> str:
    return next(d.content for d in documents.load_documents(scenarios) if d.doc_id == doc_id)


def session_documents(released: set[str], version: str = VERSION, scenarios=SCENARIOS):
    """내부 GET /internal/sessions/{id}/documents 응답."""
    docs = [
        {"doc_id": d.doc_id, "title": d.title, "released": d.doc_id in released}
        for d in documents.load_documents(scenarios)
    ]
    return lambda r: httpx.Response(200, json={"catalog_version": version, "documents": docs})


async def test_tools_listed_with_descriptions(mcp_client):
    tools = await mcp_client.list_tools()
    assert {t.name for t in tools} == TOOLS
    for t in tools:
        assert t.description and len(t.description) > 10
        for name, prop in t.input_schema["properties"].items():
            assert prop.get("description"), (t.name, name)


async def test_search_returns_matching_chunk_first(mcp_client, api, db):
    indexed = await call(mcp_client, "reindex_documents", {})
    assert indexed["ok"] is True
    target = documents.chunk(content("metrics"))[0]

    api.handler = session_documents({"metrics", "policy", "company_intro"})
    out = await call(mcp_client, "search_documents", {"query": target, "session_id": "s1"})

    assert out["ok"] is True
    top = out["data"][0]
    assert (top["doc_id"], top["title"], top["chunk"]) == (
        "metrics",
        "지표 현황 (최근 3개월)",
        target,
    )
    assert top["score"] > 0.99
    assert len(out["data"]) == 3
    assert api.requests[0].url.path == "/internal/sessions/s1/documents"
    assert api.requests[0].headers["x-internal-token"] == "test-token"


async def test_unreleased_documents_blocked(mcp_client, api, db):
    await call(mcp_client, "reindex_documents", {})
    hidden = documents.chunk(content("interview_summary"))[0]
    api.handler = session_documents({"metrics"})

    found = await call(mcp_client, "search_documents", {"query": hidden, "session_id": "s1"})
    assert [r["doc_id"] for r in found["data"]] == ["metrics"]

    blocked = await call(
        mcp_client, "get_document", {"doc_id": "interview_summary", "session_id": "s1"}
    )
    assert blocked["ok"] is False
    assert blocked["error"]["code"] == "not_released"

    opened = await call(mcp_client, "get_document", {"doc_id": "metrics", "session_id": "s1"})
    assert opened["data"]["content"] == content("metrics").strip()

    listed = await call(mcp_client, "list_documents", {"session_id": "s1"})
    assert {d["doc_id"]: d["released"] for d in listed["data"]}["interview_summary"] is False


async def test_search_without_index_for_version_is_upstream_unavailable(mcp_client, api, db):
    await call(mcp_client, "reindex_documents", {})
    api.handler = session_documents({"metrics"}, version="not-indexed")
    out = await call(mcp_client, "search_documents", {"query": "지표", "session_id": "s1"})
    assert out["ok"] is False
    assert out["error"]["code"] == "upstream_unavailable"
    assert out["error"]["retryable"] is True


async def test_reindex_idempotent_and_keeps_previous_version(
    mcp_client, api, db, database_url, tmp_path
):
    scenarios = tmp_path / "scenarios"
    shutil.copytree(SCENARIOS, scenarios, ignore=shutil.ignore_patterns("e2e", "__pycache__"))
    api.configure(make_settings(database_url, scenarios))

    first = await call(mcp_client, "reindex_documents", {})
    again = await call(mcp_client, "reindex_documents", {})
    assert first == again
    assert first["data"]["dim"] == 1024 and first["data"]["model"] == "fake-1024"
    old = first["data"]["catalog_version"]
    count = "SELECT count(*) FROM doc_chunks WHERE catalog_version = $1"
    assert await db.fetchval(count, old) == first["data"]["indexed"]

    v1_metrics = content("metrics", scenarios).strip()
    doc = scenarios / "missions" / "planning" / "documents" / "metrics.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\n| 신규 지표 | 1 |\n", encoding="utf-8")
    second = await call(mcp_client, "reindex_documents", {})

    new = second["data"]["catalog_version"]
    assert new != old
    assert await db.fetchval(count, old) == first["data"]["indexed"]
    assert await db.fetchval(count, new) == second["data"]["indexed"]

    # 파일이 바뀌어도 V1에 고정된 세션은 V1 본문을 받는다
    api.handler = session_documents({"metrics"}, version=old, scenarios=scenarios)
    pinned = await call(mcp_client, "get_document", {"doc_id": "metrics", "session_id": "s1"})
    assert pinned["data"]["content"] == v1_metrics


async def test_error_codes_mapped(mcp_client, api):
    cases = {401: "forbidden", 403: "forbidden", 404: "not_found", 410: "conflict"}
    for status, code in cases.items():
        api.handler = lambda r, s=status: httpx.Response(
            s, json={"error": {"code": "x", "message": "m"}}
        )
        out = await call(mcp_client, "list_documents", {"session_id": "s1"})
        assert out["ok"] is False
        assert out["error"]["code"] == code
        assert out["error"]["retryable"] is False
    assert len(api.requests) == len(cases)  # 4xx는 재시도하지 않는다


async def test_invalid_input_returned_as_error_result(mcp_client, api):
    out = await call(
        mcp_client, "search_documents", {"query": "지표", "session_id": "s1", "top_k": 0}
    )
    assert out["ok"] is False and out["error"]["code"] == "invalid_input"
    assert api.requests == []


async def test_connection_failure_retried_once_then_upstream_unavailable(mcp_client, api):
    def refuse(request):
        raise httpx.ConnectError("down")

    api.handler = refuse
    out = await call(mcp_client, "search_documents", {"query": "지표", "session_id": "s1"})
    assert out["error"]["code"] == "upstream_unavailable"
    assert out["error"]["retryable"] is True
    assert len(api.requests) == 2


async def test_5xx_retry_recovers(mcp_client, api):
    listed = session_documents({"metrics"})
    responses = iter([httpx.Response(503), listed(None)])
    api.handler = lambda r: next(responses)
    out = await call(mcp_client, "list_documents", {"session_id": "s1"})
    assert out["ok"] is True
    assert len(api.requests) == 2
