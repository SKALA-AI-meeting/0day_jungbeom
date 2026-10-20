"""임베딩 인터페이스. 서버는 BGE-M3(sentence-transformers, CPU)를 시작 시 1회 로드하고,
테스트는 결정적 Fake로 바꿔 끼운다(`set_embedder`).

모델 캐시 경로는 Hugging Face 표준 env `HF_HOME`(컨테이너 기본 /models)을 따른다.
"""

import asyncio
import threading
from typing import Protocol

import numpy as np

DIM = 1024


class Embedder(Protocol):
    model: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray:
        """L2 정규화된 (len(texts), dim) float32 배열."""
        ...


class BgeM3Embedder:
    """BAAI/bge-m3 dense 임베딩. import와 로드는 첫 `load()`까지 미룬다."""

    dim = DIM

    def __init__(self, model: str = "BAAI/bge-m3") -> None:
        self.model = model
        self._st = None
        self._lock = threading.Lock()

    def load(self) -> None:
        with self._lock:
            if self._st is None:
                from sentence_transformers import SentenceTransformer

                self._st = SentenceTransformer(self.model, device="cpu")

    def embed(self, texts: list[str]) -> np.ndarray:
        self.load()
        vectors = self._st.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return vectors.astype(np.float32)


_embedder: Embedder | None = None


def set_embedder(embedder: Embedder | None) -> None:
    global _embedder
    _embedder = embedder


def get_embedder(model: str) -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = BgeM3Embedder(model)
    return _embedder


async def embed(embedder: Embedder, texts: list[str]) -> np.ndarray:
    # CPU 추론이라 이벤트 루프를 막지 않게 스레드에서 돌린다.
    return await asyncio.to_thread(embedder.embed, texts)
