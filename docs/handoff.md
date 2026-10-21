# 오케스트레이터 핸드오프

다음 오케스트레이터(에이전트 세션, **다른 로컬 머신일 수 있음**)가 이어가기 위한 상태 기록이다. 읽는 순서: 이 문서 → `AGENTS.md` → `docs/README.md`(문서 색인과 정본 표) → `docs/plan.md` → `docs/dev-process.md`.

## 현재 상태 (2026-10-21, 토론형 전환)

- **방향 전환**: 과제를 "AI 동료와 2시간 업무 하루"에서 **"지원자 + AI 동료 3명의 채팅 토론으로 키워드 → 문제 상황 → 해결책을 합의하고 기획안을 제출하는 60분 세션"**으로 바꿨다. 정본 `docs/handoff/briefs/brief-debate-pivot.md`(맨 아래 "리뷰 반영 결정" R1~R7 포함), 기록 `docs/decisions.md` "2026-10-21 토론형 전환". 업무 시뮬레이션 시기의 브리프·보고·리뷰·계획은 지웠고 git 33cfe90에 있다.
- **리뷰 반영(R1~R7)**: 요소 5개·페르소나 3명(강한결·윤하람·서지안) 고정, 기업 요소 선택 MVP 제외, 60분 = 10·18·18·14와 데모·e2e 15분 압축, 세션별 메일박스·`generation`, 시간 초과는 api가 결정적으로 채움, 그래프 자극 4종, 칸 `empty | confirmed`, 의도 분류 `confidence`, 어시스턴트 tool-calling. 계획 쪽(R6)은 `docs/plan.md`에 반영: agent-spike 신설(W2~W3), W5-0은 G-C만 기다림(W3와 병렬), W5-1은 api ∥ agent ∥ mcp ∥ report-worker 4트랙(rag-mcp 정리는 be-foundation), G-F stub은 be-foundation 소유 후 인계, `track/debate`는 승인된 기대 실패 목록 허용·main(G-E)은 0, 우선순위 P0~P2, 보고서는 목업 캡처 먼저·G-E 뒤 갱신.
- **진행 중 (W1, G-D)**: `track/debate-docs`(worktree `../Day-0_zaeho.worktrees/debate-docs`, 기준 main 33cfe90)에서 PRD·`docs/` 전체를 토론형으로 고치고 R1~R7을 반영하는 중(미커밋). Codex 리뷰 1차(차단 19·비차단 9) 반영 중.
- **G-U 완료**(2026-10-21, UX 시안 모두 추천안, `docs/frontend/design.md` "UX 결정").
- **W2 선행 결과**: web-kit은 `track/debate`에 병합됨(1d45d28). agent-spike 완료(`track/agent-spike` 7a40d2a, 보고서는 그 브랜치의 `docs/handoff/reports/agent-spike-report.md`). arch-page는 Codex 차단 0으로 통과해 커밋 대기. 보고서 1차본은 `track/arch-page`에 작성됨(14쪽, 그림 7-1~7-5).
- **통합 브랜치 `track/debate` 생성됨**(main 33cfe90, 아직 커밋 없음). web-kit과 contracts(G-C)가 먼저 들어간다.
- **main 코드는 아직 옛 흐름**(보드·문서 주고받기·`reporting`, business-mcp). catalog_version `80517d9fb102c7df`. 마지막 확인: `make test`(api 166·business-mcp 9·rag-mcp 10·report-worker 27·web 13)·`make test-e2e`(mock)·`make lint` 통과. 토론형 코드는 5단계에서 `track/debate`로 바꾼다.
- **다음(순서)**: G-D 병합 → contracts(G-C) → mock-candidate ∥ mock-admin ∥ be-foundation(∥ scenario-catalog). 세부: ① G-D 마무리(리뷰 반영 → grep 정합(plan.md "G-D grep 규칙") → `codex exec` 재리뷰 → 커밋 → main squash 병합 → 사용자 확인) ② C0 worktree 정리(flow·ui-layout, `track/flow` 원격 삭제는 사용자 확인 뒤) ③ W2: arch-page·web-kit rebase·리뷰, contracts(G-C, `tests/expected-failures.txt`), agent-spike ④ W3 mock-candidate ∥ mock-admin → G-M, 빈 자리에 be-foundation(W5-0, G-C 뒤) ⑤ W4 report(목업 캡처) → G-R ⑥ G-F → W5-1~3 → G-E ⑦ 후속 report-refresh·arch-refresh. 트랙별 입력·소유 파일·완료 기준은 `docs/plan.md` 4절, 작업 방식·병합 규칙은 `docs/dev-process.md`.

## 진행 표

