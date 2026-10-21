"""rag-mcp (FastMCP, :9102/mcp): search pre-indexed company documents and return sources.

Read-only by design (PDF table 5-4: rag-mcp must not change business data).
  조회  search_docs, list_documents, index_info
The query is embedded with the same model recorded in the index metadata; a mismatch is refused.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT.parent / ".env")
sys.path.insert(0, str(ROOT))
from rag_pipeline import embedding, store  # noqa: E402

SHARED = "공통"
MAX_CONTENT = 600
mcp = FastMCP("rag-mcp", instructions="회사 문서(소개·규정·지표·회의록)에서 질문과 가까운 조항을 찾아 출처와 함께 돌려준다.")


def _meta() -> dict:
    m = store.meta()
    if not m:
        raise ToolError("503 문서 색인이 아직 없어요. rag-indexer(python -m rag_pipeline.index)를 먼저 실행해 주세요.")
    if m["model"] != embedding.model_name():
        raise ToolError(f"409 색인 모델({m['model']})과 질의 모델({embedding.model_name()})이 달라요. 같은 모델로 다시 색인해 주세요.")
    return m


@mcp.tool
def search_docs(query: str, company: str, k: int = 3) -> dict:
    """[조회] 회사 문서에서 query와 가까운 조항 k개(최대 5)를 찾는다. 공통 협업 가이드도 함께 검색한다."""
    if not query.strip():
        raise ToolError("400 query가 비어 있어요.")
    if not company.strip():
        raise ToolError("400 company가 필요해요.")
    meta = _meta()
    vec = embedding.embed([query])[0]
    hits = store.search(vec, [company, SHARED], max(1, min(int(k), 5)))
    for h in hits:
        h["content"] = h["content"][:MAX_CONTENT]
    return {"query": query, "company": company, "model": meta["model"], "results": hits}


@mcp.tool
def list_documents(company: str | None = None) -> list[dict]:
    """[조회] 색인된 문서 목록(회사, 문서명, 버전, 청크 수)."""
    _meta()
    return store.documents(company)


@mcp.tool
def index_info() -> dict:
    """[조회] 색인 메타데이터: 임베딩 모델, 차원, 문서·청크 수, 생성 시각."""
    return _meta()


if __name__ == "__main__":
    mcp.run(transport="http", host=os.getenv("MCP_HOST", "127.0.0.1"), port=int(os.getenv("RAG_MCP_PORT", "9102")))
