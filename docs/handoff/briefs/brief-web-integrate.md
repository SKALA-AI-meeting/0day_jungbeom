# 브리프: web-integrate 트랙 (P2)

역할: web-redesign mock 화면을 **실 API·WS**에 연결한다. worktree `../Day-0_zaeho.worktrees/web-integrate`(현재 폴더), 브랜치 `track/web-integrate`. 기준 커밋 main 최신(web-polish 병합 뒤), 계약 커밋 37bed0b, catalog_version `b2cc7dd7baa915ca`.

## 공통 규칙
- 커밋은 자기 브랜치에만. 키 값 출력 금지. 주석은 역할·알아야 할 로직·예외 의도 수준.
- `apps/web/` 밖(services·scenarios·tests/fixtures·docs/common)은 수정 금지. api 응답이 계약·픽스처와 다르면 **변경 요청**(경로·실제 응답·기대)으로 보고하고 화면은 계약 기준으로 둔다(api 수정은 오케스트레이터가 배정).
- `components/ui/` 내부·`globals.css`·`public/brand/`는 web-polish가 끝내고 병합했으니 **props·토큰 변경 금지**(레이아웃 손대지 않음).
- 같은 시각에 agent-session·agent-assistant가 `services/api/app/agent/`를 고친다. 이 트랙은 `AGENT_RUNNER=fake`(FakeAgentRunner·FakeAssistantRunner)로 전체 흐름을 잇고, 실제 그래프 인수(아래 2라운드)는 그 두 트랙 병합 뒤 오케스트레이터가 다시 부른다.
- **실제 스택 사용권: 이 트랙이 가진다.** main 저장소에서 `make infra-up`이 떠 있다(postgres 5432·rabbitmq 5672·rag-mcp 9102). 이 worktree에서 `cd services/api && uv run python -m app.run --reload`(8000·8001), `cd services/business-mcp && uv run python -m business_mcp`(9101), `cd services/report-worker && uv run python -m report_worker`를 띄운다. **api는 한 프로세스만**(다른 worktree에서 띄우지 않는다). 스키마 적용·seed(`make seed`)·재색인은 이 트랙만 한다. 끝나면 전부 내린다(`lsof -ti:8000,8001,9101,3000 -sTCP:LISTEN | xargs kill`). 공용 DB의 데이터는 테스트용이라 초기화해도 된다.
- 테스트: 연결 테스트는 vitest가 아니라 **실제 api를 띄운 상태에서 스크립트**(Playwright 또는 Chrome CDP)로 한 세션을 돌리고, 그 기록(단계·응답·스크린샷)을 보고서에 남긴다. 기존 vitest 11개는 통과 유지.

## 읽을 것
AGENTS.md, `docs/common/contracts.md`(전부), `docs/frontend/design.md`, `docs/plan.md`(web-integrate 행·M2 완료 기준·소유권·6건 표의 "화면·최종 인수" 열), `docs/dev-process.md`(로컬 실행·사용권), `docs/handoff/reports/web-redesign-report.md`의 "web-integrate(실 API 연결 때 바꿀 지점)"·수정 라운드 2 Codex 항목(인수 시 확인 목록: 보고 분류·종료 프레임·mock 가정 제거·catalog.documents·픽스처 재비교), `docs/handoff/reports/web-polish-report.md`의 "web-integrate에 알릴 것", `docs/handoff/reports/scenario-redesign-report.md`의 web 항목(문서 카드 본문·회사 문서 제목·FAQ 6문항·no_record_reason 시 observed null·window), `scripts/seed.py`, `services/api/app/routers/{candidate,admin,ws}.py`(실제 응답), `tests/fixtures/contracts/`(정본 예시), `apps/web/components/office/flow.ts`(candidateApi)·`components/admin/client.ts`(adminApi)·`lib/ws.ts`·`lib/api.ts`·`mocks/`.

