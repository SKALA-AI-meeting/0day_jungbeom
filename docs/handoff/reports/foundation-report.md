# foundation 트랙 완료 보고 (W0)

- worktree: `Day-0_zaeho.worktrees/foundation`, 브랜치 `track/foundation` (main 병합·push 안 함)
- 커밋 3개(기준 `7512022` 위)
  - `e1d7b32` 카탈로그가 YAML로 읽히도록 두 줄을 작은따옴표로 감쌈(값은 그대로) — **foundation 소유 밖 파일**, 아래 "어긋난 점 1"
  - `b10324d` ruff가 `.md` 코드 블록까지 포맷 검사해 `make lint`가 깨지지 않도록 Markdown 제외 — **foundation 소유 밖 파일(`ruff.toml`)**, 아래 "어긋난 점 2"
  - `5090333` 서비스 5개의 최소 앱, api 공용 기반, web 골격, 시드·픽스처
- 마지막 상태: `make infra-up` 상태(postgres·rabbitmq·rag-mcp)로 되돌려 둠

## 완료 기준 실행 결과

모든 항목은 최종 커밋(`5090333`) 상태에서 직접 실행했다.

| # | 기준 | 명령 | 결과 |
|---|---|---|---|
| 1 | `make up`에서 전부 healthy | `make infra-down; make up` 후 `docker compose ps`, 각 health 호출 | **통과.** 7개 컨테이너(api, business-mcp, postgres, rabbitmq, rag-mcp, report-worker, web) 전부 `healthy`. `curl localhost:8000/health` → `{"status":"ok"}`, `curl localhost:3000/api/health` → `{"status":"ok"}`, 컨테이너 안 `business-mcp:9101/health`·`rag-mcp:9102/health`·`api:8001/health` → `{"status":"ok"}`, worker `/tmp/heartbeat` 갱신 후 16초. 호스트에서 8001은 연결 안 됨(000, 미공개 확인) |
| 2 | `make infra-up` 후 로컬 `app.run`이 8000·8001 응답 | `make infra-up; cd services/api && uv run python -m app.run` → curl | **통과.** 8000 `{"status":"ok"} 200`, 8001 `{"status":"ok"} 200`. 두 Uvicorn이 한 프로세스에서 뜸. `--reload`도 확인: 파일을 바꾸면 watchfiles가 프로세스 전체를 재시작하고 두 포트가 다시 응답 |
| 3 | SessionService 단위 테스트(전이 전부·멱등) | `cd services/api && uv run pytest -v` | **통과.** `test_full_lifecycle_and_idempotency`(초대→동의→시작→완료→report_ready→approving→reviewed, 각 전이 재호출 멱등, 동의 전 시작·시작 후 동의 409, 발행은 generate·approve 각 1회, 완료 재호출 시 발행·`session.ended` 반복 없음, 이벤트 9행·공개 5행), `test_cancel_and_fail_transitions`(cancel 멱등·취소 후 동의 410 코드, 시작 후 취소 409, fail(session)·fail(report) 멱등) |
| 4 | 조립 결과가 scenario-model.md 수치와 일치 | 같은 실행 | **통과.** `test_assembled_timeline_matches_scenario_model`: L=120 4개는 저장 형식 예시와 같음(kickoff 0, division 10, cooperation 30, responsibility 50(공개 65), midpoint_draft 60, flexibility 70, review 90, respect 90, report_request 110, releases_at_start 4개). L=120 3개는 30·50·70, L=6 4개는 1.5·2.5·3.5·4.5 |
| 5 | FakeAgentRunner로 메시지→내부 저장→hub 브로드캐스트 | 같은 실행 | **통과.** `test_candidate_message_runs_agent_and_broadcasts`: 지원자 메시지 마스킹 저장, agent_runs started→finished(ref_ids=[message_id]), 동료 고정 응답이 같은 run_id로 저장, 소켓 프레임 순서 `message.ack → message.new → agent.progress(started) → message.new → agent.progress(finished)`, 같은 client_msg_id 재전송은 저장·실행 없이 기존 메시지로 ack |
| 6 | `make test`, `make lint` 통과 | 저장소 루트에서 `make test`, `make lint` | **통과(둘 다 exit 0).** test: api 5, business-mcp 1, rag-mcp 1, report-worker 1, web(vitest) 1. lint: ruff check·format, eslint·prettier |

