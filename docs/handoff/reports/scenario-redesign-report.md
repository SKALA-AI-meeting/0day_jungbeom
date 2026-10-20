# scenario-redesign 보고서 (P1)

브랜치 `track/scenario-redesign`, 기준 커밋 2c2342e(main eeda2a1 + 브리프), 계약 커밋 eeda2a1.

## 관문 1: 미션·스키마

### 완료 기준과 결과

| 기준 | 명령 | 결과 | 검증 방식 |
|---|---|---|---|
| 조립 결과가 `scenario-model.md` 수치와 일치(5개·3개·1개 L=120, 5개 L=6, 공개 시각, vars, releases_at_start) | `cd services/api && uv run pytest -q tests/test_scenario.py::test_assembled_timeline_matches_scenario_model` | 통과 | 고정 입력(카탈로그 파일) |
| 카드 7장의 레이블·aux·근거 타입·항목 id가 `rubric.md` 단일 표와 같고 요소당 항목 4개 | `uv run pytest -q tests/test_scenario.py::test_catalog_names_match_rubric_table` | 통과 | 고정 입력 |
| catalog_version = 미션 폴더 전체 해시(프롬프트 픽스처 한 줄만 바뀌어도 바뀜) | `uv run pytest -q tests/test_scenario.py::test_catalog_version_hashes_whole_mission_folder` | 통과 | tmp 복사본 |
| `schema.sql`이 data-model 테이블 27개·핵심 컬럼·관찰 카드 키를 갖고 적용됨 | `uv run pytest -q tests/test_schema.py` | 통과 | 격리 DB(`dayzero_test_<랜덤>`, 끝나면 DROP) |
| lint | `uv run ruff check . && uv run ruff format --check .` | 통과 | — |
| YAML 전부 파싱 | `uv run --project services/api python -c "...yaml.safe_load(glob scenarios/**/*.yaml)"` | 통과 | — |
| guard 예문 hit/miss | 임시 스크립트(그룹 패턴·strict·unless로 examples 확인) | 통과 | — |

관문 1 커밋 시 catalog_version: `f42f50d1536e1b1f`, 리뷰 반영 뒤 `e915f2faba0177ff`. 관문 2·3에서 미션 파일이 바뀌면 최종 값은 관문 3 절에 다시 적는다.

### 만든 것·바꾼 것

- `scenarios/missions/planning/`
  - `mission.yaml`: 이름·deliverable·회사·`candidate_role: primary`(주담당)·parts(3번 depends_on [2])·default_division·division_min(+422용 문장)·final_template·킥오프 기본 가정·문서 목록·관리자 안내 문안/FAQ(픽스처 `admin_catalog.json` 값 그대로).
  - `cards.yaml`: timing(fixed 비율·middle 규칙·middle_order), 흐름 카드 4장(kickoff·division·review·report_request), texture midpoint_draft(계획성 미선택일 때만), 요소 5개 → 카드 7장. 요소마다 meaning·how_we_see·if_unselected(픽스처 문구). 카드마다 name·slot·brief(·text)·labels·label_texts·aux·evidence_types·metrics·rubric(when·only_if·basis·evidence_types·pilot_value)·situation·debrief. 승격은 `flow_card`(planning_division→division, honesty_report→report_request), collab_disagree는 `attach_to: review` + `fixed_opinions` 2개 + `target_rule`, adaptability_change는 새 내용(48시간 후속 모임 하나로·이번 분기 출시) + `change_targets`, collab_help는 `finalize_metrics: [promise_kept]`.
  - `persona.yaml`: 동료 values 4개(근거·먼저 공유·한 번 반대 후 따름·사용자 관점), must, must_not_preempt 7개(창별), in_window_help, identity, must_not / 팀장 values·DM 규칙·추가 자료 고정 대응 / 어시스턴트 범위.
  - `documents/`(git mv), `company_intro.md` 한 문장을 문서 주고받기 방식으로 고침.
  - `prompts/`(git mv): colleague·manager 재작성(주담당, 문서 주고받기, 선점 금지 7개, 팀장 DM 상시), common_rules·assistant 호칭·문서 범위, observe_labels 카드 7장(레이블·aux·근거 타입·우선순위·예시), guard_patterns 요소명·호칭·미래 예고 패턴, fixtures: preemption 6건, **manager_dm 5건(새)**, context_leak 6건(보내지 않은 문서 1건 추가), grounding 도구 목록·범위 밖 질문.
- `scenarios/catalog.yaml` 삭제, `scenarios/e2e/` 초기 대본 7개(all_five·one_element·division_refuse·restart·no_assistant·assistant_reuse·early_submit)와 형식 README. 옛 대본 4개 삭제.
- `scenarios/version.py`: `catalog_version(mission_id, scenarios_dir=None)` = 미션 폴더 전체(경로+본문, 점 파일·`__pycache__` 제외) sha256 앞 16자리.
- `infra/db/schema.sql`: data-model대로 다시 씀. positions.mission_id·요소 1~5, invites (position_id, alias) unique, sessions reporting·deadline_at·reported_at·completed_at, session_events or_on_submit·document_missing, messages manager_dm, agent_runs division, documents·document_revisions(doc_id 기준)·document_versions·document_shares·document_opens·final_document, tasks(assignee null·order·due_min·depends_on), task_events, observations(card_id 키·aux·facts·updated_run_id·updated_at), connection_gaps, assistant_reuse(doc_id·applied), debrief_surveys, reports unmet·reviewer_no_record·reviewer_name, rubric_adjustments card_id·reviewer_name, report_notes. document_states 삭제.
- `services/api/app/services/scenario.py`: 미션 폴더 로드·조립·expand를 새 카탈로그로. **조립을 관문 1로 당겼다**: catalog.yaml 삭제와 동시에 깨지고, 카탈로그 수치를 검증하는 유일한 테스트라서.
- 테스트: `services/api/tests/test_scenario.py`(재작성 3건), `test_schema.py`(새 1건).

