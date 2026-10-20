"""rag-mcp 도구 4개. 공개 여부와 색인 버전은 api 내부 `GET /internal/sessions/{id}/documents`가
최종 판단하고, rag-mcp는 그 목록으로 거르기만 한다.

반환은 `{ok, data}` 또는 `{ok:false, error:{code, message, retryable}}`.
"""

from typing import Annotated, Any

import asyncpg
from pydantic import Field

from rag_mcp import client, documents, store
from rag_mcp.client import fail, ok
from rag_mcp.embedder import embed, get_embedder
from rag_mcp.server import mcp

SessionId = Annotated[str, Field(description="세션 ID. 그래프가 주입하며 모델이 바꾸지 않는다.")]
DocId = Annotated[str, Field(min_length=1, description="문서 ID(예: metrics, policy)")]

# DB 연결 실패·쿼리 오류. 검색·색인은 DB 없이 진행할 수 없으므로 upstream_unavailable.
DB_ERRORS = (OSError, asyncpg.PostgresError)


async def _session_documents(session_id: str) -> dict[str, Any]:
    """{ok, data: {catalog_version, documents: [{doc_id, title, released}]}}"""
    return await client.call("GET", f"/internal/sessions/{session_id}/documents")


@mcp.tool
async def search_documents(
    query: Annotated[str, Field(min_length=1, description="찾을 내용(자연어 질문이나 키워드)")],
    session_id: SessionId,
    top_k: Annotated[int, Field(ge=1, le=10, description="돌려줄 청크 수(기본 3)")] = 3,
) -> dict[str, Any]:
    """이 세션에 공개된 회사 문서에서 질문과 가까운 문단을 찾는다.

    세션의 카탈로그 버전으로 색인된 청크 중 공개된 문서만 코사인 유사도 순으로 돌려준다.
    결과는 [{doc_id, title, chunk, score}]. 해당 버전 색인이 없으면 upstream_unavailable.
    """
    listed = await _session_documents(session_id)
    if not listed["ok"]:
        return listed
    version = listed["data"]["catalog_version"]
    released = {d["doc_id"]: d["title"] for d in listed["data"]["documents"] if d["released"]}
    conf = client.current_settings()
    try:
        if not await store.has_version(conf.database_url, version):
            return fail(
                "upstream_unavailable", f"no index for catalog_version {version}; reindex", True
            )
        if not released:
            return ok([])
        vector = (await embed(get_embedder(conf.embedding_model), [query]))[0]
        rows = await store.search(conf.database_url, version, list(released), vector, top_k)
    except DB_ERRORS as exc:
        return fail("upstream_unavailable", f"database: {type(exc).__name__}", True)
    return ok(
        [
            {
                "doc_id": r["doc_id"],
                "title": released[r["doc_id"]],
                "chunk": r["content"],
                "score": round(float(r["score"]), 4),
            }
            for r in rows
        ]
    )


@mcp.tool
async def get_document(doc_id: DocId, session_id: SessionId) -> dict[str, Any]:
    """공개된 회사 문서 하나의 전문을 읽는다. 결과는 {doc_id, title, content}.

    본문은 세션의 카탈로그 버전으로 색인된 내용이라 같은 채용 건의 지원자는 같은 문서를 본다.
    아직 공개되지 않은 문서는 not_released, 없는 문서는 not_found,
    해당 버전 색인이 없으면 upstream_unavailable.
    """
    listed = await _session_documents(session_id)
    if not listed["ok"]:
        return listed
    entry = next((d for d in listed["data"]["documents"] if d["doc_id"] == doc_id), None)
    if entry is None:
        return fail("not_found", f"document {doc_id} not found")
    if not entry["released"]:
        return fail("not_released", f"document {doc_id} is not released yet")
    # 현재 파일이 아니라 세션 버전의 청크(400자 슬라이스)를 이어 붙여 원문을 복원한다.
    version = listed["data"]["catalog_version"]
    try:
        parts = await store.document_chunks(client.current_settings().database_url, version, doc_id)
    except DB_ERRORS as exc:
        return fail("upstream_unavailable", f"database: {type(exc).__name__}", True)
    if not parts:
        return fail(
            "upstream_unavailable", f"no index for {doc_id} in catalog_version {version}", True
        )
    return ok({"doc_id": doc_id, "title": entry["title"], "content": "".join(parts)})


@mcp.tool
async def list_documents(session_id: SessionId) -> dict[str, Any]:
    """이 세션의 회사 문서 목록과 공개 여부를 조회한다. 결과는 [{doc_id, title, released}]."""
    listed = await _session_documents(session_id)
    if not listed["ok"]:
        return listed
    return ok(listed["data"]["documents"])


@mcp.tool
async def reindex_documents() -> dict[str, Any]:
    """현재 카탈로그 버전으로 고정 회사 문서를 400자 청크로 나눠 다시 색인한다(관리용).

    같은 버전은 덮어써서 몇 번 불러도 결과가 같고, 다른 버전의 청크는 지우지 않아
    진행 중인 채용 건이 자기 버전으로 계속 검색할 수 있다.
    결과는 {indexed: 색인된 청크 수, model, dim, catalog_version}. 에이전트에는 노출하지 않는다.
    """
    conf = client.current_settings()
    version = documents.catalog_version(conf.scenarios_dir)
    pieces = [
        (doc.doc_id, no, text)
        for doc in documents.load_documents(conf.scenarios_dir)
        for no, text in enumerate(documents.chunk(doc.content))
    ]
    embedder = get_embedder(conf.embedding_model)
    vectors = await embed(embedder, [text for _, _, text in pieces])
    chunks = [
        store.Chunk(doc_id, no, text, vector)
        for (doc_id, no, text), vector in zip(pieces, vectors, strict=True)
    ]
    try:
        await store.replace_version(conf.database_url, version, embedder.model, chunks)
    except DB_ERRORS as exc:
        return fail("upstream_unavailable", f"database: {type(exc).__name__}", True)
    return ok(
        {
            "indexed": len(chunks),
            "model": embedder.model,
            "dim": embedder.dim,
            "catalog_version": version,
        }
    )
