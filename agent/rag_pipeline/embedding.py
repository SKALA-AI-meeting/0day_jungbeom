"""Embedding providers. The index stores the model name and dimension; queries must use the same ones."""
from __future__ import annotations

import hashlib
import math
import os


def provider() -> str:
    return os.getenv("EMBEDDING_PROVIDER") or ("openai" if os.getenv("OPENAI_API_KEY") else "local")


def model_name() -> str:
    return os.getenv("EMBEDDING_MODEL", "text-embedding-3-small") if provider() == "openai" else "local-char-bigram-256"


def dims() -> int:
    return 1536 if provider() == "openai" else 256


def _local(text: str) -> list[float]:
    """Deterministic offline embedding (character bigrams hashed to 256 dims) for tests without an API key."""
    v = [0.0] * 256
    t = "".join(text.split())
    for i in range(len(t) - 1):
        h = int(hashlib.md5(t[i:i + 2].encode()).hexdigest(), 16) % 256
        v[h] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def embed(texts: list[str]) -> list[list[float]]:
    if provider() == "local":
        return [_local(t) for t in texts]
    from openai import OpenAI

    client = OpenAI()
    out: list[list[float]] = []
    for i in range(0, len(texts), 64):
        resp = client.embeddings.create(model=model_name(), input=texts[i:i + 64])
        out += [d.embedding for d in resp.data]
    return out