### 의도적으로 깨진 테스트 (관문 2·3에서 고침)

옛 요소 id·옛 스키마·`catalog.yaml` 경로를 쓰는 코드라 지금은 실패한다. 관문 1 범위 밖.

| 서비스 | 결과 | 원인 | 고칠 관문 |
|---|---|---|---|
| api | 19 failed, 9 errors (관문 1 테스트 4건 포함 9 passed) | tables.py·라우터·SessionService·scheduler·agent 테스트가 옛 스키마(document_states 등)·옛 요소 id·`scenarios/prompts` 경로를 씀 | 2 |
| rag-mcp | 3 failed | `scenarios/documents` 경로, `catalog_version(scenarios_dir)` 시그니처 | 2 |
| report-worker | 6 failed, 10 errors | conftest가 `scenarios/catalog.yaml`을 읽음 | 3 |
| business-mcp | 11 passed | — | 2(도구 추가) |

### 남은 문제·질문

1. 분량: 오케스트레이터가 PRD를 1~2쪽으로 고쳐 종결(main b9e9763).
2. 지연 알림 "약 10분": 계약의 고정 문장을 유지. 6분 대본의 지원자 발화는 "공개가 늦어진대요"로 바꿨다.

### 관문 1 리뷰 반영 (REVIEW.md ## 관문 1)

main(c9b956d)으로 rebase한 뒤 반영했다.

| 항목 | 반영 |
|---|---|
| A1 | `tasks.due_min` int. `test_schema.py`에 `data_type == integer` 검사 추가 |
| A2 | `all_five` 최종본 1번 가져오기를 v1로(1번은 한 번만 보냄) |
| A3 | `plan_stated_schedule.basis: by_source`(contracts c9b956d). 테스트는 이 항목만 by_source 허용. 워커 판정은 관문 3 |
| A4 | `observe_labels.md`: 행동 레이블은 근거 1개 이상, 하지 않음 레이블은 허용 타입 활동이 없으면 `evidence: []`(0점은 근거 행 불필요). 예시에 evidence 표기 |
| B1 | C4 → `restart`(방향 변경 뒤 오탈자만), C5 → `one_element`(`inject` send_document 2회 실패), C6 → `early_submit`(제출 → disconnect/resume/state → 팀장 DM 보고). `scenarios/e2e/README.md`에 6건↔대본 인수표 |
| B2 | 대본 발화의 "10분" 제거, C3 collab_help 답을 "1분 뒤에 DM 드릴게요"로 단일화하고 사례 기준 지시는 분업 단계로 옮김(3c "재참여" 유지) |
| FAQ | `mission.yaml candidate_faq` = PRD F-02 4문항 + 기존 2문항, `tests/fixtures/contracts/admin_catalog.json` 같은 값으로 갱신(사전 승인) |

### 변경 요청

- **[반영됨, 사전 승인] `tests/fixtures/contracts/admin_catalog.json`의 `candidate_faq`**에 PRD F-02 4문항(AI가 평가하나요·기록은 어디에·결과를 알려 주나요·이의 제기)을 앞에 추가(6문항). 영향: web 관리자 mock(`apps/web/mocks/fixtures/admin`)도 같은 값으로 맞출 것(web-integrate).
- **[요청] `docs/agent/design.md` 레이블 규칙**: "레이블이 있으면 evidence가 1개 이상(없으면 unclassified로 강등)"을 "행동 레이블만 1개 이상, 하지 않음 레이블은 허용 타입 근거가 없으면 빈 배열 허용"으로 정합화(A4 지시와 맞춤). 영향: agent-session observe 강등 규칙.
- catalog_version 비교(관문 2): 실제 값이 `catalog_version("planning")`과 같은지 검증한 뒤 그 값만 정규화하고 나머지를 픽스처와 비교.

### 다른 트랙에 알릴 것

- agent-session: scenario JSON의 카드 필드명(`flow_card` 승격은 조립에서 끝나 있음, `window_start_min: 0`, `sends_document`, `effects.release_at_min`, `fixed_opinions`·`target_rule`, `change_targets`, `finalize_metrics`, `system_text`·`after_timeout_note`, `colleague_greeting`), `vars`(`interview_expected_time`·`release_time`·`final_length`, `{colleague_first_part}`는 런타임 치환), `persona`는 scenario에 통째로 복사. 프롬프트 경로는 `scenario["prompts"]`의 키(`colleague.md` 등, 미션 폴더의 `prompts/` 기준).
- e2e-runner: `scenarios/e2e/README.md`의 step 키(board·share·open·import·view·restart·disconnect)는 초기본 제안이다.

### 후속 인수자에게 넘길 것 (관문 3에서 최종)

catalog_version, 7카드 레이블(`cards.yaml`·`observe_labels.md`), fixed_opinions 2개, 선점 6건·팀장 DM 5건 픽스처, 대본 7개.

## 관문 2: API·도구 계약 검증

기준: 관문 1 리뷰 반영 커밋 위(main c9b956d로 rebase). 검증은 모두 **mock + 격리 DB**(FakeAgentRunner·FakePublisher, 테스트마다 임시 DB `dayzero_test_<랜덤>`, 끝나면 DROP). 실제 스택·LLM은 쓰지 않았다.

