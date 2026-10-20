"""`doc_chunks`(pgvector) 읽기·쓰기. 키는 (catalog_version, doc_id, chunk_no).

호출이 드물어(검색은 에이전트 응답당 1회 안팎) 호출마다 연결한다.
"""

from contextlib import asynccontextmanager
from dataclasses import dataclass

import asyncpg
import numpy as np
from pgvector.asyncpg import register_vector


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    chunk_no: int
    content: str
    embedding: np.ndarray


@asynccontextmanager
async def connect(database_url: str):
    conn = await asyncpg.connect(database_url)
    try:
        await register_vector(conn)
        yield conn
    finally:
        await conn.close()


async def replace_version(database_url: str, version: str, model: str, chunks: list[Chunk]) -> None:
    """이 버전의 청크만 새로 쓴다. 다른 버전 청크는 그대로 둔다(같은 버전 재실행은 멱등)."""
    async with connect(database_url) as conn, conn.transaction():
        await conn.execute("DELETE FROM doc_chunks WHERE catalog_version = $1", version)
        await conn.executemany(
            "INSERT INTO doc_chunks (catalog_version, doc_id, chunk_no, content, embedding, model)"
            " VALUES ($1, $2, $3, $4, $5, $6)",
            [(version, c.doc_id, c.chunk_no, c.content, c.embedding, model) for c in chunks],
        )


async def has_version(database_url: str, version: str) -> bool:
    async with connect(database_url) as conn:
        return await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM doc_chunks WHERE catalog_version = $1)", version
        )


async def document_chunks(database_url: str, version: str, doc_id: str) -> list[str]:
    """이 버전의 문서 청크 본문을 chunk_no 순으로."""
    async with connect(database_url) as conn:
        rows = await conn.fetch(
            "SELECT content FROM doc_chunks WHERE catalog_version = $1 AND doc_id = $2"
            " ORDER BY chunk_no",
            version,
            doc_id,
        )
    return [r["content"] for r in rows]


async def search(
    database_url: str, version: str, doc_ids: list[str], query: np.ndarray, top_k: int
) -> list[asyncpg.Record]:
    """같은 버전·허용된 doc_id 안에서 코사인 유사도 상위 top_k. score = 1 - 코사인 거리."""
    async with connect(database_url) as conn:
        return await conn.fetch(
            "SELECT doc_id, chunk_no, content, 1 - (embedding <=> $1) AS score FROM doc_chunks"
            " WHERE catalog_version = $2 AND doc_id = ANY($3::text[])"
            " ORDER BY embedding <=> $1 LIMIT $4",
            query,
            version,
            doc_ids,
            top_k,
        )