추가 확인: api 테스트는 실행마다 임시 DB(`dayzero_test_<랜덤>`)를 만들고 끝나면 지운다. 실행 뒤 postgres에는 `dayzero`만 남는다. 그래서 여러 worktree가 같은 postgres에서 테스트해도 서로 겹치지 않는다.

## 만든 것

### api (`services/api/`)
- `app/config.py`: env 로드(`infra/.env.local` → `infra/.env`, 이미 있는 환경변수는 덮어쓰지 않음)
- `app/db.py`: SQLAlchemy async 엔진·세션
- `app/models/`: `schema.sql`과 1:1인 18개 테이블. DDL 정본은 `schema.sql`이고 `create_all`은 쓰지 않음. 체크포인터·`doc_chunks`는 매핑하지 않음
- `app/auth.py`: bcrypt, 역할별 JWT(admin·candidate·debrief, 세션 JWT 만료 = L+120분), 초대 토큰 원문/sha256 해시, 의존성 `require_admin`·`require_candidate`(경로 session_id 일치, 아니면 403)·`require_debrief_reader`·`require_internal`(X-Internal-Token)
- `app/services/session.py`: SessionService(`create_for_invite`, `consent`, `cancel`, `start`, `complete`, `mark_report_ready`, `approve`, `mark_reviewed`, `fail`), `SessionError(code)`, `end_run_id = uuid5(session_id, "end")`
- `app/services/scenario.py`: 카탈로그 로드, `catalog_version`(`scenarios/version.py`를 파일 경로로 import), elements 검증(`InvalidElements`), 조립 `build_scenario`, 시작 시 펼치기 `expand`
- `app/services/messages.py`: `accept_candidate_message`(마스킹→client_msg_id 멱등 저장→agent_runs started→ack·new), `save_internal_message`((run_id, seq) 멱등, 새 행만 new), `serialize`(계약 Message 형식, t_min)
- `app/services/runs.py`: `start_run`, `finish_run`, `run_agent`(세션 Lock 안에서 실행하고 finished/failed 기록)
- `app/services/locks.py`, `app/services/context.py`: 세션 Lock, 공유 `AppContext`(hub·Lock·runner·publisher·DB), 의존성 `get_context`
- `app/hub.py`: 세션별 소켓 1개, 새 연결 시 이전 연결에 `session.replaced` 보낸 뒤 닫음(close code 4000), `broadcast`
- `app/queue.py`: aio-pika publisher confirm·persistent, 토폴로지(exchange `dayzero` direct, generate·approve는 DLX→`report.dlq`), `publish_report`(확인 뒤에만 `*_enqueued_at` 기록), `republish_pending`(outbox 재탐색)
- `app/masking.py`: 이메일 → `[이메일]`, 전화번호(휴대·지역·+82) → `[전화번호]`
- `app/agent/runner.py`: `AgentRunner` Protocol, `Stimulus`, `RunResult`, `FakeAgentRunner`
- `app/main.py`: 공개·내부 앱, 둘 다 `/health`, 오류 응답을 `{"error": {code, message}}`로 통일, 라우터 자동 포함
- `app/run.py`: 한 루프에서 uvicorn Server 2개, `--reload`(watchfiles), 스케줄러 자동 기동
- `Dockerfile`(curl 포함, 8000·8001), `pyproject.toml`(pytest live 마커·`addopts = "-m 'not live'"`), `uv.lock`
- `tests/`: conftest(임시 DB, FakeSocket, FakePublisher, position 팩토리), 테스트 5개

### MCP·worker
- `services/business-mcp/`, `services/rag-mcp/`: FastMCP(`fastmcp` 4.1.1) Streamable HTTP `/mcp`와 `/health`, `python -m business_mcp`(9101)·`python -m rag_mcp`(9102), Dockerfile, pyproject·lock, health 테스트. 도구는 없음
- `services/report-worker/`: `python -m report_worker`가 30초마다 `/tmp/heartbeat`(env `HEARTBEAT_PATH`)를 갱신, Dockerfile, pyproject·lock, heartbeat 테스트. 소비자는 없음