### 완료 기준과 결과

| 기준 | 명령 | 결과 | 검증 방식 |
|---|---|---|---|
| api 전체 | `cd services/api && uv run pytest -q -m "not live"` | 85 passed | mock·격리 DB |
| business-mcp | `cd services/business-mcp && uv run pytest -q` | 9 passed | api mock(httpx MockTransport) |
| rag-mcp | `cd services/rag-mcp && uv run pytest -q -m "not live"` | 10 passed | api mock·격리 DB·가짜 임베더 |
| lint | `uv run ruff check . && uv run ruff format --check .` | 통과 | — |
| report-worker | `cd services/report-worker && uv run pytest -q` | 6 failed·10 errors(관문 3 대상, `catalog.yaml` 경로) | — |

`docs/api/design.md` 완료 기준 줄별:

| 줄 | 테스트 |
|---|---|
| foundation: 모델·스키마(document_revisions·connection_gaps·completed_at·deadline_at) | `tests/test_schema.py::test_schema_has_data_model_tables` |
| foundation: SessionService 전이 전부·멱등(reporting·cancelled·regenerate) | `tests/test_session_service.py` 3건 |
| foundation: 시작 시 tasks 5행 null·지원자 문서 5개·최종본 | `test_session_service.py::test_full_lifecycle_and_idempotency` |
| foundation: 조립 수치 | `tests/test_scenario.py::test_assembled_timeline_matches_scenario_model` |
| foundation: 메시지→내부 저장→hub | `tests/test_message_flow.py` |
| api-admin: 계약 예시대로·격리·elements/mission 422·403·승인 전 final 409·재초대 조건·regenerate·시작 후 cancel·목록 세 수/시각/이메일/활동·notes 값 불변·record ref·honesty_facts·send 멱등 | `tests/routers/test_admin.py` 6건, `tests/routers/test_internal.py` 5건 |
| api-candidate: 엔드포인트·WS(ack·증분·재연결)·보내기→문서 카드·버전·자동 저장 revision·공유 안 된 버전 404·가져오기 출처·보드 확정·조기 제출·제출+5분·completed_at·reporting resume·connection_gaps·만료 발행·재시작 재실행·미발행 재발행·6분 세션 ±10초 | `tests/routers/test_candidate.py` 4건, `tests/test_candidate_ws.py` 2건, `tests/test_scheduler.py` 6건 |

**생산자 응답 = 공용 픽스처**: api 테스트가 `tests/contract.py`의 `assert_contract`로 실제 응답을 `tests/fixtures/contracts/*.json`과 비교한다(키 집합·값 종류 일치, 계약의 `키?` 선택 필드와 meta·metrics·aux 같은 자유 객체, 저장 형식 일부만 보이는 `scenario` 하위는 느슨하게). 비교한 픽스처: candidate_entry(·_completed), candidate_session_token, candidate_start, state, state_reporting, documents, document, task, my_document_save, my_document_share, document_open, final_section_import, my_documents, assistant_response, submit, debrief, debrief_survey, ws_client_frames, ws_error, ws_session_replaced, internal_session, internal_messages, internal_classification(요청), internal_division_put(요청)/internal_division, internal_board, internal_task_events, internal_docs_send, internal_docs_shared, internal_docs, internal_document_revisions, internal_documents, internal_release, internal_honesty_facts, internal_doc_views, internal_assistant_calls, internal_assistant_reuse, internal_complete, internal_report_draft·usage·final·failed, internal_test_session, observation_collab_help(요청)·observation_created, internal_observations, admin_auth_token, admin_position_created, admin_positions, admin_invite, admin_cancel, admin_candidates, admin_review_response, admin_report_notes, admin_record, admin_report_regenerate, report(합성 응답의 position·rubric·notes·connection_gaps·deliverable.final). `GET /admin/catalog`는 픽스처와 **값까지** 같다. business-mcp는 `mcp_tools.json`의 11개 도구 입력으로 불러 경로·본문·출력이 픽스처와 같은지 본다.

**catalog_version**: 실제 값이 공용 함수 `catalog_version("planning")`과 같은지 먼저 확인하고(`test_internal.py`, `test_admin.py`는 16자리), 나머지 형태만 픽스처와 비교한다(픽스처 예시값 12자리는 그대로 둠).

### 최소 테스트 6건(scenario 열, 고정 입력)

| 사례 | 파일::함수 | 확인한 것 |
|---|---|---|
| ① 보드만으로 분업 확정 | `services/api/tests/routers/test_candidate.py::test_board_only_division_confirms` | 담당 없는 5행 → PUT → division(decided_by=candidate)·task_events·WS division.confirmed·동료 division 자극(agent_runs, ref_ids=확정 task_event). 위반 조합의 마지막 PUT은 422 invalid_division이고 저장 안 함 |
| ② 카드 전 계획 | `test_candidate.py::test_plan_before_card_keeps_board_history` | 분업 카드(10분) 전에 정한 담당·순서·언제까지와 이후 재배정이 각자 시각으로 task_events에 남고 decided_at은 첫 확정 그대로 |
| ③ 창 밖 약속 이행 | `tests/routers/test_internal.py::test_observations_patch_is_idempotent` | promise_kept=null 관찰 저장(같은 키 재요청 같은 id) → PATCH metrics_patch가 그 지표만 바꾸고(창 밖 메시지 근거) 같은 run_id 재요청은 멱등, 없는 행 404. 워커 소비는 관문 3 |
| ④ 무관한 편집 | `test_internal.py::test_unrelated_edit_keeps_revisions` | 오탈자만 고친 저장도 revision 스냅샷으로 보존, target_applied=false 관찰을 document 근거로 저장. "미충족(0)"은 워커 rubric 계산이라 관문 3 |
| ⑤ 문서 제공 실패 | `tests/test_scheduler.py::test_document_send_failure_marks_event`, `services/business-mcp/tests/test_tools.py::test_send_document_failure_is_upstream_unavailable` | MCP: api 장애면 1회 재시도 뒤 upstream_unavailable(retryable). api: 러너가 `RunResult.error="document_missing: …"`를 돌려주면 그 카드 행 document_missing=true, 3회 실패 → 카드 failed·세션 failed. 워커 사유는 관문 3 |
| ⑥ reporting 재접속 | `test_candidate.py::test_reporting_resume_restores_state`, `tests/test_candidate_ws.py::test_reporting_reconnect_over_ws` | 제출 → resume 200·새 JWT, state.session reporting·deadline_at(state_reporting 형태), WS 끊김에 connection_gaps 열림·재연결에 닫힘, 보고 대기 중 팀장 DM 메시지 수신, kind=report로 completed(completed_at=보고 시각), 이후 send는 session_ending |

