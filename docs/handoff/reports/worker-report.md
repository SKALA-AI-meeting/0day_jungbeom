# worker 트랙 (W2) 완료 보고

브랜치 `track/worker`, 커밋 `d6b5a08` (push·병합 안 함). 수정은 모두 `services/report-worker/` 안.

## 완료 기준별 결과

| 완료 기준 (docs/worker-infra/design.md) | 테스트 | 결과 |
|---|---|---|
| draft 생성 후 그래프 멈춤 → approve로 같은 thread 재개 → final 저장(draft와 동일 해시) | `tests/test_graph.py::test_draft_pauses_then_approve_resumes_with_same_hash[memory\|postgres]` | 통과. postgres 쪽은 공용 DB 임시 스키마에서 실제 `AsyncPostgresSaver`로 돈다. thread `report:{id}`, interrupt 뒤 draft POST, generate 재전달은 LLM을 다시 부르지 않고 draft 저장만, final 본문의 정규화 해시가 draft와 같음 |
| 중복 approve 멱등(reviewed면 상태 확인 후 ack) | `test_duplicate_approve_is_idempotent` | 통과. 두 번째 approve는 final POST 없이 ack, 재발행 없음 |
| final 저장 후 ack 전 재전달 → 200 기존 값 | `test_redelivery_after_final_before_ack_returns_existing` | 통과. api가 final을 저장한 뒤 응답이 끊김 → attempt 2 재발행 → 다시 finalize → mock api가 200 reviewed(기존 값) → thread 완료 |
| LLM 사용량을 `reports.usage`에 기록 | `test_usage_recorded_with_draft` | 통과(워커 쪽까지만). draft POST 본문에 `usage {model, llm_calls, retries, tokens_in, tokens_out, latency_ms, fallback_used}`를 싣는다. **api가 아직 이 필드를 저장하지 않음**(변경 요청 1) |
| 금지어·타 세션 근거 id 제거 | `test_forbidden_words_and_foreign_evidence_removed` | 통과. observed·note·summary에서 금지어 든 문장 삭제, 관찰 evidence·지표 evidence_ids의 타 세션 id 제거 |
| `rubric.evaluate` 단위 테스트(카드별 픽스처, 기록 없음 포함) | `tests/test_rubric.py` (카드 4개 parametrize + 기록 없음 1) | 통과. 4장 모두 실제 `scenarios/catalog.yaml` rubric 사용. event_not_fired·no_activity·classify_failed·not_applicable, unclassified에서 지표 항목만 계산, response_minutes null → 0 |
| api 다운 상태 발행 → 3회 시도 후 DLQ → 복구 후 report_failed | `tests/test_dlq.py::test_api_down_retries_then_dlq_then_report_failed` | 통과. 공용 RabbitMQ에 `test-worker-<랜덤>.` 접두사 exchange·큐를 만들어 실제 발행·소비. attempt [1,2,3] → dlq → api 다운 중 report_failed 미ack 재시도 → 복구 뒤 failed. 테스트 후 큐·exchange 삭제 확인(`rabbitmqctl list_queues`에 0건), 임시 스키마도 0건 |
| `uv run pytest` | `cd services/report-worker && uv run pytest -q` | 13 passed |
| 루트 `make test` | `make test` | 통과 (api 23, business-mcp 11, rag-mcp 10 + 1 deselected, worker 13, web 1) |
| 루트 `make lint` | `make lint` | 통과 (ruff check·format, eslint·prettier) |
| (참고) 이미지 | `docker build -t dayzero-report-worker:track services/report-worker` 후 컨테이너 import | 성공, psycopg binary 구현 로드. compose 전체 기동은 하지 않음(M3) |

## 구현 요약

- `graph.py`: `collect → draft → approval[interrupt(draft)] → finalize`. draft 생성 노드와 interrupt 노드 분리(재개 시 LLM 재실행 없음). finalize가 state의 draft를 그대로 `POST /report/final`.
- `consumer.py`
  - generate: thread 상태 조회 → 완료면 ack만, 멈춤이면 draft 저장만, 중간 실패 체크포인트면 `ainvoke(None)`으로 이어서, 없으면 처음부터 → interrupt 확인 → `POST /report/draft` → ack. 순서 체크포인트 → draft 저장 → ack.
  - approve: 완료면 ack만, 멈춤이면 `Command(resume=True)`, finalize 실패 뒤면 `ainvoke(None)`, 그 외(체크포인트 없음 등)는 15초 뒤 같은 본문 재발행 후 ack.
  - 실패: `BACKOFF_SECONDS=(5,15,45)`를 attempt 1·2·3 실패 뒤 대기로 쓰고, attempt<3이면 attempt+1 재발행, 3이면 `{원본, error}`를 report.dlq로(로그에도 error). 재발행은 publisher confirm 확인 뒤 원본 ack. 재발행 자체가 실패하면 원본 nack(requeue).
  - dlq: `POST /report_failed`. 연결 실패·5xx면 ack하지 않고 60초 간격 재시도, 4xx는 로그 후 ack.
  - 큐 이름·DLX 선언은 api `declare_topology`와 같다. 채널은 발행용(confirm) 1개 + 큐마다 prefetch 1 소비 채널.
