# 오케스트레이터 핸드오프

다음 오케스트레이터(에이전트 세션, **다른 로컬 머신일 수 있음**)가 이 문서만 읽고 바로 이어가기 위한 상태 기록이다. 읽는 순서: 이 문서 → `AGENTS.md` → `docs/plan.md` → `docs/dev-process.md` → `docs/decisions.md`의 2026-10-20 절들 → 필요한 역할 문서.

## 현재 상태 (2026-10-21 새벽, P0 완료·개발 직전)

- **코드**: W0·W1·W2와 agent-min까지 main에 병합(코드는 아직 **옛 설계**: 요소 4개·공유 문서·`scenarios/catalog.yaml`). 테스트 api 82, business-mcp 11, rag-mcp 10, report-worker 17, web 16 통과, `make lint` 통과.
- **기획·설계 전환(P0) 완료**: 2026-10-20 사용자가 초점을 "같이 일하기 좋은 사람인가"로 재정의. 인성 5요소(책임감/성실성, 계획성/꼼꼼함, 적응성/유연성, 협업/조율, 정직/공정한 보고), 요소당 카드 최대 2장(7장), **문서 주고받기** 협업 모델(각자 문서를 보내고 받아 열어 보고 피드백, 주담당이 최종본 통합), 미션 단위 카탈로그, 호칭 "주담당", 제출 → 팀장 보고 → 종료, 관리자 생성 화면은 요소 뜻만, 전체 기록 화면·근거→기록 링크, 샘플 리포트·인쇄, AI 활용 라벨 없음. PRD·docs/common·서비스 설계·프론트 문서·계획·결정 전부 반영됐고 **개발 전 리뷰 4종**(Codex 설계·계획, Claude 지원자·담당자 관점)을 반영했다. 브랜치 `track/redesign-docs`를 main에 병합한 커밋: 960981e.
- **정본**: 기획 PRD.md → 설계 docs/common(이름은 `contracts.md`가 정본, 고정됨) → 역할 문서. 전환의 배경·결정은 `docs/prd-change-proposals.md` 재설계 절, `docs/decisions.md` 2026-10-20 절들, 리뷰 반영 지시서 `docs/handoff/reviews/review-redesign-triage.md`, 계획 리뷰 `review-plan.md`.
- **P0 마무리는 Claude Opus가 마무리·병합 완료**(2026-10-21, `docs/handoff/briefs/brief-p0-finish.md`): 공용 픽스처 `tests/fixtures/contracts/`를 contracts.md 최종본과 검수해 커밋하고 main에 squash 병합했다. 깨지는 기존 테스트는 `services/api/tests/test_candidate.py` 1개(옛 State 키)이며 목록·contracts 어긋남 4건·`make lint`의 로컬 `apps/web/.agents/` prettier 경고는 `docs/handoff/reports/fixtures-align-report.md`에 있다. 테스트는 scenario-redesign이 코드와 함께 고친다.
- **열린 worktree·탭 없음.** 이 머신의 Herdr 탭 "review-redesign"은 P0에서 닫았다. mock 서버(`apps/web`, 3000 포트)가 떠 있을 수 있으니 `lsof -ti:3000 -sTCP:LISTEN | xargs kill`로 정리한다.
- **사용자가 채울 것**: `infra/.env`·`.env.local`의 `OPENAI_API_KEY_PERSONAL`, `GEMINI_API_KEY`(역할별 `MODEL_*`는 비워 둠, 상향 규칙은 decisions.md).

## 다른 머신에서 시작하기