### 바꾼 것

- `app/models/tables.py`: 새 스키마 1:1(documents·versions·shares·opens·final_document·task_events·connection_gaps·debrief_surveys·report_notes 등).
- `app/services/`: `session.py`(submit→reporting→complete, mark_reported, regenerate_report, cancel 확장, 제출 시 최종본 version 고정), `board.py`(보드·분업 확정·동료 상태), `documents.py`(자동 저장·보내기·열기·가져오기·동료 send·shared·정직 사실), `events.py`(카드 실행 1회, document_missing 기록), `releases.py`(공개 + notice "공개됨" 줄), `views.py`(회사 문서 목록·끊김 구간·전체 기록), `states.py`(상태 순서·SessionError), `messages.py`(reply_to_doc·shared_doc, reporting 중 수신), `reuse.py`(문서별 applied), `scenario.py`(list_missions).
- 라우터: `candidate.py`(계약 경로 전부, 어시스턴트 훅 `ctx.assistant`), `ws.py`(manager_dm·reply_to_doc 검증·끊김 구간), `internal.py`(계약 경로 전부), `admin.py`(catalog·positions mission_id·candidates 평탄화·invites 재초대 규칙·report 합성·review reviewer_name·notes·record·regenerate).
- `scheduler.py`: reporting 종료(보고 또는 deadline_at), 만료 자동 제출(submitted_at=ends_at), 지연 공개 notice 줄, division 자극 재실행.
- `app/agent/runner.py`: Stimulus `division`·`task_event_ids`, `DOCUMENT_MISSING`, `AssistantRunner`·`FakeAssistantRunner`. `run.py`: 기동 시 `runner.graph()`(있으면), 종료 시 `runner.aclose()`.
- `app/agent/` 최소 수정: 허용 도구를 계약대로(동료 search_documents·get_document·get_board·get_shared_documents, 팀장 search_documents·get_board·get_shared_documents), State `current_element`→`current_card`·`report_requested` 추가(18필드), 보드 블록이 보낸 문서(get_shared_documents)를 쓰고 호칭 주담당.
- business-mcp 도구 11개(조회 4·변경 7), rag-mcp `scenarios/missions/<id>/documents`·`catalog_version(mission_id)`·`reindex_documents {mission_id?}`.
- 공용: `Makefile` e2e 대본 경로 all_five, `scripts/seed.py` 요소 id, `infra/db/schema.sql` invites 별칭 unique 제거(아래 변경 요청).

### 판단과 계약 해석(리뷰 대상)

1. **관찰 window_start·window_end는 세션 분(t_min)**: 픽스처(`observation.json` 60.0)대로 받고 DB에는 started_at+분으로 저장, GET도 분으로 돌려준다.
2. **내부 `POST /complete`는 completed_at만 확정하고 나머지 종료는 백그라운드**: 러너가 세션 Lock을 쥔 채 MCP로 부르면 동기 종료가 교착된다. 응답의 completed_at은 최종값. 그래프가 부르지 않아도 분류 PUT(kind=report)이 reported_at을 남기면 스케줄러가 5초 안에 종료한다.
3. **문서 미제공 신호**: 계약에 이벤트 행을 바꾸는 내부 API가 없어, 러너가 `RunResult(ok=False, error="document_missing…")`로 알리면 스케줄러가 sends_document 카드 행에 표시한다(agent-session 인터페이스).
4. **오류 코드는 contracts.md를 따랐다**: 재초대 조건 위반 422 invalid_previous_session(api/design.md는 409), 리뷰 본문 오류 400 invalid_item·memo_required·duplicate_item(design.md "400 안 씀"). design.md 정합화 필요.
5. 내부 `GET /assistant_reuse`는 픽스처대로 applied true/false 행을 모두 돌려준다(비율 없음).
6. 확정 뒤 보드 재배정은 division.parts만 바꾸고 decided_by·decided_at은 처음 값을 유지한다.
7. 리포트 재생성은 남은 draft와 조정 행을 지운다(새 draft가 on_conflict로 막히지 않게). 세션 기록은 그대로.
8. `empty_sections`는 rubric.md 정의(본문이 빈 최종본 섹션 전부)를 따랐다. api/design.md의 "지원자 담당 파트" 한정과 다름.

### 변경 요청

