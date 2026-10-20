# 브리프: api-fix 트랙 (P2 보충, 작은 api 변경 묶음)

역할: P2 리뷰에서 모인 api 수준 변경 요청을 한 번에 처리한다. worktree `../Day-0_zaeho.worktrees/api-fix`(현재 폴더), 브랜치 `track/api-fix`. 기준 커밋 main 최신(agent-session·agent-assistant 병합 포함), 계약 커밋 537889b.

## 공통 규칙
커밋은 자기 브랜치에만. 키 값 출력 금지. TDD happy path(항목당 테스트 1). 주석은 역할·알아야 할 로직·예외 의도 수준. `docs/common/*`·`apps/web/`·`app/agent/` 수정 금지(필요하면 변경 요청). 같은 시각에 web-integrate가 `apps/web/`을 고친다. 실제 스택 사용 안 함(격리 DB).

## 읽을 것
AGENTS.md, `docs/common/contracts.md`(assistant 경로·내부 테스트 세션·agent_runs), `docs/common/harness.md`(마스킹·Recovery), `docs/handoff.md`의 "P2 진행 중 모인 api 수준 변경 요청", `docs/handoff/reports/agent-assistant-report.md` 변경 요청, `docs/handoff/reports/web-integrate-report.md` 변경 요청 1, `app/routers/candidate.py` 어시스턴트 경로, `app/routers/internal.py` test/sessions, `app/run.py`, `app/services/context.py`, `app/masking.py`, `app/agent/assistant/runner.py`(graph()·aclose 시그니처).

## 허용 파일
`services/api/app/routers/{candidate,internal}.py`, `services/api/app/run.py`, `services/api/app/services/context.py`(필요 시), `services/api/tests/`(자기 테스트 파일), `tests/fixtures/contracts/internal_test_session*.json`(요청 예시에 company_id 추가, 형태만).

## 범위 (전부)
1. `POST /sessions/{id}/assistant`: 요청 메시지 저장 전 `app.masking.mask` 적용(저장·그래프 입력 모두 마스킹된 본문), 60회 카운트 조회→INSERT를 세션 Lock 또는 행 잠금으로 직렬화(동시 2요청에 61번째가 생기지 않음).
2. `app/run.py`: 기동 시 `ctx.assistant.graph()`(있으면) warm-up, 종료 시 `aclose()` — 세션 러너와 같은 방식. ASSISTANT_RUNNER=fake면 건너뜀.
3. `POST /internal/test/sessions`: 요청에 `company_id?` 또는 `admin_email?`을 받아 그 회사의 채용 건으로 세션을 만든다(없으면 기존 고정 회사). contracts.md 표는 오케스트레이터가 고친다(변경 요청으로 요청/응답 예시 첨부).
4. 위 3건의 테스트(격리 DB): 마스킹된 저장 1, 동시 요청 한도 1, warm-up/aclose 호출 1(Fake로), company_id 지정 1.

## 완료
`cd services/api && uv run pytest -q`, 루트 `make lint`. 보고서 `docs/handoff/reports/api-fix-report.md`(항목별 명령·결과·검증 방식, 수정 파일, 변경 요청(contracts 표 문구), web-integrate·e2e-runner에 알릴 것). 마지막 응답은 경로 한 줄.
