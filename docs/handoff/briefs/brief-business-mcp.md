# 브리프: business-mcp 트랙 (W1)
역할: business-mcp 개발. 브랜치 track/business-mcp.
## 공통 규칙
- worktree는 현재 폴더, 커밋은 자기 브랜치에만. main 병합·push 금지.
- 읽을 것: AGENTS.md, docs/plan.md(자기 트랙 행·파일 소유권·병렬 작업 규칙), docs/dev-process.md, docs/common/contracts.md, docs/decisions.md 맨 아래 "foundation 리뷰 반영" 절.
- foundation 결과를 먼저 본다: 보고서 /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/foundation-report.md 와 /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/foundation-report-2.md 의 "다른 트랙에 알릴 것" 절(자기 트랙 항목).
- 소유권 밖 파일(foundation 소유 파일, contracts.md, 다른 트랙 폴더)은 수정하지 않는다. 바꿔야 하면 보고서에 "변경 요청"으로 적고 가능한 범위에서 계속 진행한다.
- TDD, happy path 중심. 완료 기준 한 줄당 테스트 하나. LLM 호출 없음(mock). DB는 공용 postgres(`make infra-up`은 main 저장소에서 이미 떠 있음, localhost:5432). api 테스트는 실행마다 임시 DB를 만드는 conftest를 그대로 쓴다. 통합 스택은 한 번에 하나이므로 `make up`·`app.run` 상시 기동 금지(필요하면 잠깐 띄우고 내린다).
- `infra/.env` 키 값은 출력·복사 금지.
- 커밋 메시지는 한국어 한 문장, 본문에 실행한 테스트 명령.
- 끝나면 완료 기준 각 줄을 직접 실행해 명령·결과, 수정 파일 목록, 남은 문제, 변경 요청, 다른 트랙에 알릴 것을 Markdown으로 저장한다. 마지막 응답은 그 파일 경로 한 줄만.
## 추가로 읽을 것
docs/mcp/design.md(business-mcp 절·완료 기준), docs/common/contracts.md의 MCP 도구 표·오류 코드·내부 API, docs/common/harness.md(Tools·Guardrails), services/business-mcp/ 현재 골격(FastMCP 4.1.1, /mcp, /health), tests/fixtures/contracts/mcp_ok.json·mcp_error.json.
## 범위
`services/business-mcp/` 전체(진입점 소유권은 병합 후 이 트랙으로 넘어옴). 계약의 도구 10개를 Pydantic 입력 모델·docstring·`{ok, data}`/`{ok:false, error:{code,...}}` 반환으로 구현. api 내부 앱(`API_INTERNAL_URL`, 8001)을 httpx로 호출, `X-Internal-Token` 전달, DB 접근 없음. 4xx→코드 매핑(404 not_found, 403 forbidden, 409 conflict, 422 invalid_input), 5xx·연결 실패→upstream_unavailable(1회 재시도), 타임아웃 10초. post_message meta·멱등 키(run_id·seq 등)는 그대로 전달. 내부 API는 아직 없으므로 테스트는 respx 또는 httpx MockTransport로 api 응답을 mock한다. 의존성은 자기 pyproject·lock에 추가.
## 완료 기준 (plan.md·mcp/design.md)
MCP Inspector(또는 fastmcp 클라이언트)로 도구 목록·설명 확인(명령·출력 기록), 오류 코드 매핑 테스트(403→forbidden, 422→invalid_input, 연결 실패→upstream_unavailable 재시도 1회), 같은 run_id·seq 재호출을 api에 그대로 전달(중복 생성 안 함). `uv run pytest`, 루트 `make test`·`make lint` 통과.
## 보고서 경로
/private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/business-mcp-report.md