- **[요청] data-model `invites (position_id, alias) unique`**: 재응시·재발행이 같은 별칭으로 이어지는데(픽스처 `admin_candidates.json` sess-2·sess-3) DB unique면 저장할 수 없다. 스키마는 인덱스만 두고 api가 409를 막는다(이전 응시를 잇는 previous_session_id면 같은 별칭 허용). data-model 문구 수정 요청.
- **[요청] api/design.md 정합화**: 위 판단 4(422/400), 8(empty_sections), `/state`의 `session.release_at_min`(계약 State에는 없어 넣지 않음, 회사 문서 목록의 release_at_min만).
- **[참고] 픽스처 값 차이**: `documents.json`·`internal_documents.json`의 제목("루프랩·모아런 소개", "회의록")이 미션 제목("회사·서비스 소개", "지난주 회의록")과 다르다. 형태만 비교하므로 테스트는 통과. 값을 맞출지 결정 필요(web mock 영향).

### 다른 트랙에 알릴 것

- **agent-session**: Stimulus `division`(task_event_ids, 보드 확정·재배정 때 api가 보냄), 문서 전송 실패는 `RunResult.error`를 `DOCUMENT_MISSING`으로 시작, 보고 감지는 분류 PUT(kind=report, 팀 채널·팀장 DM)이 reported_at을 남기고 종료는 스케줄러가 한다(그래프가 `/complete`를 불러도 됨). State 18필드(current_card·report_requested), 보드 블록 입력은 get_shared_documents. 제출 시 or_on_submit 카드는 api가 due_at을 당겨 Lock 안에서 바로 이벤트 run으로 실행한다(자동 제출이면 submitted_at=ends_at).
- **agent-assistant**: 훅 `AppContext.assistant: AssistantRunner`, `answer(session_id, prompt, call_id) -> AssistantResult(content, cited_docs, usage)`. api가 요청·응답 메시지(channel assistant)와 assistant_calls, 60회 429를 맡는다.
- **web-integrate**: 문서 카드 메시지 본문은 "n번 제목 vK"이고 표시는 `shared_doc`로 한다. 회사 문서 제목은 미션 값(픽스처와 다름, 위 참고). `/admin/catalog`의 FAQ 6문항.
- **e2e-runner**: `make_session.py`는 아직 없다(e2e-runner 소유). 내부 `POST /internal/test/sessions`가 mission_id를 받는다.

### 남은 문제

- report-worker 테스트(관문 3).
- business-mcp README 외 서비스 README의 옛 설명 일부(api README 없음)는 관문 3에서 함께 본다.

## 관문 2 반영

`REVIEW.md` 추적을 풀고(로컬 exclude) main `6a81c13` 위로 rebase한 뒤 반영했다. 검증은 mock·격리 DB.

| 항목 | 반영 | 확인 |
|---|---|---|
| G2-A1 보내기 원자성 | revision·version·문서 카드 메시지·share를 한 트랜잭션으로 커밋한 뒤 알림(`insert_internal_message`로 커밋 없는 insert 분리) | `tests/routers/test_internal.py::test_send_is_atomic_and_retry_safe`: 커밋 전 중단 → 0·0·0, 커밋 뒤(알림 중) 중단 → 재시도가 기존 결과, 각 1건 |
| G2-A2 취소·종료 경쟁 | cancel이 submit·complete와 같은 세션 Lock에서 상태 재검사, complete는 cancelled·failed면 아무것도 하지 않고 종료 직전 재검사 | `tests/test_session_service.py::test_cancel_after_start_never_makes_a_report`: 취소 뒤 complete → 리포트 발행 없음, 종료 중 취소 → Lock 대기 뒤 conflict |
| G2-A3 document_missing 복구 | 카드가 done이면 표시 해제 | `tests/test_scheduler.py::test_document_send_recovers_on_retry`(1회 실패 → done·attempts 2·false), 실패 지속은 기존 테스트 |
| G2-A4 import version null | 내 문서 현재 저장본, source_version null. 동료 문서 null은 404 | `test_candidate_rest_follows_contract` |
| G2-A5 catalog documents | missions[].documents[{doc_id,title}] | `/admin/catalog` = 픽스처(값 일치) |
| G2-A6 approving=done | GROUPS 수정 | `test_report_review_notes_and_record` 검토 제출 뒤 display_group=done |
| G2-A7 계약 비교 강화 | `tests/contract.py`: 계약 값(status·channel·type·sender 등) 어휘 검사, 필수 필드 null 거부(단계별로 비는 필드만 NULLABLE), `키?` 선택 필드는 호출마다 지정 | `tests/test_contract_check.py`: status "banana"·channel "banana"·status null·reporting의 deadline_at 누락이 모두 실패 |
| B1 카드 전후 이력 | 카드 전 결정과 세션 시계를 11분 당겨 실제로 카드(10분) 전후에 나뉜 이력을 확인 | `test_plan_before_card_keeps_board_history`: 카드 전 7건·카드 뒤 1건, decided_at 유지 |
| B3 별칭 중복 직렬화 | 초대 생성 때 채용 건 행 잠금 후 중복 검사 | 기존 중복 409 테스트 |
| B2 record_ref 값 대조 | 관문 3 | — |

추가 계약(main 6a81c13): POST share `note?`(본문은 note만, 없으면 빈 문자열, 테스트로 본문 확인), State `session.alias`. 리포트 카드 `window`는 관문 3.

