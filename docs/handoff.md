# 오케스트레이터 핸드오프

다음 오케스트레이터(에이전트 세션, **다른 로컬 머신일 수 있음**)가 이어가기 위한 상태 기록이다. 읽는 순서: 이 문서 → `AGENTS.md` → `docs/README.md`(문서 색인과 정본 표) → `docs/plan.md` → `docs/dev-process.md`.

## 현재 상태 (2026-10-21 저녁)

- **main**: 토론형 문서 전체(G-D)와 아키텍처 페이지(G-A), 1차 과제 제출 보고서(`docs/share/report.*`, G-R). 1차 과제 제출이 끝나 **보고서는 다시 고쳐도 된다**(S5 report-refresh). main 코드는 아직 옛 흐름이고 토론형 코드는 통합 브랜치 `track/debate`에 쌓는다.
- **`track/debate` = `e4b91f8`**(push됨): web-kit → contracts(G-C) → scenario-catalog → be-foundation(G-F) → mock-admin → mock-candidate → mcp(도구 13개). 그 위에 있던 WIP 합본 `7e64a02`는 폐기했고 백업 태그 `backup/debate-7e64a02`만 남겼다(참고만, 병합 금지). `work/finish-debate`는 삭제했다.
- **원칙**: MVP 우선. 버그·크래시·명세 불일치만 고치고 최적화·정확도 개선은 "MVP 이후"(`docs/common/harness.md` 끝, `docs/agent/design.md` 끝).
- **개발·리뷰**: Codex 대신 Claude 서브에이전트만. api·agent는 Opus 개발 → Sonnet 리뷰, 나머지는 Sonnet 개발 → Opus 리뷰(`docs/dev-process.md` "작업 방식").

### 트랙 브랜치

| 브랜치 | 상태 | 다음 할 일 |
|---|---|---|
| `track/report-worker` | 완료, `e4b91f8` 위로 rebase(테스트 28개 통과). 리뷰 중 | 리뷰 결정 2건(내부 `assistant_calls`의 `request`·`response` 원문, 내부 `GET /sessions/{id}`의 `position.name`)은 계약에 반영됨. 차단 반영 → 병합 |
| `track/gm-fix` | WIP(`8816d01` → rebase), S2 진행 | 범위는 `docs/plan.md` gm-fix 행(B4~B7, N1·N3·N4·N5·N11·N12·N13). 재캡처 없음 |
| `track/api` | WIP(`c84f337`, 토론형 테스트 없음) | S1 계약 위로 rebase 후 P0 + 테스트 API(`start_at`·`advance`) + 테스트(C1~C4·C6·C8~C10) |
| `track/agent` | WIP(`df673f6`) | rebase 후 P0(최소 경로·의도 분류·guard `allow_exact`·어시스턴트·`LLM_FAKE`·`AGENT_RUNNER` 기본 `session`·temperature 연결) → P1 |
| `track/agent-spike` | 완료(병합 안 함). 보고서 `docs/handoff/reports/agent-spike-report.md`는 이 브랜치에 있음 | — |

### 남은 순서

정본은 `docs/plan.md` 1절. 요약:

```
S1  계약·문서 보완(이 커밋) → Sonnet 리뷰 → main → track/debate에 병합
S2  api ∥ agent ∥ gm-fix ∥ report-worker 리뷰 → 빈 자리에 e2e 러너·대본. 병합: report-worker → gm-fix → api → agent
S3  stage-kit ∥ web-integrate ∥ e2e + stage-e2e
S4  stage-e2e 전 단계 → playtest(파일럿 후 확대, GIF) → all_five 15분 1회 → fix-* → G-E → main 병합(사용자 확인)
S5  report-refresh ∥ arch-refresh
```

- 사용자 검토 대기(급하지 않음): 시나리오 자료 16개 수치·디브리핑·카드·FAQ 문구 초안(`[초안]` 표시).

## 다른 머신에서 시작하기

