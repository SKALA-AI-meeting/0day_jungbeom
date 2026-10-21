# api 트랙 완료 보고 (2026-10-21)

- 브랜치 `track/api`, 기준 `track/debate` 38cf9ef. WIP ead2c4e는 아래 두 커밋으로 합쳤다(push 안 함).
  - 58fd7b6 코드(`services/api/app/`, `services/api/README.md`, `infra/.env.example`)
  - 4df610b 테스트(`services/api/tests/`), 이 보고서, `api-cr.md`
  - 이 보고서가 든 마지막 커밋: agent-dev 요청·오케스트레이터 결정 CR-A1 반영(아래 "후속 반영")
- 검증 방식: 전부 **mock + 격리 DB**다. 격리 DB는 기존 conftest 방식(infra postgres 127.0.0.1:5432에 실행마다 `dayzero_test_<랜덤>` 생성·삭제). runner·의도 분류·큐·시계는 대역(`tests/kit.py`: 기록 runner, 고정 의도 분류, `MemoryPublisher`, `FakeClock`). LLM·MCP·RabbitMQ·실 스택은 쓰지 않았다. 15분 실 스택 확인은 하지 않았다(사용권 없음).

## 완료 조건

| 조건 | 명령 | 결과 |
|---|---|---|
| api 테스트 | `cd services/api && uv run pytest -q -m "not live"` | 68 passed (27초) |
| 루트 테스트 | `make test`(전 서비스 + web) | root 125, api 68, debate-mcp 15, rag-mcp 10, assessment-mcp 20, report-worker 28, web 25 통과(web은 기대 실패 목록 제외) |
| 루트 lint | `make lint` | exit 0 (ruff check·format, web eslint·prettier) |
| 계약 테스트 C1~C4·C6·C8·C9·C10 | 위 명령에 포함 | 모두 통과(아래 표) |

## design.md 완료 기준 ↔ 테스트