web-redesign 요청: `state_start.json` 추가(시작 직후, tasks 전부 null), `admin_candidates.json` 묶음 5종(web mock의 sess-4~8 병합, 8행), `admin_positions.json` candidate_count=7(별칭 기준 사람 수), 회사 문서 제목을 mission.yaml 값으로(documents·internal_documents·document·state·mcp_tools 등), `debrief.json` scoring_notice(조정 전 값이라 오해·합격 여부를 정하는 값 아님)와 persona_note('values:' 제거)를 카탈로그 `debrief_texts`에서 생성하도록 함, 422 invalid_division 문장을 파트별 팀 사정 말투(`division_min_messages`), 동료 프롬프트·카드에 "분업 확정 뒤엔 확인 문장" "보낸 문서에 없는 문장은 인용하지 않음".

사용자 결정: 요소 5개 meaning·how_we_see·if_unselected를 명사형 UI 문구로 다시 씀(장면·시점 없음), `admin_catalog.json`도 같이.

`docs/api/design.md` 정합화(이번만 허용): 재초대 422 invalid_previous_session·별칭 409, 리뷰 본문 400 예외, empty_sections 정의, State 문구(alias·release_at_min 위치).

| 명령 | 결과 |
|---|---|
| `cd services/api && uv run pytest -q -m "not live"` | 89 passed |
| `cd services/business-mcp && uv run pytest -q` | 9 passed |
| `cd services/rag-mcp && uv run pytest -q -m "not live"` | 10 passed |
| `uv run ruff check . && uv run ruff format --check .` | 통과 |

catalog_version(반영 후): `b2cc7dd7baa915ca`(관문 3 끝에 최종 값).

기타: 관문 1·2에서 자동으로 접었던 주석·docstring 줄을 문단 단위로 다시 채웠다(내용 변경 없음).

## 관문 3: 워커·픽스처 인수

기준 커밋: main `37bed0b`(관문 2 반영 뒤 rebase. main 변경은 contracts.md의 보드 변경 요약 문구 1줄과 핸드오프 문서뿐). 검증은 전부 mock(FakeLLM·FakeInternalApi) + 격리 DB(api 임시 DB, 워커 체크포인터는 공용 DB의 임시 스키마) + 테스트 전용 접두사 RabbitMQ 큐. 실제 LLM·전체 스택은 쓰지 않았다.

### 완료 기준과 결과

| 완료 기준 | 명령·테스트 | 결과 | 검증 방식 |
|---|---|---|---|
| 워커 draft 형태 = `report.json`(워커 몫 키: summary·rubric·sections·ai_usage) | `services/report-worker/tests/test_report.py::test_draft_follows_report_contract` | 통과 | 5요소 120분 세션 고정 데이터 → `build_draft` → 루트 `tests/contract_shape.py`로 비교(어휘·null·목록 원소 종류별) |
| 카드 단위 평가표·summary 세 수 | 같은 테스트 | auto_total 18·2·0, 요소별 세 수 일치 | 값 단언 |
| basis·by_source | 같은 테스트(보드 근거 → metric), `test_by_source_basis_follows_evidence`(채팅만 → label) | 통과 | 관찰 행 조작 |
| label 항목 근거(met·unmet 무관) | 같은 테스트: 미충족 resp_proposed_alternative의 근거 = 판정 창 메시지 | 통과 | 값 단언 |
| record_ref·context·flag | 같은 테스트: share record_ref = {type, id, t_min}, document·doc_view는 null, doc_view `aux_fact`, prev_persona_message 문자열 | 통과 | 값 단언 |
| 섹션 `window` | 같은 테스트: planning_division {0, 30} | 통과 | 관찰 행 창(없으면 시나리오로 계산) |
| 정직 facts | 같은 테스트: `empty_sections` [3, 5] | 통과 | 내부 `honesty_facts` 그대로 |
| ai_usage.events(사실만, 라벨 없음) | 같은 테스트: t_min·applied_part, 키 6개 | 통과 | 값 단언 |
| 응답 시간 `minutes` | 같은 테스트: honest_reported_within_10m = 2.0 | 통과 | 값 단언 |
| 보드 변경 요약(main 새 계약) | 같은 테스트("1번 담당 → 지원자(12분)"), `services/api/tests/routers/test_candidate.py::test_plan_before_card_keeps_board_history`(전체 기록) | 통과 | 워커·api 같은 표기 |
| 카드 미발생·전달 지연 | `test_unfired_and_delayed_cards` | event_not_fired, window_missed | 이벤트·메시지 시각 조작 |
| 금지어·타 세션 근거 제거 | `test_forbidden_words_and_foreign_evidence_removed` | 통과 | 텍스트 필드만 검사, 원문 인용 유지 |
| 카드 7장 항목 값·사유 | `tests/test_rubric.py`(7장 + 사유 6종 + tally) | 8 passed | 순수 함수 |
| 재생성 체크포인트 | `tests/test_graph.py::test_regenerate_after_final_starts_new_thread`[memory·postgres] | 통과 | final 뒤 completed면 thread 삭제 → 다시 모은 데이터로 새 draft(15·1·4) |
| 큐·승인·재시도·DLQ 유지 | `test_graph.py` 나머지, `test_dlq.py` | 통과 | 기존 테스트, LLM 호출 0회로 기대값만 바꿈 |
| `make test` | 루트 | api 89 · business-mcp 9 · rag-mcp 10 · report-worker 24 passed, web 16 passed | 위 방식 |
| `make lint` | 루트 | ruff check·format, web eslint·prettier 통과 | — |
| catalog_version | `catalog_version("planning")` | **`b2cc7dd7baa915ca`** (관문 3에서 미션 파일 변경 없음) | 함수 실행 |

### 최소 테스트 6건 중 워커 몫

