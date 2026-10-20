# worker 수정 라운드 보고 (Codex 리뷰 반영)

브랜치 `track/worker`. 먼저 `main`(web-admin·api-candidate 병합분 포함) 위로 rebase했고(충돌 없음, 첫 커밋 `1c0c811`), 수정 커밋은 `38699fa`. push·병합은 하지 않았다. worktree의 `REVIEW.md`는 지웠다.

## 수정 목록

| # | 리뷰 항목 | 수정 | 파일 |
|---|---|---|---|
| 1 | P1 리포트 형태 | `context.prev_persona_message`를 문자열 `"<이름> · <t>분: <본문>"`로 바꿈(이름은 scenario.company, 없으면 동료·팀장). `context.card_at_t_min`은 실제 카드 메시지 시각. 섹션 `aux_facts`는 사실 문장 배열(값 없으면 빼고, 빈 배열 허용), `out_of_window_messages`는 `[{t_min, channel, quote}]`. 항목 `minutes`는 응답 시간 항목에만 두고 관련 메시지가 없으면 null. AI 근거에 `category`를 규칙으로 붙임(재사용 행 → delegate, 요청문에 검토·확인·맞는지·검증 류 → verify, 그 외 → context) | `report_worker/report.py` |
| 2 | P2 usage 저장 | api `ReportIn.usage: dict \| None`, draft insert에 `usage`(on_conflict_do_nothing이라 재전달은 최초 값 유지), 해시는 content만. 워커 전송 주석 정리 | `services/api/app/routers/internal.py`, `report_worker/api.py` |
| 3 | P2 미발생 오판 | api 세션 조회에 `events: [{id, card_id, element, status, due_at, fired_at}]`(due_at 순). 워커는 카드 발생 = status fired·done, 실제 시각 = 그 event id의 첫 메시지(없으면 fired_at), 전달 지연 > 1.5분 → window_missed. 메시지 시각 기반 대용 추정 삭제. `id`는 메시지 event_id와 맞추는 데 필요해서 넣었다 | `internal.py`, `report.py`, `rubric.py` |
| 4 | P2 응답 분·AI 구분 | 위 1의 `minutes`·`category`. web-admin이 `items[].minutes`를 읽고 있어 이름은 그대로 둠 | `report.py` |
| 5 | P2 메시지 1,000건 | api messages에 `offset`(ge 0) 추가, 정렬에 `Message.id`를 더해 페이지가 안정적. 워커 `all_messages()`가 limit 500으로 짧은 페이지가 나올 때까지 읽음 | `internal.py`, `report_worker/api.py` |
| 6 | P2 금지어 | `\d+위`(위치 제외)·`\d+등`(등분 제외)·만점·감점·가산점·상위/하위 N%를 추가(등수는 이미 있었음). 검사 대상은 observed·note·summary뿐이라 quote·평가표 숫자는 그대로. "우선순위"는 그대로 둠 | `report.py` |
| 7 | P2 소유권 예외 | pyproject·lock 변경(런타임 psycopg[binary], dev pyyaml)을 decisions.md에 승인 예외로 기록 | `docs/decisions.md` |
| 같이 | happy path LLM 재실행 | approve 뒤 `llm.calls == 1` 단언 | `tests/test_graph.py` |
| 같이 | fixture 정리 | Postgres: CREATE SCHEMA·두 번째 연결·setup 어디서 실패해도 `DROP SCHEMA IF EXISTS`. RabbitMQ: connect 도중 실패해도 접두사 큐 3개·exchange를 이름별 새 채널로 지움 | `tests/test_graph.py`, `tests/test_dlq.py` |
| 같이 | 모델 고정 | `OPENAI_MODEL`이 gpt-4o-mini가 아니면 `load_settings()`가 RuntimeError(시작 시) | `report_worker/config.py` |
| 같이 | null 지표 사유 | `AUX_METRICS = {response_specific, proposes_alternative, proposes_fix}`는 null이면 레이블이 정상이어도 classify_failed. window_missed는 관찰 `metrics.window_missed` `{value: true, evidence_ids: []}` 또는 bool(true) | `report_worker/rubric.py` |
| 문서 | 계약 | Report 워커 산출 필드 표(섹션·항목·근거 context·ai_usage category·재사용 행), 내부 세션 조회 `events`, messages `offset`·정렬·한도, 관찰 metrics 형식과 `window_missed`, draft `usage`, 큐 재시도 백오프 5·15·45초 | `docs/common/contracts.md` |
| 문서 | 결정 | 맨 아래 "2026-10-20 worker 리뷰 반영" 절: 형태 확정, usage·events·offset, null 사유, 소유권 예외, 금지어·모델 검사 | `docs/decisions.md` |
| 기준 예시 | 실제 출력 | 4요소(협력·책임감·유연성·존중) 세션을 실제 `build_draft`(FakeLLM)로 조립한 결과 | `services/report-worker/tests/fixtures/report_sample.json` |