- `rubric.py`: 조건 문법 `label_in`·`metric`(eq/lte)·`all`, 한 조건 안의 label_in+metric은 AND, `only_if`. 근거는 충족 항목에만, 항목 조건에 쓰인 지표·레이블 근거만.
- `report.py`: 섹션(situation·label_texts 매핑·타입별 evidence·`context {prev_persona_message, card_at_t_min}`·`event_fired`·`no_record_reason`·`aux_facts`·`out_of_window_messages`), 평가표(항목 `id, text, auto, no_record_reason, reviewer, memo, evidence`, 응답 시간 항목은 `minutes`), `auto_total`, AI 활용(호출 없으면 used=false·"사용하지 않음", 있으면 LLM 한 문단 + 호출 인용·재사용(verbatim·edited) 근거). 근거는 collect한 이 세션 행에 있는 id만, item 근거는 카드 `evidence_types`로 거른다. alias·position.name·deliverable은 api GET 합성에 맡긴다.
- `llm.py`: gpt-4o-mini temperature 0, 타임아웃 30초, 재시도 2회(1·3초) 뒤 고정 문장. 테스트는 FakeLLM.
- `__main__.py`: heartbeat 루프와 소비자를 같은 루프에서, `AsyncPostgresSaver.setup()` 후 그래프 구성. `DATABASE_URL`의 `postgresql+asyncpg://`는 psycopg 형식으로 바꿔 쓴다.

## 수정 파일 (`services/report-worker/`)

- 추가: `report_worker/{api,config,consumer,graph,llm,report,rubric}.py`, `tests/{conftest,test_rubric,test_graph,test_dlq}.py`
- 수정: `report_worker/__main__.py`(소비자 연결), `pyproject.toml`(`psycopg[binary]` 추가: slim 이미지에 libpq가 없음, dev에 `pyyaml`: 테스트가 카탈로그를 읽음), `uv.lock`, `README.md`

## 남은 문제

1. `reports.usage` 실제 저장은 api 변경 전까지 안 됨(워커는 본문에 싣는 중).
2. `event_fired`는 대용 판단이다. 내부 API가 session_events를 주지 않아 "관찰 행이 있거나, 카드 시각 이후 event_id 달린 메시지가 있으면 발생"으로 본다. 관찰 행이 없고 그 뒤 카드 메시지도 없으면 조기 제출로 미발생 처리.
3. `window_missed`는 계약에 표기 형식이 없다. 지금은 관찰 `metrics.window_missed`가 true(또는 `{value: true}`)면 그 요소의 항목 전부를 사유 window_missed로 둔다. observe(agent-session)가 다른 형식을 정하면 맞춰야 한다.
4. 지표 null의 사유: aux 기반 지표가 분류 실패로 null이면 classify_failed, 레이블이 정상인데 지표가 null이면 no_activity로 둔다. rubric.md 사유 목록에 정확히 맞는 것이 없어 고른 값이다.
5. 금지어 목록은 워커 자체 정규식(합격·불합격·탈락·당락·순위(우선순위 제외)·등수·석차·상위 n%·n점·점수·채용 추천/권장). guard_patterns.yaml을 재사용하지 않았다(대상과 목적이 다름).
6. `rubric.elements[].items[]`에 `adjusted`는 넣지 않았다(api가 GET 때 병합). `no_record_reason`·`minutes`·evidence `change_ratio`·doc_view `summary`는 계약 예시에 없는 추가 필드다.

## 변경 요청

1. **contracts.md / api-admin**: `POST /internal/sessions/{id}/report/draft` 본문에 `usage`(선택, object)를 추가하고 `reports.usage`에 저장. 현재 `ReportIn`은 `content`만 받아 무시한다. 해시는 content에만 적용(usage 제외).
2. **contracts.md / api-admin**: `GET /internal/sessions/{id}`에 `events: [{card_id, element, status, due_at, fired_at}]`(또는 별도 `GET .../events`)를 추가. 워커의 `event_fired`·카드 실제 시각·window_missed 판단을 대용 추정 없이 하려면 필요하다. 반영되면 `report.event_fired`만 바꾸면 된다.
3. **contracts.md / agent-session(observe)**: window_missed를 관찰 행에 남기는 형식을 정해 달라(제안: `metrics.window_missed: {value: true, evidence_ids: []}`).

## 다른 트랙에 알릴 것

- **api-admin**: 워커는 draft 본문 `{content, usage}`를 보낸다. final은 checkpoint의 draft 그대로라 해시가 같다. dlq의 `report_failed` error 문자열은 `"<큐> attempt <n>: <예외명>: <메시지>"`. draft 재전달(멈춘 thread의 generate 재수신)은 같은 content로 다시 POST한다(api가 report_ready 멱등 응답).
- **agent-session(observe)**: 워커는 관찰 `metrics[name]`을 `{value, evidence_ids}`로 읽는다(값만 있어도 받음). label은 카드 labels·`no_evidence`·`unclassified`·null을 구분한다. evidence id가 이 세션 messages·document_revisions·doc_views·assistant_calls에 없으면 리포트에서 빠진다. 창 밖 메시지 표시는 `meta.classification.related_card`와 관찰 행의 window_start/end로 계산한다.
- **web-admin**: 섹션에 `no_record_reason`(no_activity·classify_failed·event_not_fired·window_missed), 항목에 `no_record_reason`과 응답 시간 항목의 `minutes`가 있다. revision 근거는 `summary "n번 파트 수정(t분)"`과 `change_ratio`, doc_view 근거는 `summary "<문서명> 열람(t분)"`.
- **e2e-runner**: thread id는 `report:{session_id}`이고 워커 로그에 `report <id> draft saved (thread …)`·`final saved` 줄이 남는다. 재시도 백오프는 5·15·45초라 api 장애 주입 시 DLQ까지 약 65초 걸린다.
- **foundation/orchestrator**: 워커 `pyproject.toml`에 `psycopg[binary]`(런타임)와 `pyyaml`(dev)을 더했다.