| 사례 | 파일::함수 | 확인한 것 |
|---|---|---|
| ③ 창 밖 약속 이행 | `services/report-worker/tests/test_report.py::test_promise_kept_after_window_is_consumed` | 종료 PATCH로 true가 된 promise_kept를 그대로 쓰고 창 밖(50분) 근거 메시지는 flag 없음, 근거가 아닌 창 밖 관련 메시지는 `out_of_window` |
| ④ 무관한 편집 | `test_report.py::test_unrelated_edit_is_unmet`, `test_rubric.py::test_each_card_items[adaptability_change]` | target_applied=false → adapt_applied_to_doc 0, 근거는 document·share로 남음 |
| ⑤ 문서 제공 실패 | `test_report.py::test_document_missing_reason`, `test_rubric.py::test_no_record_reasons` | 이벤트 document_missing 또는 draft_delivered=false → 두 항목 사유 document_missing, 소섹션 note "시스템: 문서 미제공" |

### 바꾼 것

- `report_worker/rubric.py`: 카드 단위 `evaluate(card, observation, event_fired, window_missed, document_missing)`, 세 수 `tally`·`total`, 사유 document_missing(only_if가 draft_delivered로 불충족이어도), aux 지표 null은 classify_failed.
- `report_worker/report.py`: summary·카드 평가표·섹션(window·card_at_t_min·note·facts)·근거 7타입 요약·record_ref·flag·ai_usage.events 조립. 문장은 카탈로그 `label_texts`·`no_record_reasons`라 LLM을 부르지 않는다(usage llm_calls 0). 보드 변경 요약은 새 계약 표기.
- `report_worker/api.py`: collect에 documents·task_events·honesty_facts, `session_status`. `consumer.py`: 재생성(final 뒤 completed면 thread 삭제 후 처음부터).
- 테스트: 워커 conftest를 새 세션 데이터로 다시 씀, `test_report`·`test_rubric`·`test_graph` 갱신, `tests/fixtures/report_sample.json`을 새 `build_draft` 출력으로 다시 만듦. README 갱신.
- 계약 비교: `tests/contract_shape.py`(루트, api·워커 공용, api `tests/contract.py`는 재수출). 목록 원소 매칭에 element·id 추가, `minutes` NULLABLE.
- api: `views.py` 전체 기록의 보드 변경 요약을 새 표기로, 테스트 draft 헬퍼에 응답 시간 항목 `minutes`.
- 픽스처: `report.json`(각 카드 `window`, 미충족 label 항목 근거, adapt_no_complaint_to_colleague의 document 근거, 보드 요약 새 표기), `admin_record.json`(보드 요약 새 표기).

### 판단(리뷰 대상)

1. **label 항목 근거**: 충족이면 조건을 만족시킨 근거, 미충족이면 판정 창의 관찰 근거·aux.related_message_ids 중 그 항목의 `evidence_types`에 맞는 것. 근거가 하나도 없으면 classify_failed(계약 "없으면 no_record").
2. **보드 변경 값 표기**: 계약 예시 외 값은 담당 candidate 지원자·colleague 동료·both 함께, 상태 할 일·진행 중·완료(web 보드와 같은 말), 순서는 숫자, 빈 값 "없음".
3. **honesty_report window**: 보고 요청 시각부터 실제 종료 시각까지(관찰 행이 있으면 그 값).
4. **재생성 판정**: thread가 끝났거나 finalize 직전인데 api 상태가 completed면 재생성으로 본다. 그 밖(reviewed 등)은 ack만.

### 변경 요청

- **[픽스처 수정, 이미 반영] `report.json`**: contracts.md에 있는 카드 `window`와 "label 항목은 met·unmet 무관하게 근거"가 예시에 빠져 있어 채움. 값은 예시 장면 시각 기준(honesty 110–115).
- **[참고] contracts.md 90행**은 `report_sample.json`을 "실제 출력 예"로 가리킨다. 새 출력으로 바꿨고, api가 붙이는 키(alias·position·deliverable·notes·connection_gaps·purge_at)는 없다.

### 다른 트랙에 알릴 것

- **web-integrate/web-redesign**: 리포트 근거 task_event·전체 기록의 요약이 "1번 담당 → 지원자(12분)" 형태. 섹션 카드에 `window`가 항상 있다. 미충족 label 항목에도 근거가 있다. 근거에 `flag`가 붙을 수 있다(out_of_window·aux_fact).
- **agent-session**: 워커는 관찰 행의 `metrics.<지표> = {value, evidence_ids}`, `aux.related_message_ids`, `metrics.window_missed`, 이벤트 `document_missing`, 종료 PATCH한 promise_kept를 읽는다. label 항목 근거는 관찰 evidence와 related_message_ids에서 고른다.

### 후속 인수자에게 넘길 것 (최종)

- catalog_version `b2cc7dd7baa915ca`(planning).
- 7카드 레이블: `scenarios/missions/planning/cards.yaml`의 `labels`·`label_texts`, 우선순위는 `prompts/observe_labels.md`.
- fixed_opinions 2개(collab_disagree: relationship_first·schedule_first).
- 선점 6건·팀장 DM 5건 픽스처(관문 1 절), 대본 7개(`scenarios/e2e/`).
- 소유권 반환: `services/api/app/agent/` → agent-session, `scenarios/missions/` 문구 → prompts, `scenarios/e2e/` → e2e-runner.

### 남은 문제

- B2 실값 대조(api 실제 세션 → 워커 `build_draft` → GET report의 record_ref가 전체 기록 ref와 같은지)를 한 테스트로 잇지는 못했다. 두 서비스 venv가 달라서다. 대신 양쪽 테스트가 같은 공식(같은 type·id, created_at−started_at 분, 소수 둘째 자리)과 같은 표기를 단언한다.
- 공용 DB에 임시 DB `dayzero_test_24b65a81`(연결 없음, 01:05 KST 생성)이 남아 있다. 이 트랙 실행에서 남은 것인지 확인하지 못해 지우지 않았다. 임시 스키마·테스트 큐는 남은 것이 없다.