## 추가·변경 테스트

- `tests/test_report.py`(새 파일, 3개)
  - `test_event_status_decides_fired_and_delay`: 리뷰의 재현 그대로. review 이벤트는 done이고 90분 메시지가 있지만 respect 이벤트는 pending → respect `event_fired=false`, 사유 event_not_fired, 항목 전부 event_not_fired. 책임감 카드 메시지가 예정 60분보다 2분 늦음 → window_missed, 근거 `card_at_t_min == 62`. 협력은 정상(사유 없음, 카드 시각 30).
  - `test_report_shape_matches_admin_view`: context 문자열·카드 시각, `aux_facts == []`, 창 밖 메시지 `[{t_min, channel, quote}]`, `minutes == 2.0`이 응답 시간 항목에만 있음, AI 근거 category 순서 context·verify·delegate.
  - `test_collect_reads_all_messages_by_offset`: 메시지 1,111건 → 전부 수집, 페이지 요청 3회.
- `tests/test_rubric.py::test_window_missed_and_aux_null_reasons`: 레이블이 정상인데 proposes_fix null → classify_failed, window_missed의 dict·bool 두 형식.
- `tests/test_graph.py`: happy path에 `llm.calls == 1`, 금지어 테스트에 1위·만점·감점·가산점·2등·상위 10% 포함, "우선순위" 문장과 quote 원문("우선순위상 1위인…")이 남는지, 평가표 합계 숫자 유지.
- `services/api/tests/routers/test_internal.py`
  - draft 테스트: draft를 `usage`와 함께 저장 → `reports.usage == usage`, 다른 usage로 재전달 → 최초 값 유지.
  - 세션 조회 테스트: `events`에 선택 요소 카드가 pending·fired_at null로 있고 미선택 respect는 없음. 메시지 테스트: `limit=1&offset=1`이 두 번째 메시지.
- conftest: scenario에 company, 세션에 events, 검증 요청 어시스턴트 호출 1건, mock 내부 API의 messages가 offset·limit 페이지를 따름.

## 검증 명령과 결과

| 명령 | 결과 |
|---|---|
| `cd services/report-worker && uv run pytest -q -rs` | 17 passed, skip 0 (Postgres 체크포인터·RabbitMQ DLQ 실제 실행) |
| 테스트 후 `rabbitmqctl list_queues`/`list_exchanges`의 `test-worker` 수, `information_schema.schemata`의 `test_worker_%` 수 | 0 / 0 / 0 |
| `cd services/api && uv run pytest -q tests/routers/test_internal.py` | 10 passed |
| 루트 `make test` | 통과: api 31, business-mcp 11, rag-mcp 10 + 1 deselected, worker 17, web 6 files / 9 tests |
| 루트 `make lint` | 통과 (ruff check, ruff format 85 files, eslint, prettier) |
| `apps/web`에서 임시 `components/admin/zz-worker-sample.test.tsx`로 `report_sample.json`(+ api GET 합성 필드 alias·position.name·빈 deliverable)을 `ReportView`로 `renderToStaticMarkup` | 2회 실행 모두 통과. 1회차는 출력 HTML에 "직전 메시지: 이도현 · 30분", "카드 발생 30분", "실제 2분", 위임·맥락·검증 그룹, "운영 정책 문서를 열람함", "관찰 창 밖 메시지 95분"이 있고 "기타"·"[object Object]"는 없음을 단언. 2회차는 console.error 0건을 단언. 임시 파일은 지웠고 화면 코드는 수정하지 않음(`git status` 깨끗) |

## web-admin 타입(`apps/web/components/admin/types.ts`)과의 대조