### web (`apps/web/`)
- Next 16.4.2, React 19.3, Tailwind 4.3, TypeScript 5.9, eslint 9 + eslint-config-next + prettier, vitest 4
- `app/globals.css`: 토큰(`@theme`: 색 16개, 글꼴, 글자 크기 6단계, 모서리 3단계, 간격). `app/layout.tsx`, `app/page.tsx`(안내만), `app/api/health/route.ts`(+테스트)
- `components/ui/`: props와 골격만. `Button`, `Badge`, `StatusBadge`(9개 표시 상태 라벨: 초대됨·만료·취소·진행 중·완료·리포트 준비됨·확정 중·검토 완료·실패), `Card`, `Input`·`Textarea`·`Select`, `Tabs`(base-ui, 안 읽음 수), `ConfirmDialog`(base-ui), `EmptyState`
- `lib/api.ts`: fetch 래퍼(Bearer, Idempotency-Key, 오류 → `ApiError(status, code)`), `NEXT_PUBLIC_MOCK=1`이면 mocks, `sessionSocketUrl`
- `mocks/`: 계약 예시 JSON, 경로 표 `ROUTES`(report·state 2개만), `ws-replay.ts`(프레임 시간순 재생)
- `Dockerfile`(standalone), `pnpm-lock.yaml`, `pnpm-workspace.yaml`(unrs-resolver 빌드 스크립트 비허용, pnpm 11이 승인 안 된 빌드를 오류로 처리함)
- UI 라이브러리: `emilkowalski/skills`의 `pick-ui-library` SKILL.md를 웹에서 읽고 그 기준대로 프리미티브 base-ui, 클래스 clsx, 변형 cva를 골랐다. `npx skills add`로 스킬을 설치하지는 않았다

