# 테스트 픽스처

`contracts/`는 `docs/common/contracts.md`의 예시 JSON을 그대로 옮긴 것이다. 서비스 사이(MCP·api·web mock)가
같은 예시를 공유한다. 계약 예시가 바뀌면 이 폴더와 `apps/web/mocks/fixtures/`를 함께 갱신한다.

| 파일 | 계약 |
|---|---|
| `report.json` | Report |
| `state.json` | State 스냅샷 |
| `message.json` | Message (State의 첫 메시지) |
| `mcp_ok.json`, `mcp_error.json` | MCP 공통 응답 형식 |
| `ws_events.json` | WS 프레임 `{at_ms, type, payload}` 재생 예시(지원자 메시지 → 동료 응답, 문서 공개) |