| 필드 | 워커 출력 | 타입 | 판정 |
|---|---|---|---|
| `Evidence.context` | `{prev_persona_message: string\|null, card_at_t_min: number}` | `{prev_persona_message?: string\|null; card_at_t_min?: number\|null}` | 일치 |
| `Evidence` 추가 키 | doc_view `doc_id`, revision `change_ratio`·`summary` | `change_ratio?`, `summary?`(doc_id 없음) | 남는 키는 무시돼 문제없음 |
| `ReportSection.aux_facts` | string[] | `Fact[]` (`string \| {text}`) | 일치 |
| `ReportSection.out_of_window_messages` | `{t_min, channel, quote}[]` | 같은 형태 | 일치 |
| `ReportSection.no_record_reason`·`event_fired`·`note` | string\|null, bool, string | `?: string`, `?: boolean`, `?: string` | 실행상 일치. 사유가 없을 때 null을 보내는데 타입은 optional string이다(`??`로 처리돼 화면 영향 없음) |
| `RubricItem.no_record_reason` | auto가 값이면 null | `?: string` | 위와 같음 |
| `RubricItem.minutes` | 응답 시간 항목만, 관련 메시지 없으면 null | `?: number` | 대체로 일치. **null일 때 화면이 `item.minutes !== undefined`라 "실제 분"(숫자 빈칸)을 그린다** → 아래 "다른 트랙에 알릴 것" |
| `AiEvidence.category` | delegate·context·verify | 같은 열거 | 일치. 재사용 행의 `ratio`는 타입에 없지만 무시됨 |
| `Report` 상위 | session_id, stage, position.elements, rubric, sections, ai_usage, generated_at, reviewed_at | alias·position.name·deliverable도 필수 | api GET이 합성(`admin.py get_report`). 워커 content에는 넣지 않음 |
| `ReportSection.card_t_min` | 넣지 않음 | 선택 | 화면은 근거 context로 대체한다. 근거가 없는 섹션은 카드 시각이 안 보인다(브리프 형태에 없는 필드라 추가하지 않음) |

## 남은 문제

1. 응답 시간 항목의 `minutes: null`은 화면에서 "실제 분"으로 보인다(화면 수정 금지라 그대로 둠).
2. 전달 지연 판정(예정보다 1.5분 초과)을 워커도 한다. observe가 `metrics.window_missed`를 남기면 둘 중 하나만 맞아도 window_missed가 된다. 두 판단이 다르게 나올 수 있는 경우(예: observe가 다른 기준을 씀)는 agent-session과 맞춰야 한다.
3. `aux_facts` 문장은 지금 카탈로그의 두 지표(colleague_revised_after_feedback, policy_doc_opened)만 사람이 읽는 문장으로 바꾼다. 새 aux 지표가 생기면 `"<지표>: 예/아니오"`로 나온다.
4. 섹션 근거가 없는 요소(기록 없음)는 화면에 카드 발생 시각이 안 보인다. 섹션 `card_t_min`을 넣을지는 계약 결정이 필요하다.
5. DLQ 테스트의 "api 다운"은 MockTransport 장애이고 실제 api 중지가 아니다. 실제 통합은 M3.

## 변경 요청

- 없음. 이번 라운드에서 허용된 범위(internal.py·contracts.md·decisions.md)로 이전 보고의 변경 요청 1~3을 반영했다.

## 다른 트랙에 알릴 것

- **web-admin**: `items[].minutes`가 null일 수 있다(응답 시간 항목인데 관련 메시지가 없을 때). `!== undefined` 대신 `!= null` 검사가 맞다. 실제 워커 출력 예는 `services/report-worker/tests/fixtures/report_sample.json`이고 mock fixture를 이 형태에 맞춰 두면 좋다. `no_record_reason`은 값이 없을 때 null로 온다.
- **agent-session(observe)**: window_missed는 `metrics.window_missed: {value: true, evidence_ids: []}`로 남긴다. aux 지표(response_specific·proposes_alternative·proposes_fix)를 null로 두면 리포트에 classify_failed로 보인다. 카드 inject 메시지는 반드시 자기 이벤트의 event_id를 달아야 워커가 실제 카드 시각을 잡는다(없으면 fired_at).
- **api-admin / api-candidate**: `GET /internal/sessions/{id}`에 `events`가 늘었고 messages에 `offset`이 생겼다(정렬에 id 추가). draft `usage`는 `reports.usage`에 저장된다. `tests/routers/support.py::to_report_ready`는 그대로 두었고 draft 테스트만 usage를 직접 보낸다.
- **e2e-runner**: 세션 비용 합산에 `reports.usage`를 쓸 수 있다(`tokens_in`, `tokens_out`, `llm_calls`).
