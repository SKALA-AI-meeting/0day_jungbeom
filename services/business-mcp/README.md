# business-mcp

설계: `docs/mcp/design.md`. 계약: `docs/common/contracts.md`(MCP 도구 표·오류 코드·내부 REST).

- 도구 10개는 `business_mcp/tools.py`, api 내부 앱(`API_INTERNAL_URL`, `X-Internal-Token`) 호출은 `client.py`.
- 실행: `uv run python -m business_mcp` (9101, `/mcp`·`/health`). 테스트: `uv run pytest` (api는 httpx MockTransport로 mock).