1. `git clone` 후 **`infra/.env`를 먼저 만든다. 이 파일은 git에 없다.** 사용자가 이전 머신의 `infra/.env` 전체 내용을 메모장에 복사해 두었으니, 새 머신에서 `infra/.env`에 그대로 붙여넣는다(OpenAI·LangSmith 키, 64바이트 `JWT_SECRET`, `INTERNAL_TOKEN`, `AGENT_RUNNER=fake` 포함). 메모장 사본이 없으면 `infra/.env.example`을 복사해 키를 직접 채운다. **키 값은 어떤 pane 브리프·로그·대화에도 출력하지 않는다.**
2. `infra/.env.local`을 만든다: `.env`를 복사해 호스트명 `postgres`·`rabbitmq`·`api`·`business-mcp`·`rag-mcp`를 `localhost`로 바꾼 것. `API_INTERNAL_URL=http://localhost:8001`, `AGENT_RUNNER=fake`(실제 그래프를 쓰려면 `session`).
3. 도구: Python 3.12 + `uv`, Node 22 + `pnpm`, Docker, **libpq**(`brew install libpq && brew link --force libpq`, 없으면 api 테스트가 psycopg import에서 전부 실패). `make infra-up`(postgres·rabbitmq·rag-mcp만 docker). rag-mcp 이미지는 3.4GB이고 첫 기동 때 BGE-M3(약 2.3GB)를 `/models` 볼륨에 받는다.
4. 각 서비스에서 `uv sync`, `apps/web`에서 `pnpm install`. 루트에서 `make test`·`make lint`가 통과하는지 확인한다(공용 postgres·rabbitmq가 떠 있어야 api·worker 테스트가 돈다).
5. worktree마다 `infra/.env`·`.env.local`을 복사해 줘야 한다(git 무시 파일이라 worktree에 없다).
6. Herdr를 쓴다면 `~/.agents/skills/herdr`와 플러그인 `dev@horang-skills`(herdr-dispatch 포함, 마켓플레이스 `zaehorang/horang-skills` GitHub 소스)가 있어야 한다. 디자인 스킬은 `cd apps/web && npx -y skills@latest add emilkowalski/skills --yes`(git 무시).

## 직접 서비스 돌려보기 (다른 머신에서, P3 병합 뒤)

1. 인프라: `make infra-up`(postgres·rabbitmq·rag-mcp. 첫 기동은 이미지 빌드 + BGE-M3 다운로드로 오래 걸림).
2. 공용 DB 스키마가 비어 있으면 적용: `docker exec -i infra-postgres-1 psql -U dayzero -d dayzero -v ON_ERROR_STOP=1 -q < infra/db/schema.sql`(DB 사용자는 `.env`의 DATABASE_URL 사용자).
3. 앱 4개를 각자 터미널에서(worktree 아니라 main 체크아웃, `infra/.env.local`을 읽음):
   ```
   cd services/api && AGENT_RUNNER=session ASSISTANT_RUNNER=graph ENABLE_TEST_API=1 uv run python -m app.run
   cd services/business-mcp && uv run python -m business_mcp
   cd services/report-worker && uv run python -m report_worker
   cd apps/web && pnpm dev          # http://localhost:3000 (NEXT_PUBLIC_MOCK 없이)
   ```
4. `make seed` → 채용 건·회사 문서 색인(indexed > 0, catalog_version 확인).
5. **120분 정식 세션**: http://localhost:3000/admin 가입·로그인 → 채용 건 생성 → 초대 → 링크를 다른 브라우저(시크릿 창)로 열어 지원자 진행.
6. **6분 짧은 세션**(내부 테스트 API, `ENABLE_TEST_API=1` 필요):
   ```
   python scripts/make_session.py --minutes 6 --elements responsibility,planning,adaptability,collaboration,honesty
   ```
   출력의 `invite_token`으로 http://localhost:3000/s/<invite_token> 입장, `admin_email`로 관리자 로그인(비밀번호는 스크립트 고정값 `e2e-password-1234`, `scripts/make_session.py`의 PASSWORD)하면 그 세션의 리포트·전체 기록이 보인다. 카드 7장은 120분 비율로 6분에 압축돼 나온다(분업 0.5분, 도움 1.5분, 중간 점검 2.25분, 지연 3분·공개 3.5분, 변경 3.75분, 리뷰 4.5분, 보고 요청 5.5분).
7. 브라우저 자동 한 세션: `cd apps/web && node e2e/session.mjs`(스크린샷 `apps/web/e2e/shots/`). 대본 e2e: `make test-e2e`(mock) / 실 스택은 `tests/e2e/README.md`.
8. 끝나면 네 앱 종료: `lsof -ti:8000,8001,9101,3000 -sTCP:LISTEN | xargs kill; pkill -f report_worker`.

## 다음 행동: P1 개발 시작 (사용자 승인 뒤)

사용자가 "P0까지 끝내고 멈춰라"고 했으므로 **P1은 사용자가 시작하라고 할 때** 띄운다. 파도·소유권·관문은 `docs/plan.md`(P0~P5 표, 테스트 6건 배정, 공용 파일 담당), 절차는 `docs/dev-process.md`, 체크리스트는 아래 "오케스트레이터 체크리스트".

