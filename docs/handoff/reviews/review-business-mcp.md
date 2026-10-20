검증 결과: **테스트 10개 통과**, business-mcp의 Ruff 린트·포맷 검사 통과. 실제 API·WS 연동은 미검증입니다.

### 1) 반드시 고칠 것 — 병합 차단

- **[P2] 내부 인증 실패를 `invalid_input`으로 반환하지 않도록 수정** — `services/business-mcp/business_mcp/client.py:80`  
  내부 API는 토큰 불일치 시 401을 반환합니다(`services/api/app/auth.py:121`). 현재 이를 `invalid_input`으로 바꾸는 것을 재현했습니다. 호출 인자를 고쳐도 해결되지 않는 서비스 인증 문제이므로, `forbidden` 또는 `internal`로 매핑하고 API 트랙과 확정해야 합니다.

### 2) 고치면 좋은 것

- **성공 응답의 JSON 해석 실패도 공통 오류 형식으로 반환** — `services/business-mcp/business_mcp/client.py:78`  
  200 응답에 비 JSON 본문을 주면 `isError=true`, `structured_content=None`이 됩니다. 보고서의 “항상 `{ok,...}` 반환”과 달라지므로, 해당 예외를 계약의 오류 코드로 변환하면 호출 측 처리가 일관됩니다.

### 3) 보고서 쟁점별 의견

- **410 → `conflict`: 의미상 수용 가능하나 합의 필요** — `services/business-mcp/business_mcp/client.py:21`  
  만료·취소 상태를 변경 불가 충돌로 표현하는 것은 합리적입니다. 다만 현재 MCP 매핑 계약에 없으므로 확정된 규칙처럼 취급해서는 안 됩니다.

- **423 → `not_released`: 타당** — `services/business-mcp/business_mcp/client.py:23`  
  `docs/common/contracts.md:113`의 공개 전 문서 응답과 같은 의미입니다.

- **나머지 4xx → `invalid_input`: 일괄 적용은 부적절** — `services/business-mcp/business_mcp/client.py:80`  
  400의 입력·도메인 검증 실패에는 맞지만, 401의 내부 인증 실패까지 같은 코드로 표현하면 원인이 왜곡됩니다.

- **멱등 키·메타 전달: 적합** — `services/business-mcp/business_mcp/tools.py:89`, `:133`, `:161`  
  `run_id·seq`, `part_no·run_id`, `element·window_start`와 `meta`를 보존하며 중복 판단은 API에 맡깁니다.

- **재시도·타임아웃: 적합** — `services/business-mcp/business_mcp/client.py:69`, `:72`  
  HTTPX 타임아웃 10초, 전송 오류·5xx에 최초 포함 최대 2회, 4xx 무재시도로 설계와 일치합니다.

- **`limit≤50`, 느슨한 `parts` 검증: 수용 가능** — `services/business-mcp/business_mcp/tools.py:50`, `:100`  
  조회 상한은 하네스와 일치하고, 분업의 상세 조건을 API가 판단하도록 한 것도 계약에 맞습니다.

- **Inspector 대체: 기능 확인은 됐으나 완료 기준 대체를 명시할 필요** — `services/business-mcp/tests/test_tools.py:28`  
  FastMCP 클라이언트로 목록·설명·스키마를 확인했지만, `docs/mcp/design.md:19`에 명시된 Inspector 확인 자체를 수행한 것은 아닙니다.

- **테스트 범위·MVP 규모: 적절** — `services/business-mcp/tests/test_tools.py:1`  
  정상 전달, 계약 오류, 재시도, 멱등 키 검증 중심이며 과도한 테스트나 불필요한 계층 분리는 없습니다.

### 4) 다른 트랙 주의사항

- **API: 변경 요청은 응답 유실 후 재전송될 수 있음** — `services/business-mcp/business_mcp/client.py:72`  
  저장 후 응답만 실패해도 재시도하므로 계약된 멱등 처리가 필수입니다.

- **Agent: `ok:false`를 반환값으로 처리해야 함** — `services/business-mcp/business_mcp/server.py:21`  
  입력 검증 실패도 MCP 예외가 아닌 구조화된 결과로 전달됩니다. `session_id` 주입·도구 허용 목록은 그래프 책임입니다(`docs/common/contracts.md:185`).

- **소유권 위반 없음; main 변경은 보존해야 함** — `docs/handoff.md:8`, `:51`  
  `main..HEAD`의 handoff 차이는 main에만 있는 `99f2fff` 때문에 발생했습니다. 트랙 커밋 `4772b8c`의 실제 변경은 `services/business-mcp/` 안의 7개 파일뿐입니다.

- **통합 검증은 agent-min에서 이어서 수행** — `docs/plan.md:19`, `:65`  
  현재 mock 테스트는 키 전달만 증명합니다. 실제 중복 저장 방지와 그래프→MCP→API→WS 흐름은 후속 연결 테스트에서 확인해야 합니다.