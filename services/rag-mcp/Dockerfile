FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
# BGE-M3 가중치는 이미지에 넣지 않고 시작 시 HF_HOME(볼륨)에 받아 재사용한다.
ENV HF_HOME=/models
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY rag_mcp ./rag_mcp
EXPOSE 9102
CMD ["python", "-m", "rag_mcp"]