### P1 기동 절차
1. **브리프 2개 작성** → `docs/handoff/briefs/brief-web-redesign.md`, `brief-scenario-redesign.md`. 아래 템플릿대로 기준 커밋(main 최신), 계약 커밋(같은 값), catalog_version(scenario가 새로 발급), 허용 파일(plan.md 소유권 행), 사전 승인 공용 변경, 테스트 격리명, 검증 방식을 적는다. 읽을 것에 반드시: AGENTS.md, PRD.md, `docs/common/contracts.md`·`scenario-model.md`·`rubric.md`·`data-model.md`, 역할 문서(`docs/frontend/design-direction.md`·`design-system.md`·`design.md` / `docs/api/design.md`·`mcp`·`worker-infra`·`agent`), `docs/handoff/reviews/review-redesign-triage.md`, `review-plan.md` 3·4절, `docs/handoff/reports/fixtures-align-report.md`.
2. **worktree 2개**: `sh scripts/worktree.sh web-redesign`, `sh scripts/worktree.sh scenario-redesign`. 각 worktree에 `infra/.env`·`.env.local` 복사.
3. **탭 2개**(트랙마다 하나): `herdr tab create --workspace $HERDR_WORKSPACE_ID --cwd <worktree> --label <트랙>` → 루트 pane에 `herdr pane run <pane> "cd <worktree>"` → `herdr agent start <트랙> --kind claude --pane <pane> -- --permission-mode auto`(폴더 신뢰 확인에 멈추면 `agent send-keys enter`) → `herdr agent prompt <트랙> "<브리프 경로>를 읽고 시작"`. 리뷰 pane은 같은 탭 오른쪽에 `pane split --direction right`로 만들고 Codex(`-m gpt-6.1-sol -c model_reasoning_effort=high -s workspace-write -a never -c features.fast_mode=false`)를 띄워 완료 보고 뒤 리뷰 브리프를 보낸다. 결과는 worktree의 `REVIEW.md`.
4. **web-redesign 관문**: 구현 완료 → UI/UX 전문가 페르소나 리뷰(Claude Opus 서브에이전트 또는 pane, 실제 mock 화면·스크린샷, 결과 `docs/handoff/reviews/review-uiux-view.md`) → 반영 → Codex 리뷰 → 반영 → **사용자가 `NEXT_PUBLIC_MOCK=1 pnpm dev`로 확인**(http://localhost:3000/s/live, 관리자는 아무 이메일·비밀번호) → 피드백 반영 → 병합. 사용자 확인을 기다리는 동안 scenario-redesign은 계속한다.
5. **scenario-redesign 관문**: 내부 관문 3개(미션·스키마 → API·도구 계약 검증 → 워커·픽스처 인수)마다 중간 보고 → Codex 리뷰 → `make test`·`make lint` → 병합. 병합 시 catalog_version·7카드 레이블·fixed_opinions·선점/팀장 DM 픽스처·대본 초기본을 인수하고 `scenarios/missions/` 문구는 prompts, `scenarios/e2e/`는 e2e-runner로 소유권 반환(P1 관문).
6. 둘 다 병합되고 사용자 mock 확인이 끝나면 P2(agent-session ∥ agent-assistant ∥ web-integrate ∥ web-polish).

### 이전 라운드의 미처리 변경 요청 (재설계로 정리됨)
- 해결됨: 분류 저장 도구(`record_observation`·`update_observation`으로 계약화), 팀장 허용 목록(contracts), State 필드 수(18), harness의 MCP 클라이언트 문구(직접 만든 McpClient), worker `card_t_min`(카드 소섹션에 카드 시각 포함).
- scenario-redesign이 맡음: `app/run.py` 기동 시 runner 초기화·종료 시 aclose, `tests/conftest.py`·`services/api/tests/conftest.py` 갱신(공용 변경 담당 1명 지정).
- web-redesign이 맡음: `lib/api.ts`의 미사용 `idempotencyKey` 제거, State의 파트 제목·`virtual_company`·`session_id`(contracts의 새 State 형태로 해결).

## P1 진행 중 결정·변경 요청 (2026-10-21)

- **사용자 결정(2026-10-21 새벽): P1에서 멈추지 않고 P5까지 연속 진행한다.** 사용자 mock 확인 관문은 건너뛰고(나중에 한꺼번에 수정), web은 UI/UX 리뷰 → Codex 리뷰 → 병합. P2 착수 조건에서 '사용자 mock 확인'을 뺀다. Claude 한도가 부족하면 작업을 정리하고 다음 리셋 때 이어간다. 작업 단위마다 main에 병합·커밋해도 된다.

- web-redesign 완료 보고(8cdf03b) 변경 요청 처리: ① 시작 직후 `state_start.json`·② 묶음 5종 `admin_candidates.json` 보강(sess-4~8)·⑥ `GET /admin/catalog` missions[].documents {doc_id,title} 추가 → scenario-redesign이 관문 2 뒤 반영(계약은 c9b956d 이후 커밋에 반영됨). ③ 묶음 정의는 design.md 쪽(확정 중은 "완료")으로 data-model.md를 고침. ④ import의 내 문서 미전송 버전은 `version: null`. ⑤ no_record_reason 6종 픽스처는 보류. ⑦ `.prettierignore`에 `mocks/fixtures` 허용. 긴 최종본 섹션 접기는 사용자 승인(접음, 인쇄는 펼침). 사용자 결정: 요소 카드 문구(meaning·how_we_see·if_unselected)와 화면 라벨은 설명조가 아니라 프로덕트 UI 말투(명사형·간결·상황 비공개)로 — scenario가 카탈로그·픽스처, web이 라벨.
- scenario-redesign 관문 1 리뷰 반영: basis `by_source`(contracts), FAQ 4+2문항(admin_catalog.json 수정 사전 승인), PRD 분량 1~2쪽(b9e9763).

## P2 진행 중 모인 api 수준 변경 요청 (오케스트레이터가 P2 병합 뒤 fix 트랙 또는 e2e에서 처리)

- 어시스턴트 라우터(`app/routers/candidate.py`): 요청 메시지 저장 전 `app.masking.mask`, 60회 카운트 조회→INSERT 직렬화(agent-assistant Codex 리뷰).
- `app/run.py`: `ctx.assistant` warm-up(`graph()`)·종료 시 `aclose()`(agent-assistant 보고서). 체크포인터 setup의 `CREATE INDEX CONCURRENTLY`가 열린 트랜잭션에 막힐 수 있어 기동 시 먼저 수행.
- MODEL_ASSISTANT 역할별 생성 함수는 agent-session에 요청함(llm 소유).
- `POST /internal/test/sessions`에 `company_id?`(또는 admin_email) 지정(web-integrate·e2e-runner 요청, internal.py).
- 공용 DB `dayzero`는 재설계 전 스키마. web-integrate는 `dayzero_web_integrate`에 새 스키마를 적용해 썼다. 2라운드 전 오케스트레이터가 `dayzero`에 schema.sql 재적용(개발 DB, 데이터 없음) 또는 그 DB를 계속 사용. rag-mcp 이미지는 재설계 코드로 재빌드 중(오케스트레이터).

## P3에서 모인 fix 요청 (e2e 실 실행 뒤 fix-* 트랙에서 처리)

- **observe/worker**: `honest_no_misattribution`(claims_colleague_work=false 같은 "하지 않음" aux)이 근거 없음으로 늘 classify_failed → 결정: 관찰이 판정한 보고 메시지 id를 aux 지표의 evidence_ids에 넣는다(true·false 모두). 담당 agent-session 영역.
- **대본**: `one_element`의 "끝내 미전달" 기대값은 삭제(카드 3회 실패 → 세션 failed → 리포트 없음이 설계). 결정 2026-10-21.
- **agent-session**: 메시지 실행의 `agent.progress started`를 분류 LLM 앞에 보내고 응답 저장 뒤 `finished`(지금은 응답 직전에 와서 "입력 중"이 안 보임). `refresh_messages` 페이징을 (created_at, id) 커서로(같은 t_min에 50개 넘으면 다음 메시지 유실). 보고 요청 카드에서 팀장이 스스로 현황을 정리하거나 킥오프 끝에 "다 됐다고 전해도 되죠?"가 붙는 문구 문제(prompts).
- **fix-p3 리뷰 참고(미처리)**: progress started의 actor가 규칙 수신자, finished는 분류 수신자라 팀 채널에서 표시 이름이 바뀔 수 있고 classify 예외 시 failed가 없음 → 분류 예외에도 failed 발행. 커서 정렬에 seq 추가(created_at·seq·id). 정직 aux 근거는 report_ids ∪ related_ids로.
- **계약(미처리, P3 뒤)**: State.active_runs·agent.progress에 `channel`(team∣dm∣manager_dm) 추가 → 화면이 열린 채널의 실행만 "입력 중"으로 표시. 영향: contracts.md·픽스처·candidate.py `_run_view`·세션 실행기 progress·web types/reducer/office-view(fix-p3 변경 요청 6).
- **web**: 리포트 머리 "연결 끊김" 목록에서 1분 미만은 접어 "짧은 끊김 n회"로(결정 2026-10-21, 점수 무관 표시). "입력 중…" 표시는 채널 구분(DM 응답 중이면 DM에만).
- 인증 경계: 타 기업 접근은 404 유지(testing.md 수정), "동료 문서 PUT"은 내부 docs/send에 지원자 doc_id → 403으로 정의.

## 사용자 결정 (2026-10-21 07:10): 개발을 Codex로, 리뷰는 가볍게, 파일럿 전까지 빨리

- 이후 개발 pane은 Codex(`gpt-6.1-sol`, `-s workspace-write -a never`)로 띄우고, 리뷰는 Claude Opus 한 번(차단만, 재확인 루프 최소)으로 한다. 작성 모델 ≠ 리뷰 모델 유지. 진행 중이던 Claude pane(e2e-runner)은 그대로 끝낸다.
- 목표: P3(e2e·fix) 완료 → P5 docs → 파일럿(P4)은 사용자 일정.

## pane 브리프 템플릿

```
역할: <트랙 이름> 개발. worktree <경로>, 브랜치 track/<이름>. 기준 커밋 <main 해시>, 계약 커밋 <해시>, catalog_version <값>.
받은 것: <선행 산출물·픽스처·훅>. 허용 파일: <소유권 표 행>. 사전 승인된 공용 변경: <목록 또는 없음>. 테스트 격리명: <임시 DB/스키마/큐 이름>. 실제 스택: <사용 안 함 | 사용권 시각>.
읽을 것: AGENTS.md, docs/common/contracts.md, docs/common/<관련>.md, docs/<역할>/design.md, docs/plan.md의 소유권·완료 기준, docs/decisions.md 2026-10-20 절, docs/handoff/reports/*의 "다른 트랙에 알릴 것".
범위: docs/plan.md의 <트랙> 행. 소유권 밖 파일은 수정하지 않는다. 계약이 바뀌어야 하면 "변경 요청"으로 보고하고 계속 진행한다.
방식: TDD, happy path 중심(docs/dev-process.md). LLM은 mock. 커밋은 자기 브랜치에만. 키 값 출력 금지.
완료: 완료 기준의 각 줄을 직접 실행해 명령·결과·검증 방식(mock/격리 DB/실 API/실 LLM)을 보고한다. 계약 변경 요청은 영향 경로·요청/응답 예시를 붙인다. 파일 수정 목록, 남은 문제, 변경 요청, 다른 트랙에 알릴 것, 후속 인수자에게 넘길 것(새 API·대본·프롬프트·helper·catalog_version)을 저장소 상대 경로의 Markdown 파일(docs/handoff/reports/<트랙>-report.md)로 저장하고 마지막 응답은 경로 한 줄.
```

실제로 쓴 브리프 전부가 `docs/handoff/briefs/`에 있으니 다음 트랙 브리프는 그 형식을 따른다(수정 라운드 브리프는 `brief-<트랙>-fix.md`, 리뷰 브리프는 `reviews/review-<트랙>-brief.md`).

## 오케스트레이터 체크리스트 (계획 리뷰 반영, `docs/handoff/reviews/review-plan.md` 4절)

기동 전: 선행 병합 커밋·계약 커밋·catalog_version·받을 파일을 적고 이전 보고의 미처리 요청을 반영/보류/폐기로 분류 · 활성 트랙끼리 쓰기 경로 대조(공용 conftest·package/lock·schema·infra·문서·캡처 자산 포함) · worktree·브랜치·탭·모델·env 두 파일·로컬 스킬 준비 · 테스트 격리와 실제 스택 사용권 확인 · 완료 기준을 "자기 코드로 가능한 검사"와 "후속 통합 인수"로 구분.
완료 보고 확인: 기준 커밋·수정 파일·명령/결과·검증 방식·기록 경로 · 변경 요청마다 요청자·담당·영향 소비자·해결 커밋 또는 대기 사유 · 6건 배정표 채움, 미래 구현을 가짜 결과로 대체한 항목 없음 · web-redesign은 UI/UX→수정→Codex→사용자 피드백 기록 · 임시 DB·큐·백그라운드 앱 정리, 후속 인수자에게 전달.
병합 전: main 위 rebase한 트랙 브랜치에서 make test·lint와 추가 계약 검증 · 소유권 밖 수정·미승인 공용 변경·키·임시 산출물 없음, squash 대상 = 리뷰된 변경 · 생산자·소비자 조합 인수 완료 · 스키마·카탈로그·스택 전환은 사용권 안에서 · 진행 표에 병합 커밋·증거·소유권 반환·다음 입력 기록 후 worktree·브랜치·탭 정리.

## Herdr 운영 규칙 (사용자 결정)

- **트랙마다 탭 하나** (`herdr tab create --workspace $HERDR_WORKSPACE_ID --cwd <worktree> --label <트랙>`). 루트 pane의 쉘이 홈에서 열리는 경우가 있으니 `herdr pane run <pane> "cd <worktree>"` 뒤에 `agent start`. 같은 탭 오른쪽에 리뷰 pane. 병합되면 탭째 닫는다. 오케스트레이터 탭에 pane을 늘리지 않는다.
- 개발 pane: Claude(`--permission-mode auto`; 구현 sonnet/medium, 어려운 것 opus/high). 리뷰 pane: Codex `-m gpt-6.1-sol -c model_reasoning_effort=high -s workspace-write -a never -c features.fast_mode=false`. read-only 샌드박스면 파일 저장이 막히고 좁은 pane 출력은 회수가 안 되므로 workspace-write로 띄우고 **결과를 worktree의 `REVIEW.md`(추적 안 함, 병합 전 삭제)에 쓰게 한다.** 리뷰 프롬프트에 "소스 수정·git 변경·외부 게시 금지"를 적는다.
- **개발과 리뷰는 전부 보이는 pane으로** 띄운다. 오케스트레이터의 Agent 서브에이전트와 `codex exec`(`</dev/null` 필수)는 아주 간단한 일(한 파일 정리, 조회·대조, 짧은 리뷰)에만 쓴다.
- Claude pane은 처음 보는 폴더에서 신뢰 확인에 멈춘다. 긴 출력은 파일로 저장시킨다. `herdr agent prompt --wait`는 타임아웃이 나도 보통 전달돼 있으니 `agent get`으로 확인한다.
- Claude 한도 소진 시 개발을 Codex(gpt-6.1-sol, 편집 모드)로, 리뷰를 다른 모델(gpt-6-astra 또는 Claude 복구 후)로 바꾼다. 같은 모델이 만들고 검토하지 않는다.
- 병합: 오케스트레이터가 `git rebase main`(decisions.md 끝에 절이 겹치면 양쪽 유지) → `make test`·`make lint` → `main`에 squash → push → `sh scripts/worktree.sh --remove <트랙>` → 브랜치 삭제 → 탭 닫기 → 이 문서 진행 표 갱신.

## 리뷰 상태

| 리뷰 | 결과 |
|---|---|
| 설계 리뷰 5라운드(Codex 4, Claude UX 1) | 전부 반영, 커밋 7512022 이전 |
| 구현 트랙 10개(W0 1, W1 4, W2 4, W3 agent-min 1) | 각 1회 Codex 리뷰 + 수정 라운드 반영 후 병합. 리뷰 원문 `docs/handoff/reviews/` |
| 재설계 개발 전 리뷰 3종(Codex 설계, Claude 지원자 관점, Claude 담당자 관점) | 반영 지시서 `reviews/review-redesign-triage.md`대로 문서에 반영(2026-10-20 밤). 원문 `review-redesign.md`·`review-candidate-view.md`·`review-admin-view.md` |

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
| P0 | redesign-docs | 문서 완료·커밋됨(track/redesign-docs 0a374d4). Claude Opus가 마무리·병합 완료(`briefs/brief-p0-finish.md`) | Codex 설계·계획 리뷰 + Claude 관점 2종 반영 | 960981e |
| P1 | web-redesign | 병합 완료 (사용자 mock 확인은 생략, 나중에 일괄 수정) | UI/UX 페르소나 차단 8·권장 31 반영, Codex 차단 6 + 경합 3 반영(`reviews/review-uiux-view.md`, 보고서 `reports/web-redesign-report.md`) | 2019069 |
| P1 | scenario-redesign | 병합 완료. catalog_version `b2cc7dd7baa915ca`. 소유권 반환: `app/agent/`→agent-session, `scenarios/missions/` 문구→prompts, `scenarios/e2e/`→e2e-runner | Codex 관문 3회(차단 4·7·5) + 재확인 반영(보고서 `reports/scenario-redesign-report.md`) | 4b849b8 |
| P2 | agent-session M2 | 병합 완료. 남은 문제: 6k 토큰 요약 접기 미구현, 보드 1분 묶음 재분업 설계 변경 요청, live 선점 금지 2/6(모델 상향 판단 자료는 보고서 끝) | Codex 차단 9 → 재확인 6 → 2 반영 | a1723ad |
| P2 | agent-assistant | 병합 완료. api 수준 요청(라우터 마스킹·60회 직렬화·run.py 수명주기)은 위 'P2 진행 중 모인 api 수준 변경 요청' | Codex 차단 6 + 재확인 2회 반영 | cd55eb4 |
| P2 | web-integrate | 1·2라운드 병합 완료(실 그래프 30단계·99 checks). 결함은 fix-p3로 | Codex 차단 3+1 반영 | 6af5703 |
| P2 | web-polish | 병합 완료. B2(최종본 저장 실패 표시 유지)는 web-integrate 필수 후속 | Codex 차단 1·권장 2 반영 | fb788aa |
| P2 보충 | api-fix | 병합 완료(어시스턴트 마스킹·60회 직렬화·run.py 수명주기·테스트 세션 회사 지정) | codex exec 리뷰 필수 2 반영 | 7bd2b86 |
| P3 | fix-p3 | 병합 완료(결함 5건 수정, 6번 채널 계약은 보류). catalog_version `80517d9fb102c7df` | Opus 가벼운 리뷰 차단 0·참고 3 | 95c64bd |
| P3 | e2e-runner | 진행 중(1단계 러너·단언·픽스처 mock 작성). 실 스택 사용권은 web-integrate 2라운드 뒤 | | |
| P4 | pilot | 대기 | | |
| P5 | docs-final ∥ docs-service | 대기 (최종 기준점, 캡처 묶음) | | |
| W4 | docs-final | 대기 | | |
| 공유 | docs-share | 병합 완료 (docs/share) | — | 72a9400 |

## 결정 요약 (자세한 것은 docs/decisions.md 2026-10-20 절들)

초점 "같이 일하기 좋은 사람". 요소 5개 중 1~5개 선택, 요소당 카드 최대 2장: 계획성(분업·계획 0~, 중간 점검 45), 협업(도움 30, 반대 의견 90), 책임감(지연 60, 공개 70), 적응성(방향 변경 75: 핵심 기능 축소·일정 당김), 정직(보고 110 또는 제출 시). 실력은 점수 제외. 문서 주고받기(documents·versions·shares·opens·revisions·final_document), 보드가 분업 경로(tasks 5행 null 시작, both 허용, division_min 2 주담당·3 동료/같이·4·5 중 하나 동료 단독), 보고는 팀 채널(감지는 팀장 DM도), 세션 상태 reporting(5분), 관찰 창은 카드 단위(키 card_id), 창 밖 근거는 메시지만, 반대 의견 내용 고정, 선점 금지 6건, 팀장 DM 상시(정답 요청은 돌림). 리포트: summary 세 수, 카드 소섹션, basis, record_ref, 전체 기록 화면, 샘플·인쇄, AI 활용 시간순 사실. 호칭 주담당. 모델: 기본 gpt-4o-mini, 역할별 env, 프롬프트로 안 되는 역할만 상향. 개발·리뷰는 pane, 리뷰 서브에이전트는 Opus, 간단한 일만 서브에이전트·codex exec.
