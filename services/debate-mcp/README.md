# debate-mcp

설계: `docs/mcp/design.md`. 계약: `docs/common/contracts.md`(MCP 도구 표·오류 코드·내부 REST).

- 도구 7개(조회 get_debate_state·get_transcript·get_draft, 변경 post_message·propose_option·set_stance·fill_slot, 모두 `async def`)는 `debate_mcp/tools.py`, api 내부 앱(`API_INTERNAL_URL`, `X-Internal-Token`) 호출은 `client.py`.
- 실행: `uv run python -m debate_mcp` (9101, `/mcp`·`/health`). 테스트: `uv run pytest` (api는 httpx MockTransport로 mock, 출력은 `tests/contract_shape.py`의 `MCP_TOOLS` 형태로 검사).
- 409의 api 오류 코드(`no_consensus`·`stale_generation`·`slot_confirmed`·`phase_not_open`)는 `{code: conflict, message: <api 코드>}`로 그대로 전달한다.
