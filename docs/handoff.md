# 오케스트레이터 핸드오프

다음 오케스트레이터(에이전트 세션, **다른 로컬 머신일 수 있음**)가 이 문서만 읽고 바로 이어가기 위한 상태 기록이다. 읽는 순서: 이 문서 → `AGENTS.md` → `docs/plan.md` → `docs/dev-process.md` → `docs/decisions.md`의 2026-10-20 절들 → 필요한 역할 문서.

## 현재 상태 (2026-10-20 저녁)

- **W0·W1·W2 전부 병합 완료, W3의 1단계 agent-min까지 병합 완료.** main 최신은 `git log`로 확인. 테스트: api 82, business-mcp 11, rag-mcp 10, report-worker 17, web 16 통과. `make lint` 통과.
- 모든 트랙은 Codex 리뷰(gpt-6.1-sol high) → 수정 → rebase → `make test`·`make lint` → squash 병합을 거쳤다. 트랙별 브리프·보고서·리뷰 원문은 **`docs/handoff/{briefs,reports,reviews}/`** 에 있다(다른 머신에서도 읽을 수 있게 저장소에 넣음).
- 열린 worktree·pane·탭 없음. 다음 세션은 깨끗한 main에서 시작한다.
- 팀 공유 문서: `docs/share/architecture.html`, `docs/share/plan-report.html|pdf`.

## 다른 머신에서 시작하기

1. `git clone` 후 **`infra/.env`를 먼저 만든다. 이 파일은 git에 없다.** 사용자가 이전 머신의 `infra/.env` 전체 내용을 메모장에 복사해 두었으니, 새 머신에서 `infra/.env`에 그대로 붙여넣는다(OpenAI·LangSmith 키, 64바이트 `JWT_SECRET`, `INTERNAL_TOKEN`, `AGENT_RUNNER=fake` 포함). 메모장 사본이 없으면 `infra/.env.example`을 복사해 키를 직접 채운다. **키 값은 어떤 pane 브리프·로그·대화에도 출력하지 않는다.**
2. `infra/.env.local`을 만든다: `.env`를 복사해 호스트명 `postgres`·`rabbitmq`·`api`·`business-mcp`·`rag-mcp`를 `localhost`로 바꾼 것. `API_INTERNAL_URL=http://localhost:8001`, `AGENT_RUNNER=fake`(실제 그래프를 쓰려면 `session`).
3. 도구: Python 3.12 + `uv`, Node 22 + `pnpm`, Docker. `make infra-up`(postgres·rabbitmq·rag-mcp만 docker). rag-mcp 이미지는 3.4GB이고 첫 기동 때 BGE-M3(약 2.3GB)를 `/models` 볼륨에 받는다.
4. 각 서비스에서 `uv sync`, `apps/web`에서 `pnpm install`. 루트에서 `make test`·`make lint`가 통과하는지 확인한다(공용 postgres·rabbitmq가 떠 있어야 api·worker 테스트가 돈다).
5. worktree마다 `infra/.env`·`.env.local`을 복사해 줘야 한다(git 무시 파일이라 worktree에 없다).
6. Herdr를 쓴다면 `~/.claude/skills/herdr-dispatch`와 `~/.agents/skills/herdr`가 있어야 한다. 없으면 pane 대신 일반 터미널·에이전트로 같은 절차를 따른다.

## 다음 행동 (W3 나머지 → W4)

파도 표(`docs/plan.md`)대로 동시 4개까지. 트랙마다 worktree + 탭(작업 pane + 리뷰 pane).