| 기준 | 테스트(파일::함수 요지) | 결과 |
|---|---|---|
| C1 지원자 확정 | `test_c01_confirm`: 프레임 순서 `slot.confirmed→phase.changed→timer→materials.opened`·seq 연속·support 스냅샷·누적 마감 28분, 후보 밖 422 `invalid_keyword`, 다른 단계 409 `phase_not_open`, 같은 값 200·다른 값 409 `slot_confirmed`, 키·정규화 라벨 연결과 불일치 null(분류 호출 0), 동시 확정 하나만 | 통과 |
| C2 AI 합의 채우기 | `test_c02_consensus_fill`: (a) 같은 run 안 fill → `filled_by` p3·공지 seq 5 `consensus_fill`·WS `message.new→slot.confirmed→phase.changed→timer`, 같은 run_id 재호출은 기존 칸·공지, 재실행은 skipped·공지 1건 (b) AI 지지 추가 뒤 같은 run_id로 성공 (c) 철회 뒤 409 `no_consensus`·칸·공지·단계 변화 없음, 검사 순서 `phase_not_open` | 통과 |
| C3 시간 초과 | `test_c03_timeout`: 마감 전 틱 변화 없음, 마감 틱에 p3 고정 문장(R7)+`slot.confirmed{timeout, p3}`·`phase.changed{timeout}`, 지지 최다 안, 그래프 자극은 다음 단계 `phase_started`뿐, 안이 없으면 `default_keyword`. 선택 4단계는 `test_consensus` | 통과 |
| C4 침묵 초대 | `test_c04_silence_invite`: 첫 idle `deferred` → 다음 틱 새 run_id로 재enqueue → p3 `is_invite` 1건, 두 번째 초대 409, `origin` invited→spontaneous, 입력 중 보류·대기 중 중복 없음 | 통과 |
| C6 제출·자동 제출 | `test_c06_submit`: 토론 단계 제출 409 `phase_not_open`, 제출 → completed·`ended_at`·`session.ended{submitted}`·`report.generate{eval_round:1}`, 멱등, 제출 뒤 message.send `session_ending`, `ends_at` 자동 제출 `auto_submitted`·`session.ended{timeout}` | 통과 |
| C8 유형 비노출 | `test_c08_persona_hidden`: 입장·동의·시작 전/후 `/state`·자료·WS 프레임 전부 유형 문자열 0건, 관리자 리포트·디브리핑 `seats[].persona_type` 있음 | 통과 |
| C9 입장·재입장 | `test_c09_entry`: GET `session_id`·`default_display_name`, consent 표시 이름 정리, 시작 전 `/state` 이름·아바타·`keyword_options`, `/assets` 200, resume `session_id`, 종료 뒤 `debrief_token`으로 디브리핑(`my_messages` ≤ 3, `appeal_contact`) | 통과 |
| C10 검토 | `test_c10_review`: 422(`memo_required`·`invalid_dimension`·`duplicate_dimension`·`invalid_input`), 승인·`report.approve{eval_round}`, 같은 본문 200·다른 본문 409 `already_reviewed`, final 해시 불일치 409 `draft_mismatch`·같으면 reviewed, `adjusted_level` 병합·`review{reviewer_name, reviewed_at}`, 목록 칩 조정 반영·총점 없음 | 통과 |
| 조립 | `test_scenario`: 강한결·윤하람·서지안, 카드 6·차원 19, 아바타 이름 유형 없음, 15분 오프셋 0.75/0.5/1.25(≥ 20초), 누적 마감 60·15 | 통과 |
| SessionService | `test_lifecycle`: start(칸 3·초안·키워드 안내·phase_started, 멱등), 취소·실패 `ended_at`, 리포트 실패 → regenerate `eval_round` +1, reissue 토큰 교체·옛 링크 404, 재응시 같은 별칭·진행 중 422 `invalid_previous_session` | 통과 |
| 메일박스 | `test_mailbox`: 페르소나 LLM 연속 실패 3회 failed(session), 직렬 소비(동시 1), 메시지 generation = 저장 값, ack이 분류 전, 낡은 자극 skipped여도 분류·안 반영, 밀린 사이 단계가 바뀐 메시지는 그 단계 카탈로그로 분류, `stale_generation`, finished 재실행 안 함, 200초 started 재실행, recover 재큐, ports.enqueue 새 run, typing 6초 만료, 분류 실패 other·low 지지 없음 | 통과 |
| 스케줄러·카드 | `test_scheduler`: 마감 임박 1건, card_due 미전달이면 새 uuid4로 재enqueue·대기 중 중복 없음, 기준안 잠금(지원자 지지 안이 아닌 첫 안, proposer p1, 불변), `card_ids` 두 개가 두 카드 `delivered_seats` 갱신·남은 담당만 재enqueue, 재기동 recover 시 미처리 마감 채우기·outbox 재발행 | 통과 |
| 자료·어시스턴트·비용 | `test_lifecycle`: 키워드 전 잠김·423, 확정 뒤 그 키워드 자료만, catalog_version 1벌 시드, 열람 기록, 60회 초과 429, 어시스턴트 비용 → `debate_cost_usd`(cost_left ≤ 0), 리포트 비용은 `cost_usd`에만 | 통과 |
| 관리자·내부 | `test_lifecycle`·`test_internal`: 기업 간 격리 404, 요소 선택·30분 422, 내부 토큰 없음 401·공개 포트 `/internal` 404, `tail`, rubric 창 원본, `position.name`, 안 멱등·최초 제안자 보존, 관찰 멱등, completed 뒤 내부 쓰기 409, evaluations 멱등·422·`evaluation_runs` 1행, 사실 지표, record `ref`, purge(`ended_at`+90일, completed·cancelled, 초대 행은 남김) | 통과 |
| 테스트 API | `test_test_api`: start_at keyword·problem·solution·proposal 시드 재생 뒤 `/state` 그 단계 시작·앞 칸 confirmed·WS seq 1..n = `ws_seq`·generation 연속·마지막 `phase_started`만 그래프로, `ended`는 completed·`debrief_token`·`admin_report_url`·큐 발행, `advance{to: card:…}` 뒤 card_due, `advance{to: deadline}` 뒤 시간 초과, 둘 다 주면 422, 꺼져 있으면 404 | 통과 |

