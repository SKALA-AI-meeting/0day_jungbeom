# foundation 수정 라운드 보고 (Codex 리뷰 반영)

- 브랜치 `track/foundation`, 커밋 `83ee855`(이전 `5090333` 위). main 병합·push 안 함
- 인프라는 `make infra-up` 상태(postgres·rabbitmq·rag-mcp) 그대로

## 완료 기준 재실행 결과 (`83ee855`)

| # | 기준 | 명령 | 결과 |
|---|---|---|---|
| 3 | SessionService 단위 테스트(전이 전부·멱등) | `cd services/api && uv run pytest -v` | **통과.** `test_full_lifecycle_and_idempotency`에 파트 행 5개(revision 0) 기대값을 추가함. `test_cancel_and_fail_transitions`에 세 경로를 추가함: 동의 후 만료된 초대의 start → `expired`, 종료 run `ok=False` → completed·report_enqueued_at 기록·agent_runs failed, 발행 미확인 → report_enqueued_at 비움 → `republish_pending`이 1건 재발행 후 기록 |
| 5 | FakeAgentRunner로 메시지→내부 저장→hub 브로드캐스트 | 같은 실행 | **통과.** `test_candidate_message_runs_agent_and_broadcasts` 변경 없이 통과 |
| 6 | `make test`, `make lint` | 저장소 루트 | **통과(둘 다 exit 0).** test: api 5, business-mcp 1, rag-mcp 1, report-worker 1, web 1 |

테스트 파일 밖에서 추가로 확인한 것:
- **동시 제출**: 임시 테스트(실행 뒤 삭제)에서 서로 다른 DB 세션 두 개로 `complete()`를 동시에 호출했다. 종료 실행 1회, 발행 1회였고 두 호출 모두 completed를 돌려줬다. 리뷰 재현 결과는 종료 실행 2회, 발행 2회였다
- **실제 RabbitMQ**: 라우팅되지 않는 키로 발행하면 `PublishError`가 난다(이전에는 성공으로 처리됐다). `report.generate` 발행은 Ack를 받는다. 확인용으로 넣은 메시지는 purge했다
- **CORS**: 실행 중인 `app.run`에 `OPTIONS /health`(Origin localhost:3000, Authorization 헤더 요청)를 보내면 200이고 `access-control-allow-origin: http://localhost:3000`이 붙는다. 다른 origin은 400이고 허용 헤더가 없다. 내부 앱(8001)은 405로 CORS가 없다. 8000·8001 `/health`는 둘 다 응답한다
- **SCENARIOS_DIR**: `/scenarios`(없음)이면 저장소 `scenarios/`로 대체한다. `/no/such/dir`이면 `ValueError`를 낸다

## 수정 목록

### 반드시 고칠 것
1. **종료 run 실패 처리**(`app/services/session.py`): `complete()`가 `RunResult.ok`를 확인한다. False면 경고 로그를 남기고 completed로 진행해 리포트를 발행한다. agent_runs는 `run_agent`가 failed로 기록한다
2. **동시 제출 직렬화**: `complete()`의 상태 재검증 → submitted_at → 종료 실행 → 재사용 추정 → completed 커밋 → 발행 → `session.ended`를 모두 `locks(session_id)` 안에서 한다. Lock 안에서 다시 읽은 상태가 in_progress가 아니면 그대로 돌려준다. `app/services/runs.py`의 `run_agent(..., lock_held=True)`는 Lock을 다시 잡지 않고 실행만 한다. 호출 규칙은 모듈 docstring과 `docs/agent/design.md`에 적었다
3. **시작 시 만료 검사**: `start()`가 `invites.expires_at <= now`이면 `SessionError("expired")`(410, consent와 같은 코드)를 낸다. 이미 시작한 세션의 재호출은 이전처럼 같은 값을 돌려준다
4. **CORS**(`app/main.py`, `app/config.py`): 공개 앱에만 `CORSMiddleware`를 붙였다. origin은 `WEB_ORIGIN`(쉼표 구분, 기본 `http://localhost:3000`), 메서드 전부, 헤더 Authorization·Content-Type·Idempotency-Key. 쿠키 자격 증명은 허용하지 않는다(Bearer 인증). `infra/.env.example`에 `WEB_ORIGIN`을 추가했다. 키 파일(`infra/.env`, `.env.local`)은 건드리지 않았고 기본값으로 동작한다
5. **큐 발행**(`app/queue.py`): 채널을 `on_return_raises=True`로 열고, 발행 결과가 `Basic.Ack`가 아니면 `PublishNotConfirmed`를 낸다. 어느 쪽이든 `publish_report`가 False를 돌려주고 `*_enqueued_at`은 기록되지 않는다. 테스트용 `FakePublisher`에 `fail` 플래그를 추가했다

