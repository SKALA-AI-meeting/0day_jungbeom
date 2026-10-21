"""Vector store: pgvector (VECTOR_DB_URL) or a local JSON index (tests / offline)."""
from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

LOCAL_INDEX = Path(os.getenv("RAG_LOCAL_INDEX", Path(__file__).resolve().parent / "index.json"))


def _pg():
    import psycopg
    from pgvector.psycopg import register_vector

    conn = psycopg.connect(os.environ["VECTOR_DB_URL"], autocommit=True)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    return conn


def use_pg() -> bool:
    return bool(os.getenv("VECTOR_DB_URL"))


def write(chunks: list[dict], vectors: list[list[float]], model: str, dims: int) -> dict:
    meta = {"model": model, "dims": dims, "chunks": len(chunks), "built_at": time.time(),
            "documents": len({(c["company"], c["doc"]) for c in chunks})}
    if use_pg():
        import numpy as np

        with _pg() as conn:
            conn.execute("DROP TABLE IF EXISTS rag_chunks")
            conn.execute(f"""CREATE TABLE rag_chunks (id SERIAL PRIMARY KEY, company TEXT, doc TEXT, section TEXT, version TEXT,
                             path TEXT, content TEXT, embedding vector({dims}))""")
            conn.execute("CREATE TABLE IF NOT EXISTS rag_index_meta (id INT PRIMARY KEY, meta JSONB)")
            with conn.cursor() as cur:
                for c, v in zip(chunks, vectors):
                    cur.execute("INSERT INTO rag_chunks (company, doc, section, version, path, content, embedding) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                                (c["company"], c["doc"], c["section"], c["version"], c["path"], c["content"], np.array(v)))
            conn.execute("CREATE INDEX ON rag_chunks USING hnsw (embedding vector_cosine_ops)")
            conn.execute("INSERT INTO rag_index_meta (id, meta) VALUES (1, %s) ON CONFLICT (id) DO UPDATE SET meta = EXCLUDED.meta", (json.dumps(meta),))
    else:
        LOCAL_INDEX.write_text(json.dumps({"meta": meta, "chunks": [{**c, "embedding": v} for c, v in zip(chunks, vectors)]}, ensure_ascii=False))
    return meta


def meta() -> dict | None:
    if use_pg():
        with _pg() as conn:
            exists = conn.execute("SELECT to_regclass('rag_index_meta')").fetchone()[0]
            if not exists:
                return None
            row = conn.execute("SELECT meta FROM rag_index_meta WHERE id = 1").fetchone()
            return row[0] if row else None
    if not LOCAL_INDEX.exists():
        return None
    return json.loads(LOCAL_INDEX.read_text())["meta"]


def search(vector: list[float], companies: list[str], k: int) -> list[dict]:
    if use_pg():
        import numpy as np

        with _pg() as conn:
            rows = conn.execute(
                """SELECT company, doc, section, version, content, 1 - (embedding <=> %s) AS score
                   FROM rag_chunks WHERE company = ANY(%s) ORDER BY embedding <=> %s LIMIT %s""",
                (np.array(vector), companies, np.array(vector), k)).fetchall()
        return [{"company": r[0], "doc": r[1], "section": r[2], "version": r[3], "content": r[4], "score": round(float(r[5]), 4)} for r in rows]
    data = json.loads(LOCAL_INDEX.read_text())
    scored = []
    for c in data["chunks"]:
        if c["company"] not in companies:
            continue
        s = sum(a * b for a, b in zip(vector, c["embedding"])) / ((math.sqrt(sum(a * a for a in vector)) * math.sqrt(sum(b * b for b in c["embedding"]))) or 1)
        scored.append({k2: c[k2] for k2 in ("company", "doc", "section", "version", "content")} | {"score": round(s, 4)})
    return sorted(scored, key=lambda x: -x["score"])[:k]


def documents(company: str | None) -> list[dict]:
    if use_pg():
        with _pg() as conn:
            q = "SELECT company, doc, version, count(*) FROM rag_chunks" + (" WHERE company = %s" if company else "") + " GROUP BY 1,2,3 ORDER BY 1,2"
            rows = conn.execute(q, (company,) if company else ()).fetchall()
        return [{"company": r[0], "doc": r[1], "version": r[2], "chunks": r[3]} for r in rows]
    data = json.loads(LOCAL_INDEX.read_text())
    agg: dict = {}
    for c in data["chunks"]:
        if company and c["company"] != company:
            continue
        key = (c["company"], c["doc"], c["version"])
        agg[key] = agg.get(key, 0) + 1
    return [{"company": a, "doc": b, "version": v, "chunks": n} for (a, b, v), n in sorted(agg.items())]