1. **agent-session M2** (브랜치 `track/agent-session` 새로 생성, 전 단계 agent-min의 구조 메모는 `docs/handoff/reports/agent-min-report.md` "다음 라운드를 위해 정한 구조" 절). 범위: 전이표 전체(kickoff→negotiate→work→review→submit→done), kickoff 분업 제안·재지시 1회 제한, draft_part(texture)·review 완성본·respect 위반 삽입·fix_part, observe(창 계산·규칙 지표·레이블 분류·`metrics.window_missed {value, evidence_ids}`·aux null→classify_failed), 복구(LLM 실패 3회→세션 failed), work_notes. 반드시 넣을 것: **미공개 문서 판정을 코드가 결정적으로**(agent-min live 실패 원인: 모델이 get_document를 안 불러 짐작 답변), 책임감 observe 입력에 `release_at`·`released_before_message`(prompts 결정), report_request는 창을 닫지 않음.
2. **agent-assistant** (agent-min 병합됐으므로 시작 가능): `app/agent/assistant/`, `POST /sessions/{id}/assistant`(api-candidate 라우터 소유라 소유권 예외 승인 필요, 응답 `{call_id, message_id, content, cited_docs}`, 429 `assistant_limit`), 공개 문서만 인용, assistant_calls·response_message_id 저장 순서(reuse 계산 전제).
3. **web-polish**: `components/ui/` 내부·globals.css 소유권 이관. 좁은 화면, 메시지 도착 스크롤, 모션 4종, break-ui. worker 보고의 "items[].minutes null이면 빈칸" 수정도 여기서.
4. **e2e-runner**: `tests/e2e/`, `scenarios/e2e/*.yaml`, `scripts/make_session.py`. 보고서들의 "e2e-runner에 알릴 것" 절을 모아 대본에 반영. 통합 스택은 한 번에 하나.
5. **W4 docs-final** + 파일럿.

### 미처리 변경 요청(오케스트레이터 결정 필요, 보고서 "변경 요청" 절 참조)
- agent-min: 분류 저장용 MCP 도구 추가 또는 프로세스 안 DB 직접 저장 인정(지금은 직접 저장); `app/run.py` 기동 시 runner 초기화·종료 시 aclose; harness.md의 `langchain-mcp-adapters` 문구 정정(직접 만든 McpClient 사용); contracts.md 허용 목록 표에 페르소나별 분리(팀장은 get_board·get_document_state만); design.md State "16필드" 표기(실제 17).
- web-office: State에 파트 제목·`virtual_company`·`session_id` 추가(M2 api 보강으로 미룸), `lib/api.ts`의 미사용 `idempotencyKey` 제거(foundation).
- worker: 섹션 `card_t_min` 추가 여부.
- 공통: `tests/conftest.py`·`services/api/tests/conftest.py`는 foundation 소유로 확정됨. pyproject·lock의 트랙별 변경은 승인 후 decisions.md에 기록.

## pane 브리프 템플릿

```
역할: <트랙 이름> 개발. worktree <경로>, 브랜치 track/<이름>.
읽을 것: AGENTS.md, docs/common/contracts.md, docs/common/<관련>.md, docs/<역할>/design.md, docs/plan.md의 소유권·완료 기준, docs/decisions.md 2026-10-20 절, docs/handoff/reports/*의 "다른 트랙에 알릴 것".
범위: docs/plan.md의 <트랙> 행. 소유권 밖 파일은 수정하지 않는다. 계약이 바뀌어야 하면 "변경 요청"으로 보고하고 계속 진행한다.
방식: TDD, happy path 중심(docs/dev-process.md). LLM은 mock. 커밋은 자기 브랜치에만. 키 값 출력 금지.
완료: 완료 기준의 각 줄을 직접 실행해 명령과 결과를 보고한다. 파일 수정 목록, 남은 문제, 변경 요청, 다른 트랙에 알릴 것을 Markdown 파일로 저장하고 마지막 응답은 경로 한 줄.
```

실제로 쓴 브리프 전부가 `docs/handoff/briefs/`에 있으니 다음 트랙 브리프는 그 형식을 따른다(수정 라운드 브리프는 `brief-<트랙>-fix.md`, 리뷰 브리프는 `reviews/review-<트랙>-brief.md`).

## Herdr 운영 규칙 (사용자 결정)

- **트랙마다 탭 하나** (`herdr tab create --workspace $HERDR_WORKSPACE_ID --cwd <worktree> --label <트랙>`). 루트 pane의 쉘이 홈에서 열리는 경우가 있으니 `herdr pane run <pane> "cd <worktree>"` 뒤에 `agent start`. 같은 탭 오른쪽에 리뷰 pane. 병합되면 탭째 닫는다. 오케스트레이터 탭에 pane을 늘리지 않는다.
- 개발 pane: Claude(`--permission-mode auto`; 구현 sonnet/medium, 어려운 것 opus/high). 리뷰 pane: Codex `-m gpt-6.1-sol -c model_reasoning_effort=high -s workspace-write -a never -c features.fast_mode=false`. read-only 샌드박스면 파일 저장이 막히고 좁은 pane 출력은 회수가 안 되므로 workspace-write로 띄우고 **결과를 worktree의 `REVIEW.md`(추적 안 함, 병합 전 삭제)에 쓰게 한다.** 리뷰 프롬프트에 "소스 수정·git 변경·외부 게시 금지"를 적는다.
- `codex exec` 백그라운드는 사용자가 원치 않는다(보이는 pane으로). 꼭 쓰면 `</dev/null` 필수.
- Claude pane은 처음 보는 폴더에서 신뢰 확인에 멈춘다. 긴 출력은 파일로 저장시킨다. `herdr agent prompt --wait`는 타임아웃이 나도 보통 전달돼 있으니 `agent get`으로 확인한다.
- Claude 한도 소진 시 개발을 Codex(gpt-6.1-sol, 편집 모드)로, 리뷰를 다른 모델(gpt-6-astra 또는 Claude 복구 후)로 바꾼다. 같은 모델이 만들고 검토하지 않는다.
- 병합: 오케스트레이터가 `git rebase main`(decisions.md 끝에 절이 겹치면 양쪽 유지) → `make test`·`make lint` → `main`에 squash → push → `sh scripts/worktree.sh --remove <트랙>` → 브랜치 삭제 → 탭 닫기 → 이 문서 진행 표 갱신.