## 후속 반영 (agent-dev 요청, 오케스트레이터 CR-A1)

- 기준안 잠금은 api 몫(CR-A1): 메일박스가 `card_due`를 꺼낼 때 그래프 실행 전에 한 트랜잭션으로 `session_cards` 행을 만들고 문제 상황 카드면 `locked_option_id`를 잠근다(이미 구현돼 있었음). `test_scheduler`가 C5 단언(지원자가 P1 지지 → 잠금 = P2, proposer p1, 이후 불변)과 DebateState `card_progress[].locked_option_id` 노출을 확인한다. `docs/api/design.md` "세션 메일박스"에 한 줄 추가(사전 승인).
- `AGENT_RUNNER` 기본 `session`, `services/context.py`는 `app/agent/factory.py` 입구 사용(이미 반영).
- 의도 분류 호출에 선택 인자 `message_id`·`instructions`(`positions.scenario.prompts["intent.md"]`)를 넘긴다. G-F stub은 이 인자를 몰라 예외 → 계약 폴백이 되므로 agent 병합 전에는 결과가 같다.
- 페르소나 LLM 실패: `RunResult.error`가 `persona_llm_unavailable`로 시작하면 `sessions.llm_failures` +1, 정상 run이면 0, 3회면 `failed(session)`·`ended_at`·WS `session.ended{failed}`(`test_mailbox::test_three_persona_llm_failures_fail_the_session`).

## CR-A1 (기준안 잠금) 구현·테스트 상태

**구현됨·테스트됨.** api 메일박스(`app/mailbox.py` `process`)가 `card_due`를 꺼내면 그래프(`AgentRunner.run`) 실행 **전에** 한 트랜잭션으로 `debate.lock_lead_option`을 부른다: `session_cards` 행 생성, 문제 상황 카드면 `locked_option_id`를 "지원자 현재 지지 안이 아닌 첫 시나리오 안"으로 한 번만 잠그고, 그 안 행이 없으면 proposer = 카드 첫 담당 자리(p1)로 만든다. 낡은 자극(단계가 바뀜)이면 잠그지 않고 skipped. 검증: `tests/test_scheduler.py::test_problem_cards_lock_lead_and_joint_message_delivers_both` — 지원자가 P1 지지 → 잠금 = P2(`water_p2`, proposer p1), 두 카드 같은 기준안, 이후 불변, DebateState `card_progress[].locked_option_id` 노출(C5 api 쪽 단언).

## CR-2·리뷰 비차단 반영 (마지막 두 커밋)

- CR-2(승인): 계약 픽스처를 S1 형태로 — `internal_rubric`(cards `stage_id`·`window` 객체), `internal_assistant_calls`(`request`·`response`), `internal_session`(`position.name`), `state_*` 5개(`keyword_options`), `internal_test_session`(+request: `phase`·`start_at`). `report.review` 형태를 `{reviewer_name, reviewed_at?}`로 좁힘(예시는 draft라 null 유지). web mock 사본 바이트 동일(web prettier 설정). `tests/contract_shape.py` 형태 갱신, assessment-mcp `card_window`를 계약 객체(`start: stage_start|card_message`, `end: stage_end:<phase>|submit`) 해석으로 바꾸고 옛 문자열 분기 제거(기존 `test_session_record_assembled_in_contract_shape`가 창 4종을 모두 대조하므로 테스트 추가 없음). web 컴포넌트 수정 없음.
- 리뷰 비차단: review `adjustments` 항목이 객체가 아니면 422 `invalid_input`, card_due 재enqueue 상한(같은 카드 마지막 run 이후 30초 간격·최대 3회, 넘으면 로그만, `test_card_due_retries_are_spaced_and_capped`), `/internal/test/*`는 라우터 의존성으로 본문 검증 전에 404.

## S1 확정분 반영

State `keyword_options`, 내부 messages `tail`, rubric `cards[].window` 원본(+`stage_id`, `window_code` 제거), 409 세부 코드, Report `review{reviewer_name, reviewed_at}`(승인 시각을 `reports.reviewed_at`에 기록, final은 유지), `assistant_calls`의 `request`·`response`, 내부 세션 `position.name`, 테스트 API(`services/test_sessions.py`).

