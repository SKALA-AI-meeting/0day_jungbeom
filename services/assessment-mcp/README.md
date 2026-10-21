# assessment-mcp

평가 기록자 MCP 서버. Streamable HTTP `:9103/mcp`, 헬스 `/health`. 계약: `docs/common/contracts.md` "assessment-mcp", 설계: `docs/mcp/design.md`.

- 도구 6개(`assessment_mcp/tools.py`, 모두 `async def`): record_observation·save_evaluation(변경, 멱등 키 그대로 전달), get_rubric·get_session_record·get_transcript_span(앞 5·뒤 3)·get_contributions(조회). api 내부 앱 호출·오류 매핑은 `client.py`.
- `get_session_record`는 내부 GET(세션·메시지 페이지 반복·칸·기획안·관찰·사실 지표·기여·척도)을 모아 SessionRecord로 조립하고, 관찰 창은 척도 `cards[].window` 규칙과 칸 확정 시각으로 계산한다. completed 전이면 `conflict`.
- 모든 도구 호출은 `X-Assessment-Token`이 `ASSESSMENT_MCP_TOKEN`과 같아야 하고 아니면 api를 부르지 않고 `forbidden`(서버 토큰이 비면 전부 거부). 페르소나 에이전트는 이 서버에 접근하지 못한다(허용 목록·토큰).

```
uv run python -m assessment_mcp   # 9103
uv run pytest   # api는 httpx MockTransport, 출력은 tests/contract_shape.py MCP_TOOLS 형태로 검사
```

환경: `API_INTERNAL_URL`, `INTERNAL_TOKEN`, `ASSESSMENT_MCP_TOKEN`.
