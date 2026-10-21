# assessment-mcp

평가 기록자 MCP 서버. Streamable HTTP `:9103/mcp`, 헬스 `/health`. 계약: `docs/common/contracts.md` "assessment-mcp", 설계: `docs/mcp/design.md`.

G-F 골격(서버·`/health`·Dockerfile)만 있다. 도구 6개와 `X-Assessment-Token` 검사는 mcp 트랙이 더한다. 페르소나 에이전트는 이 서버에 접근하지 못한다(허용 목록·토큰).

```
uv run python -m assessment_mcp   # 9103
uv run pytest
```

환경: `API_INTERNAL_URL`, `INTERNAL_TOKEN`, `ASSESSMENT_MCP_TOKEN`.
