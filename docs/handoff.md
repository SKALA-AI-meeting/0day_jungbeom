# 오케스트레이터 핸드오프

다음 오케스트레이터(에이전트 세션, **다른 로컬 머신일 수 있음**)가 이어가기 위한 상태 기록이다. 읽는 순서: 이 문서 → `AGENTS.md` → `docs/README.md`(문서 색인과 정본 표) → `docs/plan.md` → `docs/dev-process.md`.

## 현재 상태 (2026-10-21 18시, 세션 종료 시점)

- **main (`2742aa3`, push됨)**: 토론형 문서 전체(G-D, `4f5de50`)와 아키텍처 페이지·최종 과제 보고서(G-A·G-R). 보고서 `docs/share/report.pdf`(15쪽, 7장은 목업 캡처)는 **확정본**이다. 사용자 결정으로 본 개발 뒤에도 보고서는 다시 고치지 않는다(report-refresh 없음).
- **main 코드는 아직 옛 흐름**이다. 토론형 코드는 통합 브랜치 `track/debate`에 쌓고 있다.
- **원칙**: MVP 우선. 버그·크래시·명세 불일치만 고치고 최적화·정확도 개선은 "MVP 이후"(`docs/common/harness.md` 끝, `docs/agent/design.md` 끝).

### 통합 브랜치 `track/debate` (push됨)

들어간 것(순서): web-kit → contracts(G-C, 픽스처 87개·형태 테스트 97개) → scenario-catalog(`scenarios/missions/debate/`, 카탈로그 검사 28개) → be-foundation(G-F: 스키마 25테이블·모델·ports·G-F stub·debate-mcp 이름 변경·rag-mcp 정리·assessment-mcp 골격·compose 8개·Makefile·env 이름) → mock-admin → mock-candidate(웹 테스트 35개·빌드 통과, 캡처 `tests/e2e/records/mock-ui-*`) → mcp(도구 13개, Codex 차단 0).

### 트랙 브랜치 (모두 push됨, 아직 `track/debate`에 안 들어감)

| 브랜치 | 상태 | 다음 할 일 |
|---|---|---|
| `track/report-worker` | 완료, 테스트 28개 통과(`9fd7703`). Codex 리뷰 전 | 리뷰 → `track/debate` 병합. 확인 사항: compose report-worker에 `../scenarios:/scenarios:ro` 마운트, api `GET /internal/sessions/{id}/evaluations?run_id=` 없음=404, Report `position.name` 출처, ai_usage 인용 출처 |
| `track/api` | **WIP**(`c84f337`, 중간 커밋, 테스트 미완). admin router 작성 중에 멈춤 | 이어서 P0 완료 → 테스트 → 리뷰. 추가 결정: State에 `keyword_options[{option_key,label}]`, 내부 messages `tail=N`(최근 N개 오래된 순)·토론방만, 내부 `GET /rubric`(cards[].window 포함), 409 `error.code`에 세부 코드 |
| `track/agent` | **WIP**(`df673f6`, 테스트 fake 작성 중에 멈춤) | 이어서 P0(최소 경로·의도 분류·guard `allow_exact`·어시스턴트) → P1. `ROLE_CONFIG.temperature`를 make_llm에 연결 |
| `track/gm-fix` | **WIP**(`8816d01`, 목업 UI/UX 리뷰 차단 7건 수정 중) | 리뷰 `docs/handoff/reviews/gm-uiux-review.md`(이 핸드오프와 함께 추가) 기준으로 마무리. 보고서용 재캡처는 불필요 |
| `track/agent-spike` | 완료(병합 안 함). 보고서 `docs/handoff/reports/agent-spike-report.md`는 이 브랜치에 있음 | — |

### 남은 순서

1. api·agent WIP 이어서 완료 → 각 리뷰(`codex exec`, 막히면 Claude 읽기 전용 리뷰) → `track/debate` 병합. report-worker·gm-fix도 리뷰 후 병합.
2. W5-2: web-integrate(목업 → 실 api 연결) ∥ e2e 러너·대본.
3. W5-3: 15분 실 스택 `all_five` 1회(필수) → fix → G-E(main 실패 0) → `track/debate`를 main에 squash 병합(사용자 확인).
4. 계약 문서 보완(작은 정리): Report.review = `{reviewer_name, reviewed_at}`, State `keyword_options`, 내부 `tail`·`/rubric`, rubric.md 1.2 표 `MODEL_REPORT` → `MODEL_EVALUATOR`.
5. 사용자 검토 대기(급하지 않음): 시나리오 자료 16개 수치·디브리핑·카드·FAQ 문구 초안(`[초안]` 표시).

## 다른 머신에서 시작하기

1. `git clone` 후 **`infra/.env`를 먼저 만든다(git에 없음).** 사용자가 메모장에 둔 이전 `infra/.env` 전체를 붙여넣는다(OpenAI·LangSmith 키, 64바이트 `JWT_SECRET`, `INTERNAL_TOKEN`, `AGENT_RUNNER=fake`). 없으면 `infra/.env.example`을 복사해 채운다. 토론형 env 이름은 `MODEL_INTENT`·`MODEL_TURN`·`MODEL_PERSONA`·`MODEL_ASSISTANT`·`MODEL_EVALUATOR`와 `ASSESSMENT_MCP_TOKEN`(임의 문자열)이다. 옛 `MODEL_COLLEAGUE/MANAGER/OBSERVE/REPORT`·`BUSINESS_MCP_URL`은 지운다. **키 값은 어떤 브리프·로그·대화에도 출력하지 않는다.**
2. `infra/.env.local`: `.env`를 복사해 서비스 호스트명을 `localhost`로, `API_INTERNAL_URL=http://localhost:8001`.
3. 도구: Python 3.12 + `uv`, Node 22 + `pnpm`, Docker, **libpq**(`brew install libpq && brew link --force libpq`), Codex CLI(리뷰). `make infra-up`(postgres·rabbitmq·rag-mcp). rag-mcp 첫 기동 때 BGE-M3(약 2.3GB)를 받는다.
4. 각 서비스 `uv sync`, `apps/web`에서 `pnpm install`, 루트에서 `make test`·`make lint`.
5. 브랜치 이어받기: `git fetch origin` 후 `git worktree add ../Day-0_zaeho.worktrees/<트랙> track/<트랙>`(api·agent·gm-fix·report-worker·debate). worktree마다 `infra/.env`·`.env.local`을 복사한다. 디자인 스킬은 `cd apps/web && npx -y skills@latest add emilkowalski/skills --yes`(git 무시).

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
