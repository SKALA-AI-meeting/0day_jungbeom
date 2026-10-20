"""연결 테스트용 MCP 서버 기동: `python mcp_server.py business|rag PORT`.

각 서비스의 가상환경(uv run, cwd=서비스 폴더)에서 실행한다. rag는 BGE-M3 대신 글자 2-gram 해시
임베딩을 쓴다(결정적, 같은 낱말이 많을수록 가깝다). 나머지는 실제 서버 코드 그대로다.
"""

import sys

import uvicorn


def _rag_app():
    import hashlib

    import numpy as np
    from rag_mcp.embedder import DIM, set_embedder
    from rag_mcp.server import create_app

    class BigramEmbedder:
        model = "test-bigram"
        dim = DIM

        def embed(self, texts):
            rows = np.zeros((len(texts), DIM), dtype=np.float32)
            for row, text in zip(rows, texts, strict=True):
                compact = "".join(text.split())
                for i in range(len(compact) - 1):
                    digest = hashlib.blake2b(compact[i : i + 2].encode(), digest_size=4).digest()
                    row[int.from_bytes(digest, "big") % DIM] += 1.0
                row /= np.linalg.norm(row) or 1.0
            return rows

    set_embedder(BigramEmbedder())
    return create_app()


def _business_app():
    from business_mcp.server import create_app

    return create_app()


if __name__ == "__main__":
    name, port = sys.argv[1], int(sys.argv[2])
    app = _rag_app() if name == "rag" else _business_app()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