### 같이 고칠 것
6. `scripts/seed.py`: `structuredContent`(없으면 첫 텍스트 블록의 JSON)가 `{ok: false, error}`면 실패로 처리한다. 성공이면 `data`를 돌려준다. 라우터·도구가 아직 없어 실제 실행으로는 검증하지 못했다
7. **web mocks 분리**: `mocks/index.ts`는 `mocks/admin.ts`·`mocks/office.ts`의 `ROUTES`를 합치기만 하고, 두 파일은 빈 배열이다. 공용 타입은 `mocks/types.ts`(`MockRoute`, `MockHandler`)에 두었다. fixture는 `fixtures/admin/report.json`, `fixtures/office/state.json`으로 옮겼다. 이제 기본 mock 경로는 0개이고 각 화면 트랙이 채운다. `ws-replay.ts`와 `fixtures/ws_events.json`, `message.json`, `mcp_*.json`은 foundation 쪽에 그대로 두었다. mocks README에 소유 표를 넣었다
8. **문서 파트 행**: `start()`가 `scenario["parts"]` 수만큼 `document_states`(빈 본문, revision 0)를 `ON CONFLICT DO NOTHING`으로 만든다. tasks는 만들지 않는다
9. **state.json 시각**: `started_at 2026-10-20T01:00:00Z`, `ends_at 03:00:00Z`(remaining_seconds 5400 = 30분 시점), 메시지 `created_at 01:00:00Z`(t_min 0.0)로 바꿨다. `tests/fixtures/contracts/state.json`과 `mocks/fixtures/office/state.json` 둘 다다. 같은 메시지를 복사한 `message.json`(tests·web 둘 다)의 created_at도 맞췄다. id·본문의 "..."와 report.json은 그대로 두었다
10. **config**: `SCENARIOS_DIR`이 기본값 `/scenarios`이면서 없을 때만 저장소 `scenarios/`로 대체한다. 다른 경로가 없으면 `ValueError`를 낸다

### 문서 동기화
- `docs/common/contracts.md`: 공통에 CORS 한 줄. 인증 표의 "시작" 행에 파트 행 생성과 시작 시 만료 410 `expired`. WS 봉투 `{"type","payload"}` 예시와 `session.replaced` 후 close code 4000. 큐 표의 `attempt`는 1부터 시작해 총 3회
- `docs/common/data-model.md`: SessionService 목록에 `cancel`. 세션 실패는 중단 안내만(PRD 7.4·contracts debrief와 맞춤). document_states는 시작 시 생성
- `docs/common/scenario-model.md`: 시점은 0.01분 단위로 반올림. `interview_expected_time`은 실제 책임감 카드 시각이고 미선택이면 "시작 시 공유됨"
- `docs/agent/design.md`: `RunResult.usage`. `run_agent`의 Lock 규칙(`lock_held`). 종료 run 실패 처리
- `docs/plan.md` 소유권: foundation 행에 `services/api/tests/conftest.py`를 넣고, `app/services/`에서 reuse.py, `mocks/`에서 admin·office 파일을 뺐다. api-candidate 행에 `app/services/reuse.py`와 context의 reuse 훅 연결. web-admin 행에 `mocks/admin.ts`·`mocks/fixtures/admin/`, web-office 행에 `mocks/office.ts`·`mocks/fixtures/office/`
- `docs/decisions.md`: "2026-10-20 foundation 리뷰 반영 (Codex)" 절. 결정 1·2·7·8·10, 소유권 예외 3건 수용, 확인 후 큐 유실 복구는 MVP 제외
- `scenarios/catalog.yaml`: 킥오프 주석의 "책임감 카드 시각(L×5/12)"을 "책임감 카드 시각"으로 바꿨다. 값 변경은 없지만 파일 내용이 바뀌었으므로 `catalog_version` 해시는 달라진다

## 하지 않은 것 (브리프 범위 밖)
확인 후 큐 유실 복구, 실제 runner 연결, reuse 구현, 임베딩 의존성, web build args. 키 값은 출력하지 않았다.

## 남은 것·알릴 것
- `infra/.env`의 `API_INTERNAL_URL`이 8000인 문제(이전 보고 "어긋난 점 3")는 그대로다. W1 MCP 연결 전에 사용자가 고쳐야 한다
- api-candidate: `complete()`가 세션 Lock을 잡으므로 Lock 안에서 `complete()`를 부르면 교착된다. 스케줄러·WS 핸들러에서는 Lock 밖에서 부른다. 메시지 실행은 `run_agent(...)`를 기본값(`lock_held=False`)으로 부른다
- web-admin·web-office: 이전에 index에 있던 report·state 두 경로는 이제 없다. 각자 `admin.ts`·`office.ts`에 다시 추가해야 mock 화면이 데이터를 받는다