## 관문 3 반영

`REVIEW.md` `## 관문 3`(차단 A1~A5, 권장 B1~B3)을 반영하고 main `35d4514`(web-redesign 병합 포함) 위로 rebase했다. 검증은 mock(FakeLLM 없음·워커 LLM 0회) + 격리 DB(api 임시 DB, 워커 체크포인터 임시 스키마) + 테스트 전용 큐.

| 항목 | 반영 | 확인 |
|---|---|---|
| A1 분류 실패 시 aux 항목 | `rubric._atom`: 레이블이 unclassified·null이면 aux 지표(AUX_METRICS)는 값이 남아 있어도 classify_failed. 기록 지표는 그대로 계산 | `services/report-worker/tests/test_rubric.py::test_no_record_reasons`: responsibility_delay를 unclassified로 → [1, null, null, 1] |
| A2 전부 기록 없음 | 카드 사유를 근거 검사 뒤 **최종 항목 값**으로 계산(하나라도 값이 있으면 사유 없음). 사유가 있는 카드는 observed null이고, summary line은 observed가 남은 카드만 이으므로 요소가 전부 기록 없음이면 null | `tests/test_report.py::test_all_no_record_card_hides_observed`: honesty window_missed → observed·line null, 0·0·4 |
| A3 관찰 행 없을 때 창 | 실제 카드 시각(이벤트 id의 첫 메시지, 없으면 fired_at)부터 다음에 실제 실행된 요소 카드 또는 실제 종료(completed_at)까지. 미발생 카드는 예정 시각(종료 뒤면 종료 시각)의 빈 창 | `test_window_without_observation_uses_actual_times`: 20분 요청·25분 종료 → {20, 25} |
| A4 flag 누락 | 항목 근거 집합(scored, flag 없음)과 섹션 중복 제거를 분리. 항목 근거가 아니면 aux 사실 → aux_fact, 창 밖 메시지 → out_of_window | `test_flags_survive_when_also_in_observation`: 관찰 근거에도 든 dv2는 aux_fact, related_message_ids의 55분 메시지는 out_of_window, 점수에 쓰인 50분 약속 메시지는 flag 없음 |
| A5 applied_part | 내부 `GET /assistant_reuse`가 호출마다 ratio 큰 순으로 준다(비율 값은 여전히 싣지 않음). 워커는 호출의 첫 applied 행 | `services/api/tests/routers/test_report_pipeline.py::test_applied_part_is_highest_ratio`: 0.4·0.9 → 2 |
| B1 단계별 비교 | `tests/contract_shape.py`: status 어휘를 부모 키로 좁힘(session·tasks·events), status가 reporting이면 submitted_at·deadline_at, completed면 completed_at이 null이면 실패 | `services/api/tests/test_contract_check.py`: 세션 status "todo", reporting deadline_at null 거부 |
| B2 WS 간헐 실패 | **원인 확정**: 테스트 db 세션의 identity map에 시작 때 만든 보고 요청 카드 객체(fired_at 없음)가 살아 있으면 `mark_reported`가 앱이 다른 연결에서 실행한 값 대신 옛 값을 읽었다(약한 참조라 GC 시점에 따라 간헐). 그 객체를 붙잡아 두면 매번 `fired_at=None request_status=pending`으로 재현됐다. `mark_reported`·`_fire_report_request`의 카드 조회에 `populate_existing` | `services/api/tests/test_candidate_ws.py::test_reporting_reconnect_over_ws`: 카드 객체를 끝까지 붙잡아 둔 채 통과, 실패 시 fired_at·created_at·상태를 메시지로 남김. 수정 전 단독 25회는 모두 통과(재현 안 됨) |
| B3 실값 ref 통합 | api venv에서 워커 패키지를 경로로 import해 실제 세션 → 내부 collect → build_draft → draft 저장 → GET report·GET record | `test_report_pipeline.py::test_report_refs_match_record`: message·share·open·task_event record_ref가 전체 기록 ref에 있고, ai_usage 이벤트(call_id·t_min)가 assistant_call ref와 같음 |

새 테스트 3개(A2~A4)는 수정 전 `report.py`에서 실패하고 수정 후 통과함을 확인했다.

| 명령 | 결과 |
|---|---|
| `make test` | api 91 · business-mcp 9 · rag-mcp 10 · report-worker 27 passed, web 11 files·11 tests passed |
| `make lint` | ruff check·format, web eslint·prettier 통과 |

catalog_version: **`b2cc7dd7baa915ca`**(미션 파일 변경 없음).

다른 트랙에 알릴 것:
- **web**: 카드 소섹션의 `no_record_reason`이 있으면 `observed`는 null이다. summary `line`도 요소가 전부 기록 없음이면 null이다. 관찰 행 없는 카드의 `window`는 실제 시각 기준이고, 미발생 카드는 start=end다.
- **agent-session**: 분류 실패(label null·unclassified)면 aux 값은 점수에 쓰이지 않는다. 기록 지표는 계속 쓰인다.

남은 것: B4(리포트 역할 모델·llm.py docstring 정리)는 리뷰 지시대로 오케스트레이터 문서 결정 몫으로 두고 손대지 않았다. 공용 DB의 임시 DB `dayzero_test_24b65a81`은 소유를 확인하지 못해 그대로 두었다.