## 수정 파일

- 공용(사전 승인): `services/api/app/config.py`(`AGENT_RUNNER` 기본 `session`, `llm_fake`), `infra/.env.example`(`LLM_FAKE=0`, `AGENT_RUNNER=session`, `ENABLE_TEST_API` 설명). compose는 env_file로 충분해 바꾸지 않았다.
- api: `app/{run,main,hub,mailbox,queue,scheduler}.py`, `app/routers/*`, `app/services/*`(신규 `budget`·`timeout`·`test_sessions`·`purge`, 삭제 `locks`·`messages`·`runs`·`states`), `services/api/README.md`.
- 테스트: `services/api/tests/conftest.py`(픽스처 추가, 기존 격리 방식 유지), `tests/kit.py`, `tests/test_*.py` 15개.

## 남은 문제

- 실 WebSocket 엔드포인트(토큰 close 4401·4403, 교체 4000, connection_gaps)는 단위 테스트가 없다. 수신 처리 `handle_send`와 hub 송신 큐만 검증했다(web-integrate·e2e에서 확인 필요).
- 15분 실 스택 1~2개(design.md "시간")는 하지 않았다. 시간 로직은 가짜 시계 단위 테스트로만 봤다.
- `/state`의 `session.phase`는 completed 세션에서 `proposal`로 내려간다(WIP 그대로). 계약에 completed 예시가 없어 두었다.
- design.md 구조표의 `office_clock.py`·`runs.py`는 만들지 않았다(오피스 시각은 web이 변환하고 api에서 쓰는 곳이 없음, run 기록은 `phases.queue_run`·`mailbox`).
- `advance{to: idle}`은 메시지 시각을 당기지 않으므로 지원자가 그 단계에서 이미 말했으면 "단계 절반 무의견" 조건 시점으로 당긴다(의견을 냈으면 침묵 초대 조건에 닿지 않는다).
- 시드 step 문법이 문서에 없다(CR-1).

## agent 트랙에 알릴 것

- `AGENT_RUNNER=session`이면 api가 `app.agent.factory`의 `db_scenario(session_factory)`, `build_debate_runner(settings, scenario, ports_for)`, `build_assistant_runner(settings, scenario)`와 `app.agent.llm.make_llm("intent")`를 부른다(`services/context.py` `build_context`, agent WIP 0b4cd1b의 시그니처와 같음). 이름이 바뀌면 알려 달라.
- 의도 분류는 메일박스가 `intent.classify(llm, message, phase=, catalog=, options=, recent=, seats=)`로 부른다(G-F 시그니처). 실패는 api가 계약 폴백으로 바꾼다.
- `RunResult.usage.cost_usd`를 메일박스가 `sessions.debate_cost_usd`·`cost_usd`에 더하고, 어시스턴트는 `AssistantResult.usage.cost_usd`를 더한다. DebateState `cost_left`는 `services/budget.py`(`SESSION_COST_HARD_USD` env, 기본 2).
- card_due 첫 처리 때 api 메일박스가 `session_cards` 행을 만들고 문제 상황 카드면 기준안을 잠근다(proposer = 카드 첫 담당 자리). 그래프 `cards` 노드는 DebateState `card_progress`의 `locked_option_id`를 읽으면 된다.
- `honesty_credit` 관찰은 api가 남기지 않는다(계약대로 그래프 `phase_started` 실행의 `record_observation`).
- 테스트 API 재생은 그래프를 부르지 않고, 끝난 뒤 현재 단계 `phase_started`(run_id `uuid5(session, "phase:"+phase)`)만 메일박스에 넣는다.

## CR

`docs/handoff/reports/api-cr.md`: CR-1 단계 시드 step 키 → 오케스트레이터가 testing.md 정본으로 올림, CR-2 → 이 트랙이 처리(위), CR-3 → 현 구현(모든 구두점 제거·공백 접기) 유지, 계약 문구는 오케스트레이터가 명시.