1. `git clone` 후 **`infra/.env`를 먼저 만든다(git에 없음).** 사용자가 메모장에 둔 이전 `infra/.env` 전체를 붙여넣는다(OpenAI·LangSmith 키, 64바이트 `JWT_SECRET`, `INTERNAL_TOKEN`). 없으면 `infra/.env.example`을 복사해 채운다. 토론형 env 이름은 `MODEL_INTENT`·`MODEL_TURN`·`MODEL_PERSONA`·`MODEL_ASSISTANT`·`MODEL_EVALUATOR`와 `ASSESSMENT_MCP_TOKEN`(임의 문자열)이고, `AGENT_RUNNER=session`(기본값), 단계별 테스트용 `ENABLE_TEST_API=1`·`LLM_FAKE=1`(실제 모델이면 비움)이다. 옛 `MODEL_COLLEAGUE/MANAGER/OBSERVE/REPORT`·`BUSINESS_MCP_URL`은 지운다. **키 값은 어떤 브리프·로그·대화에도 출력하지 않는다.**
2. `infra/.env.local`: `.env`를 복사해 서비스 호스트명을 `localhost`로, `API_INTERNAL_URL=http://localhost:8001`.
3. 도구: Python 3.12 + `uv`, Node 22 + `pnpm`, Docker, **libpq**(`brew install libpq && brew link --force libpq`). `make infra-up`(postgres·rabbitmq·rag-mcp). rag-mcp 첫 기동 때 BGE-M3(약 2.3GB)를 받는다.
4. 각 서비스 `uv sync`, `apps/web`에서 `pnpm install`, 루트에서 `make test`·`make lint`.
5. 브랜치 이어받기: `git fetch origin` 후 `git worktree add ../Day-0_zaeho.worktrees/<트랙> track/<트랙>`(api·agent·gm-fix·report-worker, 통합 확인은 debate). worktree마다 `infra/.env`·`.env.local`을 복사한다. 디자인 스킬은 `cd apps/web && npx -y skills@latest add emilkowalski/skills --yes`(git 무시).

옛 흐름 코드(main)를 직접 돌려보는 방법은 33cfe90 판 이 문서의 "직접 서비스 돌려보기"를 본다. 토론형 스택을 띄워 단계별로 보는 방법은 `docs/dev-process.md` "토론형 스택으로 단계별 확인"이다.

## 서브에이전트 브리프 템플릿

```
역할: <트랙> 개발(모델 <Opus|Sonnet>). worktree <절대 경로>, 브랜치 track/<트랙>. 기준 커밋 <main 또는 track/debate 해시>, 계약(G-C) 커밋 <해시>, catalog_version <값>.
받은 것: <선행 산출물·픽스처·동결 인터페이스>. 허용 파일: <plan.md 4절 소유 파일>. 사전 승인된 공용 변경: <목록 또는 없음>. 테스트 격리명: <임시 DB/스키마/큐>. 실제 스택: <사용 안 함 | 사용권 시각>.
읽을 것: AGENTS.md, docs/common/contracts.md, docs/common/<관련>.md, docs/<역할>/design.md, docs/plan.md 해당 행, brief-debate-pivot.md.
범위: plan.md의 <트랙> 행. 소유 밖 파일은 수정하지 않는다. 계약이 바뀌어야 하면 CR 파일을 쓰고 그 분기만 멈춘다.
방식: TDD, happy path 중심(docs/dev-process.md). LLM은 mock. 커밋은 자기 브랜치에만, 한국어 한 문장. 키 값 출력 금지.
리뷰: 완료 보고 뒤 다른 모델(<Sonnet|Opus>)의 읽기 전용 리뷰 서브에이전트가 차단 항목만 본다. 차단은 같은 개발 에이전트가 반영하고 재리뷰는 1회까지.
완료: 완료 기준 각 줄을 직접 실행해 명령·결과·검증 방식(mock/격리 DB/실 API/실 LLM)을 docs/handoff/reports/<트랙>-report.md에 남긴다(수정 파일, 남은 문제, CR, 다른 트랙에 알릴 것, 후속 인수자에게 넘길 것). 마지막 응답은 보고서 경로 한 줄.
```