## 허용 파일
`apps/web/app/`, `apps/web/components/{admin,office}/`(상태 로직·API 호출·reducer·saver), `apps/web/lib/api.ts`·`lib/ws.ts`, `apps/web/mocks/`(정리: 픽스처를 main 공용 픽스처와 같게, worst·mock-controls·data-toggle은 MOCK일 때만), 연결 테스트 스크립트 `apps/web/e2e/`(새 폴더, git 포함, 스크린샷은 무시), `apps/web/.env.example`·`package.json`(필요 시). `components/ui/`·`globals.css`·`public/brand/` 금지.

## 범위 (1라운드, FakeAgentRunner)
1. `NEXT_PUBLIC_MOCK` 없이 `lib/api.ts`·`lib/ws.ts`가 실 api(8000)·WS에 붙는다. 관리자: 가입·로그인 → 채용 건 생성(요소 5개, catalog.documents 표시) → 초대 → 링크. 지원자: 입장 → 동의 → 시작 → 오피스(State 복원, alias) → 보드 분업 확정(division.confirmed WS·422 message 표시) → 내 문서 저장(1초 디바운스, revisions) → 보내기(note) → 동료 문서 받기(FakeAgentRunner가 보내는 고정 문서)·열기(opens)·답글(reply_to_doc) → 최종본 가져오기(version null 포함)·편집 → 제출 → reporting(deadline_at·5분 카운트·재접속) → 보고 → completed → 디브리핑(최종본·설문 POST) → 관리자 리포트(draft, 조정·메모·검토 완료·final·메모 추가) → 전체 기록(record_ref 하이라이트) → 삭제 예정일. 6분 테스트 세션(`POST /internal/test/sessions` 또는 seed 옵션)을 쓴다.
2. 재연결: WS 끊김(3초 재접속·/state 갱신·connection_gaps), 4401 → resume, session.replaced(4000) 오버레이, reporting 재입장.
3. mock 가정 제거: 보고 감지는 서버 분류(kind=report)이므로 화면은 session.reporting·session.ended 프레임만 따른다. "공개됨" 칩은 document.released 프레임·State로 판정(문장 파싱 제거). 회사 문서 제목은 catalog/State 값. active_runs 복원 확인.
4. 어시스턴트: FakeAssistantRunner 응답 표시·복사·60회 429 안내.
5. `mocks/fixtures/`를 main `tests/fixtures/contracts/`와 값까지 같게 다시 복사(web 전용 2개 제외).

## 완료 기준 (docs/plan.md M2 web-integrate 행)
실 API로 **문서 공유 → 열람 → 통합 → 제출 → 보고 → 리포트 → 전체 기록**까지 한 세션이 화면에서 돈다: 연결 스크립트 1개가 위 1~4를 순서대로 수행하고 단계별 스크린샷(`apps/web/e2e/shots/`, git 무시)과 응답 로그를 남김. 재연결 3종이 스크립트로 확인됨. `pnpm test`·`pnpm lint`·`npx next build`(MOCK 없이) 통과, 루트 `make lint`. 끝나면 모든 앱 프로세스 종료.

## 2라운드 (agent-session·agent-assistant 병합 뒤, 별도 지시로)
`AGENT_RUNNER=session`·`ASSISTANT_RUNNER=graph`로 같은 스크립트를 다시 돌려 "실제 한 세션" 인수(동료 문서 실제 생성·카드 7장·관찰·리포트 근거).

## 보고
`docs/handoff/reports/web-integrate-report.md`: 기준 커밋, 완료 기준 줄별 명령·결과·검증 방식(실 API/격리 DB), 연결 스크립트 경로·실행법, 수정 파일, 계약·픽스처와 다른 실제 응답(변경 요청, api 담당 지정 요청), 남은 문제, 다른 트랙에 알릴 것(e2e-runner: 화면 단계와 API 호출 순서, agent-session: 화면이 기대하는 메시지·문서 타이밍), 2라운드에서 확인할 목록. 마지막 응답은 경로 한 줄.
