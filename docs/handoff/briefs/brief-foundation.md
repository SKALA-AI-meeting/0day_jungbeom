# 브리프: foundation 트랙 (W0)

역할: foundation 개발. worktree는 현재 폴더(`Day-0_zaeho.worktrees/foundation`), 브랜치 `track/foundation`. 커밋은 이 브랜치에만. main 병합·push는 하지 않는다.

## 읽을 것 (순서대로)
1. `AGENTS.md`
2. `docs/plan.md` — M0.5 foundation 행(범위·완료 기준), "파일 소유권" foundation 행
3. `docs/dev-process.md` — 도구(uv·ruff·pnpm), 로컬 실행, `app.run` 두 리스너, `infra/docker-compose.dev.yml`, pytest `live` 마커, seed 위치, 비밀값
4. `docs/common/architecture.md`, `docs/common/data-model.md`, `docs/common/contracts.md`, `docs/common/scenario-model.md`
5. `docs/api/design.md` — 구조 표의 [foundation] 항목, SessionService, 완료 기준 foundation 줄
6. `docs/frontend/design.md`, `docs/mcp/design.md`, `docs/worker-infra/design.md` — foundation이 만드는 최소 골격 부분만
7. `infra/`(compose, schema.sql, .env.example), `scenarios/catalog.yaml`, `Makefile`, `ruff.toml`

## 범위
`docs/plan.md` M0.5 행 그대로: 서비스 5개의 최소 앱(Dockerfile, `/health`, pyproject·lockfile), api 공용 기반(config, db, models, auth, SessionService, scenario, hub, queue, masking, AgentRunner Protocol + FakeAgentRunner), web 기본(Next 앱, 디자인 토큰, 공용 컴포넌트는 props만, `mocks/` 골격, `/api/health`), `scenarios/version.py`, `scripts/seed.py`, `tests/conftest.py`·`tests/fixtures/` 골격, `infra/.env.local` 생성(`infra/.env`를 복사해 호스트명만 localhost로, git 무시 확인).
소유권 표의 foundation 파일만 만든다. 라우터(`app/routers/*`), 스케줄러, agent 그래프, MCP 도구 구현, 워커 그래프, 관리자·지원자 화면은 다른 트랙이다. 각 MCP·worker는 진입점과 `/health`(worker는 heartbeat 파일)까지만.
`docs/common/contracts.md`는 바꾸지 않는다. 계약이나 스키마가 바뀌어야 하면 멈추고 보고한다. 문서와 어긋남을 발견하면 추측하지 말고 보고에 적는다.

## 방식
TDD, happy path 중심(`docs/dev-process.md`). LLM 호출 없음(FakeAgentRunner). 테스트는 완료 기준 한 줄당 하나.
DB는 `make infra-up`으로 띄운 postgres(5432)를 쓴다. 통합 스택은 한 번에 하나이므로 api를 두 개 띄우지 않는다.
`infra/.env` 안의 키 값은 절대 출력하거나 파일에 옮겨 적지 않는다(파일에서만 읽는다).
커밋 메시지는 한국어 한 문장, 본문에 실행한 테스트 명령.

## 완료 기준 (plan.md M0.5)
1. `make up`(전체 compose)에서 전부 healthy: api·business-mcp·rag-mcp `/health`, web `/api/health`, worker heartbeat 파일
2. `make infra-up` 후 로컬 `uv run python -m app.run`이 8000·8001 둘 다 응답
3. SessionService 단위 테스트(전이 전부·멱등)
4. 시나리오 조립 결과가 `docs/common/scenario-model.md` 수치와 일치하는 테스트
5. FakeAgentRunner로 메시지→내부 저장→hub 브로드캐스트 단위 테스트
6. `make test`, `make lint` 통과

## 보고
끝나면 완료 기준 각 줄을 직접 실행해 명령과 결과(요약)를 아래 경로에 Markdown으로 저장한다. 파일 수정 목록, 남은 문제, 문서와 어긋난 점, 다른 트랙에 알릴 것을 함께 적는다.
저장 경로: /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-day-zero/90e4e69c-acb7-4a6e-b8e2-a14b26e6a4e7/scratchpad/foundation-report.md
마지막 응답은 그 파일 경로 한 줄만.