## 리뷰 상태

| 리뷰 | 결과 |
|---|---|
| 설계 리뷰 5라운드(Codex 4, Claude UX 1) | 전부 반영, 커밋 7512022 이전 |
| 구현 트랙 10개(W0 1, W1 4, W2 4, W3 agent-min 1) | 각 1회 Codex 리뷰 + 수정 라운드 반영 후 병합. 리뷰 원문 `docs/handoff/reviews/` |

## 진행 표

| 파도 | 트랙 | 상태 | 리뷰 | 병합 커밋 |
|---|---|---|---|---|
| W0 | foundation | 병합 완료 | Codex 차단 5·권장 5 반영 | c9fa550 |
| W1 | prompts | 병합 완료 | Codex 차단 4 반영 | fb963e0 |
| W1 | api-admin | 병합 완료 | Codex 차단 6 반영 | 9447848 |
| W1 | api-candidate | 병합 완료 | Codex 차단 7 반영 | a5514d9 |
| W1 | business-mcp | 병합 완료 | Codex 차단 1·권장 1 반영 | 502b88b |
| W2 | rag-mcp | 병합 완료 | Codex 차단 1 반영 | 5c96986 |
| W2 | web-admin | 병합 완료 | Codex 차단 7 반영 | 6ee6a2a |
| W2 | web-office | 병합 완료 | Codex 차단 6 반영 | 3d5eb65 |
| W2 | worker | 병합 완료 | Codex 차단 7 반영 | 2ed126f |
| W3 | agent-min (agent-session 1단계) | 병합 완료 | Codex 4건 반영, live 1회 실패(M2에서 해결) | 07f82f3 |
| W3 | agent-session M2 | 대기 | | |
| W3 | agent-assistant | 대기 | | |
| W3 | web-polish | 대기 | | |
| W3 | e2e-runner | 대기 | | |
| W4 | docs-final | 대기 | | |
| 공유 | docs-share | 병합 완료 (docs/share) | — | 72a9400 |

## 결정 요약 (자세한 것은 docs/decisions.md)

요소 선택은 채용 건 단위 1~4개. 지원자는 리드(분업 결정·재지시·보고). 동료는 회사 인재상 페르소나(성향 자유 + 의무 카드 + 선점 금지, 카탈로그 `persona`). 평가표는 요소당 4항목, AI 분류를 입력으로 규칙이 1/0/기록 없음 산출, 담당자가 조정해 확정(`docs/common/rubric.md`). 리포트는 산출물 + 관찰·평가표 + AI 활용. 에이전트는 api 모듈(`app/agent/`), 작업 기억 `work_notes`, 중간 초안 texture. 관찰 창은 다음 요소 카드까지(흐름 카드는 닫지 않음, 마지막 창은 제출까지). Recovery는 재시도 2회 후 폴백, 대체 모델 없음. 사람 승인은 리포트 그래프 interrupt. 시계는 접속과 무관. 임베딩 BGE-M3 로컬. Idempotency-Key는 MVP 계약에서 제외(도메인 멱등만). tasks 행은 내부 division PUT이 생성. 디브리핑 기한은 종료 +7일. 시작 공개 문서는 start()가 즉시 공개. 리포트 JSON 형태(aux_facts string[], context.prev_persona_message 문자열, items[].minutes, ai_usage category)는 worker 산출 기준. MVP 제외 목록은 plan.md. 동시 pane 4개, 인프라만 docker.
