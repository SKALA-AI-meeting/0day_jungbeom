"""Offline RAG pipeline (Pipe and Filter): Documents -> Chunking -> Embedding -> Indexing -> Vector DB.

Run once before rag-mcp serves queries (compose service `rag-indexer`):
  uv run --python 3.12 python -m rag_pipeline.index
Chunks are cut per article ("## " heading) and carry source metadata (company, document, section, version).
"""
from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from . import embedding, store  # noqa: E402

DOCS = Path(__file__).resolve().parent / "documents"
MAX_CHARS = 700
log = logging.getLogger("dayzero.rag.index")


def load_documents() -> list[dict]:
    docs = []
    for path in sorted(DOCS.glob("*/*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        head = {}
        while lines and ":" in lines[0] and not lines[0].startswith("#"):
            k, v = lines.pop(0).split(":", 1)
            head[k.strip()] = v.strip()
        docs.append({"company": path.parent.name, "doc": head.get("title", path.stem), "version": head.get("version", "0"),
                     "path": str(path.relative_to(DOCS)), "body": "\n".join(lines)})
    return docs


def chunk(doc: dict) -> list[dict]:
    """One chunk per article; long articles are split on blank lines / bullets."""
    out, section, buf = [], "본문", []

    def flush():
        text = "\n".join(buf).strip()
        if not text:
            return
        parts, cur = [], ""
        for para in text.split("\n"):
            if len(cur) + len(para) > MAX_CHARS and cur:
                parts.append(cur)
                cur = ""
            cur += para + "\n"
        parts.append(cur)
        for p in parts:
            out.append({k: doc[k] for k in ("company", "doc", "version", "path")} | {"section": section, "content": f"[{doc['doc']} · {section}]\n{p.strip()}"})

    for line in doc["body"].splitlines():
        if line.startswith("## "):
            flush()
            section, buf = line[3:].strip(), []
        else:
            buf.append(line)
    flush()
    return out


def build() -> dict:
    chunks = [c for d in load_documents() for c in chunk(d)]
    vectors = embedding.embed([c["content"] for c in chunks])
    return store.write(chunks, vectors, embedding.model_name(), embedding.dims())


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    print(build())
