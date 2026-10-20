"""실제 BGE-M3(CPU) 확인. 기본 실행에서 빠진다: `uv run pytest -m live`."""

import numpy as np
import pytest
from rag_mcp.embedder import BgeM3Embedder

pytestmark = pytest.mark.live


def test_bge_m3_embeds_1024_normalized_and_ranks_related_text_higher():
    embedder = BgeM3Embedder()
    vectors = embedder.embed(
        ["유료 기능 출시 정책", "올해는 유료 기능을 출시하지 않는다", "러닝 모임 일정"]
    )
    assert vectors.shape == (3, 1024)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-3)
    assert vectors[0] @ vectors[1] > vectors[0] @ vectors[2]