### 공용
- `scenarios/version.py`: `catalog_version()`. catalog.yaml, documents/*.md, prompts/* 전체(경로+내용)를 sha256으로 해시해 앞 16자리. 표준 라이브러리만 씀
- `scripts/seed.py`: httpx만 사용. 가입(409면 로그인) → 채용 건 생성 → rag-mcp `reindex_documents`(MCP JSON-RPC 직접 호출). **검증 못 함**: 라우터와 도구가 아직 없음
- `tests/conftest.py`(`load_contract`, `scenarios_dir`), `tests/fixtures/contracts/`(report, state, message, mcp_ok, mcp_error, ws_events) + README
- 루트 `pyproject.toml`·`uv.lock`: ruff 도구 환경. Makefile의 `uv run ruff`가 루트에서 돌려면 프로젝트가 필요함
- `infra/.env`, `infra/.env.local`(git 무시 확인, 커밋 안 함). 아래 "남은 문제 1"

## 남은 문제

1. **env 파일 위치.** worktree에는 `infra/.env`가 없어 main 체크아웃의 `infra/.env`를 이 worktree로 복사했다(내용은 출력하지 않음). `.env.local`은 이 복사본에서 `postgres`·`rabbitmq`·`api`·`business-mcp`·`rag-mcp` 호스트명만 `localhost`로 바꿔 만들었다. main 체크아웃에는 `.env.local`이 아직 없다. W1 worktree들도 둘 다 필요하다
2. **compose 프로젝트 이름 공유.** 모든 worktree와 main에서 compose 파일이 `infra/`에 있어 프로젝트 이름이 전부 `infra`다. 어느 worktree에서 `make up`을 해도 같은 컨테이너와 볼륨(pgdata 등)을 바꾼다. `infra-up` → `up`으로 바꾸면 postgres가 포트 바인딩 없이 재생성되므로, 끝나면 `make infra-down; make infra-up`으로 되돌려야 한다(이번에 그렇게 했다)
3. **rag-mcp 임베딩 의존성 미포함.** BGE-M3용(sentence-transformers/FlagEmbedding + torch)은 이미지가 수 GB라 넣지 않았다. 지금은 asyncpg·pgvector만 있다. lockfile은 foundation 소유인데 rag-mcp 트랙이 추가해야 하므로 승인 절차가 필요하다
4. **`app/services/reuse.py`(estimate_reuse) 미구현.** foundation 소유 경로(`app/services/`)인데 브리프 범위에 없다. `complete()`에 `reuse_estimator` 훅(기본 없음)만 두었다. 담당 트랙을 정해야 한다
5. **세션 시작 시 `document_states`·`tasks` 행을 만들지 않는다.** State 예시에는 revision 0인 빈 파트가 있다. 시작 시 만들지, PUT에서 upsert할지 api-candidate와 정해야 한다
6. **`seed.py` 미검증**(라우터·도구가 생긴 뒤 `make seed`로 확인)
7. **web 이미지의 `NEXT_PUBLIC_*`는 빌드 시점 값이다.** compose는 런타임 env_file만 주므로 지금은 `lib/api.ts` 기본값(localhost:8000)이 들어간다. 지금 `.env` 값과 같아서 동작은 한다. 바꾸려면 compose에 build args가 필요하다(compose는 foundation 소유가 아님)

## 문서·계약과 어긋난 점 (추측으로 고치지 않은 것 포함)

1. **`scenarios/catalog.yaml`이 YAML로 읽히지 않았다**(34행 `(예: "…")`, 37행 `"AI 맞죠?" → …`). 두 줄을 작은따옴표로만 감싸 읽힌 값은 원문과 같다. 소유 밖 파일이라 별도 커밋(`e1d7b32`)으로 분리했다. 받아들이지 않으면 이 커밋만 빼면 되지만, 그러면 조립·테스트가 깨진다
2. **ruff 0.17은 Markdown 코드 블록도 포맷한다.** 그래서 `docs/agent/design.md`가 `ruff format --check`에 걸려 `make lint`가 실패했다. `ruff.toml`에 `extend-exclude = ["*.md"]` 한 줄을 넣었다(`b10324d`, 소유 밖)
3. **`infra/.env`의 `API_INTERNAL_URL=http://api:8000`.** `.env.example`·계약은 8001이다. 키 파일이라 손대지 않았고, `.env.local`도 그대로 `localhost:8000`이 됐다. 지금은 영향이 없지만, MCP가 내부 API를 부르기 시작하면 8001로 고쳐야 한다(사용자가 직접 수정)
4. `scenario-model.md`는 division을 L/12로, 카탈로그는 `at_fraction: 0.0833`(→9.996)으로 적는다. 조립은 0.01분 단위로 반올림해 문서 수치(10, 110, L=6이면 0.5·5.5)와 맞췄다
5. 카탈로그 주석 `{interview_expected_time} = 책임감 카드 시각(L×5/12)`. L×5/12가 책임감 카드 시각과 같은 경우는 3~4개 선택일 때뿐이다(2개면 60분, 1개면 30분). 실제 책임감 카드 시각을 `scenario.vars.interview_expected_time`("00:50" 형식)에 넣었고, 미선택이면 "시작 시 공유됨"이다
6. **AgentRunner 시그니처는 `docs/agent/design.md`를 따랐다**: `run(session_id, stimulus: Stimulus, run_id)`, Stimulus `{type, message_id?, event_ids}`. `RunResult`에는 문서의 `{ok, fallback_used, error}`에 `usage`를 더했다. `agent_runs.usage`를 채울 출처가 필요해서다
7. WS 프레임 형식은 계약에 명시가 없어 `{"type": ..., "payload": {...}}`로 정했다. web mocks도 같은 형식이다. 계약에 적어 두기를 제안한다
8. 계약의 MCP 응답 예시는 `{"ok": true, "data": {...}}`라 JSON이 아니다. 픽스처 `mcp_ok.json`의 data에는 Message 예시를 넣었다
9. 큐 본문의 첫 `attempt` 값은 계약에 없어 `1`로 정했다(1→2→3에서 실패하면 DLQ, 총 3회). worker 트랙이 같은 값을 써야 한다
10. `data-model.md`의 SessionService 목록에 `cancel`이 없지만, 계약의 `/admin/sessions/{id}/cancel`도 상태 전이라서 `cancel()`을 추가했다(invited→cancelled, `invites.cancelled_at`)
11. `SCENARIOS_DIR=/scenarios`는 로컬에 없는 경로다. 브리프대로 `.env.local`에서는 호스트명만 바꿨고, 대신 config가 그 경로가 없으면 저장소의 `scenarios/`를 쓰도록 했다
12. mcp Python SDK 2.x는 `FastMCP`를 `MCPServer`로 이름을 바꿨다. 설계의 "FastMCP"에 맞춰 독립 패키지 `fastmcp`(4.1.1)를 썼다. api의 `mcp>=1.9`(2.3.0으로 해석)는 에이전트 트랙의 MCP 클라이언트용이므로 API 차이를 확인해야 한다
13. `docs/frontend/design.md`는 스킬 설치(`npx skills add`)를 말하지만, 외부 코드 설치라 하지 않고 SKILL.md만 읽었다
14. `apps/web/README.md`(M1 안내 문구)를 web 실행법으로 바꿨다. 소유 표에는 없는 파일이다

## 다른 트랙에 알릴 것

- **라우터(api-admin, api-candidate)**: `app/routers/{admin,candidate,ws,internal}.py`에 `router = APIRouter()`만 두면 `main.py`가 자동으로 붙인다(admin·candidate·ws는 8000, internal은 8001). `main.py`는 고치지 않는다. `SessionError(code)`를 던지면 404/409/410으로 바뀐다(`main.ERROR_STATUS`). 의존성은 `get_context`(`ctx.session_service(db)`, `ctx.hub`, `ctx.runner`, `ctx.locks`, `ctx.publisher`, `ctx.session_factory`)
- **api-candidate**: WS `message.send`는 `accept_candidate_message(...)`를 부른 뒤 `run_agent(db, runner, locks, session_id, Stimulus("message", message_id), run_id)`를 백그라운드로 돌린다. 스케줄러는 `app/scheduler.py`에 `async def run(ctx)`를 두면 `run.py`가 같은 루프에서 띄운다. outbox는 `queue.republish_pending(db, ctx.publisher)`. 종료는 `SessionService.complete(id, "timeout"|"submitted")`
- **api 테스트 공용 픽스처**: `services/api/tests/conftest.py`(임시 DB, `FakeSocket`, `FakePublisher`, `service`, `make_position`)는 foundation이 만들었다. 소유 표에는 루트 `tests/conftest.py`만 있으니 이 파일도 공유 대상으로 정해 달라
- **api-admin**: 채용 건 생성은 `build_scenario(settings.scenarios_dir, elements, 120)` → `(scenario, catalog_version)`, 검증 실패는 `InvalidElements`(→ 400 `invalid_elements`). 초대는 `SessionService.create_for_invite`. 반환한 토큰 원문으로 링크를 만든다
- **agent-session**: Protocol은 `app/agent/runner.py`. 세션 시나리오에는 카드 본문, `documents`(본문), `prompts`(prompts/ 전체), `vars`, persona·parts·division 규칙이 복사돼 있다. respect 미선택이면 review 카드에 `review_without_violation: true`가 붙는다. FakeAgentRunner의 seq는 respond=1, inject=1+카드 순번이다
- **business-mcp / rag-mcp**: `server.py`의 `mcp`에 도구를 추가한다. rag-mcp는 `/scenarios/version.py`의 `catalog_version()`을 파일 경로로 import한다(api의 `scenario.catalog_version` 참고). 임베딩 의존성은 "남은 문제 3"
- **worker**: 큐 이름·DLX는 `app/queue.declare_topology`와 같아야 한다. 첫 attempt는 1이다. heartbeat는 `report_worker.heartbeat.run()`과 같은 루프에서 소비자를 돌리면 된다
- **web-admin / web-office**: 토큰은 Tailwind 유틸리티(`bg-surface`, `text-muted`, `border-line`, `bg-accent`, `text-danger` …)로 쓴다. 상태 배지는 `StatusBadge`. mock 경로는 `mocks/index.ts`의 `ROUTES`에 추가하고 WS는 `replay()`를 쓴다
- **prompts**: `scenarios/prompts/` 전체가 `catalog_version`과 `scenario.prompts`에 들어간다(README 포함)
