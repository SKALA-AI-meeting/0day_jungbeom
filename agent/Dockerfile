FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
ENV PATH="/app/.venv/bin:$PATH"
# one image, several services: agent (uvicorn), business-mcp, rag-mcp, detector-mcp, analytics-mcp, rag-indexer
CMD ["uvicorn", "app.agent_api:app", "--host", "0.0.0.0", "--port", "8000"]
