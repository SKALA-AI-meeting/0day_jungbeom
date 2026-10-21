"""`material_chunks`(pgvector) 읽기·쓰기. 키는 (catalog_version, material_id, chunk_no).

검색은 세션의 catalog_version과 확정 키워드(keyword_key)로 거른다. 원문은 api가 `materials`
테이블에서 읽으므로 여기서는 청크만 다룬다. 호출이 드물어 호출마다 연결한다.
"""

from contextlib import asynccontextmanager
from dataclasses import dataclass

import asyncpg
import numpy as np
from pgvector.asyncpg import register_vector


@dataclass(frozen=True)
class Chunk:
    material_id: str
    keyword_key: str
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
        await conn.execute("DELETE FROM material_chunks WHERE catalog_version = $1", version)
        await conn.executemany(
            "INSERT INTO material_chunks"
            " (catalog_version, material_id, keyword_key, chunk_no, content, embedding, model)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7)",
            [
                (version, c.material_id, c.keyword_key, c.chunk_no, c.content, c.embedding, model)
                for c in chunks
            ],
        )


async def has_version(database_url: str, version: str) -> bool:
    async with connect(database_url) as conn:
        return await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM material_chunks WHERE catalog_version = $1)", version
        )


async def search(
    database_url: str,
    version: str,
    keyword_key: str,
    material_ids: list[str],
    query: np.ndarray,
    top_k: int,
) -> list[asyncpg.Record]:
    """같은 버전·키워드·열린 자료 안에서 코사인 유사도 상위 top_k. score = 1 - 코사인 거리."""
    async with connect(database_url) as conn:
        return await conn.fetch(
            "SELECT material_id, chunk_no, content, 1 - (embedding <=> $1) AS score"
            " FROM material_chunks"
            " WHERE catalog_version = $2 AND keyword_key = $3 AND material_id = ANY($4::text[])"
            " ORDER BY embedding <=> $1 LIMIT $5",
            query,
            version,
            keyword_key,
            material_ids,
            top_k,
        )