| 웨이브 | 트랙 | 상태 | 리뷰 | 병합 커밋 |
|---|---|---|---|---|
| W1 | debate-docs (1·1-1단계, G-D) | 커밋·병합 직전 (3차 리뷰·agent-spike 결과 반영 중) | `codex exec` 재리뷰 | |
| — | C0 worktree·브랜치 정리 | 대기 (G-D 뒤, 원격 삭제는 사용자 확인) | — | |
| W2 | ux-options (G-U) | 완료 (모두 추천안, design.md 반영은 debate-docs) | — | |
| W2 | arch-page (2단계, G-A) | 완료, 커밋 대기 (`track/arch-page`) | `codex exec` 차단 0 | |
| W2 | web-kit | 완료 (`track/debate`에 병합) | 통과 | 1d45d28 |
| W2 | contracts (G-C, 기대 실패 목록) | 대기 (G-D 병합 뒤 다음 순서) | | |
| W2~W3 | agent-spike (G-F 동결 입력, 병합 없음) | 완료 (`track/agent-spike`, 보고서 `docs/handoff/reports/agent-spike-report.md`는 그 브랜치에 있음) | — | 7a40d2a |
| W3 | mock-candidate · mock-admin (G-M) | 대기 (G-C 뒤, be-foundation과 병렬) | | |
| W5-0 | be-foundation (G-F) · scenario-catalog (W3와 병렬 가능) | 대기 (G-C 뒤) | | |
| W4 | report (1차본 → report-fill G-R → report-refresh) | 1차본 작성됨 (`track/arch-page`, 14쪽, 캡처 자리 그림 7-1~7-5). report-fill은 G-M 뒤, report-refresh는 G-E 뒤 | | |
| W5-1 | api · agent · mcp(debate+assessment) · report-worker | 대기 | | |
| W5-2 | web-integrate · e2e | 대기 | | |
| W5-3 | e2e 실 실행 · fix-* · playtest(선택) → G-E | 대기 | | |
| 후속 | report-refresh · arch-refresh | 대기 (G-E 뒤) | | |

## 다른 머신에서 시작하기

1. `git clone` 후 **`infra/.env`를 먼저 만든다(git에 없음).** 사용자가 메모장에 둔 이전 `infra/.env` 전체를 붙여넣는다(OpenAI·LangSmith 키, 64바이트 `JWT_SECRET`, `INTERNAL_TOKEN`, `AGENT_RUNNER=fake`). 없으면 `infra/.env.example`을 복사해 채운다. 토론형부터는 `ASSESSMENT_MCP_TOKEN`·`MODEL_*`도 필요하다(G-F에서 example 갱신). **키 값은 어떤 브리프·로그·대화에도 출력하지 않는다.**
2. `infra/.env.local`: `.env`를 복사해 서비스 호스트명을 `localhost`로, `API_INTERNAL_URL=http://localhost:8001`.
3. 도구: Python 3.12 + `uv`, Node 22 + `pnpm`, Docker, **libpq**(`brew install libpq && brew link --force libpq`), Codex CLI(리뷰). `make infra-up`(postgres·rabbitmq·rag-mcp). rag-mcp 첫 기동 때 BGE-M3(약 2.3GB)를 받는다.
4. 각 서비스 `uv sync`, `apps/web`에서 `pnpm install`, 루트에서 `make test`·`make lint`.
5. worktree마다 `infra/.env`·`.env.local`을 복사한다. 디자인 스킬은 `cd apps/web && npx -y skills@latest add emilkowalski/skills --yes`(git 무시).

옛 흐름 코드(main)를 직접 돌려보는 방법은 33cfe90 판 이 문서의 "직접 서비스 돌려보기"를 본다. 토론형 실행법은 G-E 뒤 README와 이 문서에 다시 쓴다.

## 서브에이전트 브리프 템플릿

```
역할: <트랙> 개발. worktree <절대 경로>, 브랜치 track/<트랙>. 기준 커밋 <main 또는 track/debate 해시>, 계약(G-C) 커밋 <해시>, catalog_version <값>.
받은 것: <선행 산출물·픽스처·동결 인터페이스>. 허용 파일: <plan.md 4절 소유 파일>. 사전 승인된 공용 변경: <목록 또는 없음>. 테스트 격리명: <임시 DB/스키마/큐>. 실제 스택: <사용 안 함 | 사용권 시각>.
읽을 것: AGENTS.md, docs/common/contracts.md, docs/common/<관련>.md, docs/<역할>/design.md, docs/plan.md 해당 행, brief-debate-pivot.md.
범위: plan.md의 <트랙> 행. 소유 밖 파일은 수정하지 않는다. 계약이 바뀌어야 하면 CR 파일을 쓰고 그 분기만 멈춘다.
방식: TDD, happy path 중심(docs/dev-process.md). LLM은 mock. 커밋은 자기 브랜치에만, 한국어 한 문장. 키 값 출력 금지.
완료: 완료 기준 각 줄을 직접 실행해 명령·결과·검증 방식(mock/격리 DB/실 API/실 LLM)을 docs/handoff/reports/<트랙>-report.md에 남긴다(수정 파일, 남은 문제, CR, 다른 트랙에 알릴 것, 후속 인수자에게 넘길 것). 마지막 응답은 보고서 경로 한 줄.
```
