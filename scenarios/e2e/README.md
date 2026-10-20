# e2e 대본 (초기본)

scenario-redesign이 만든 초기본을 e2e-runner 트랙이 인수해 다듬는다. 형식과 단언은 `docs/common/testing.md`, 실행은 `tests/e2e/README.md`.

공통 키:
- `mission`(기본 planning), `elements`, `minutes`. `expect`: `labels`(카드별 기대 레이블), `evidence_types`(카드별 들어 있어야 할 근거 타입), `rubric`(요소별 `{met, unmet, no_record}`, 첫 실 실행으로 확정), `tool_choice`(단언 3b: `search_documents`·`no_tool`에 지원자 발화 본문), `masked`(단언 3: 어시스턴트 요청 원문 `raw`가 저장·리포트·기록 어디에도 없고 `marks`가 남음).
- `at`: 카드 id(그 카드의 `message.new.event_id`를 받은 직후), 절대 분(`12.5`), 또는 `+분`(직전 step 기준).

step 동작(한 step에 여러 개면 아래 순서로 실행):

| 키 | 호출 |
|---|---|
| `board: [{part_no, assignee?, status?, order?, due_min?, expect?}]` | `PUT /sessions/{id}/tasks/{part_no}`를 순서대로. `expect`는 기대 상태 코드(기본 200, 위반 조합은 422) |
| `say: {channel, content, reply_to_doc?: {part_no, version}}` | WS `message.send`. reply_to_doc의 part_no는 받은 동료 문서로 바꿔 보낸다 |
| `write: {part_no∣final, content}` | `PUT /sessions/{id}/my-documents/{part_no∣final}` (final은 `{sections: [{part_no, content}]}`) |
| `share: {part_no, channel}` | `POST .../my-documents/{part_no}/share` |
| `open: {part_no, version}` | 받은 동료 문서를 `POST .../documents/{doc_id}/open` |
| `import: {part_no, from: candidate∣colleague, version}` | `PUT .../final/sections/{part_no}/import` |
| `view: doc_id` | `GET .../documents/{doc_id}` |
| `assistant: 질문`, `capture_as` | `POST .../assistant`, 응답 본문을 변수로 보관(`{이름}`으로 치환) |
| `submit: true` | `POST .../submit` |
| `restart: api` | api 컨테이너 재시작 후 `/s/{token}/resume`·`/state` 복원 |
| `disconnect: 초` | WS를 끊고 그 시간 뒤 `POST /s/{token}/resume`(새 JWT) → `GET /state` → 재연결 |
| `inject: {tool, fail_times}` | 다음 그 도구 호출을 fail_times번 실패시킴. 도구 호출 단위이고 MCP 안 재시도까지 503(HTTP로는 ×2). 러너의 장애 주입 프록시(`tests/e2e/faults.py`)가 api 내부 앱 앞에서 한다 |

## 최소 테스트 6건 ↔ 대본 인수표

| 사례 | 대본·단계 | 기대값 | 남은 검증(e2e-runner) |
|---|---|---|---|
| C1 보드만으로 분업 확정 | `all_five` at 0.2 `board` 5건, 위반 조합은 `one_element` planning_division `board`(`expect: 422`) | 마지막 PUT 뒤 `division.confirmed{candidate}`, task_events 5건, 동료 보드 doing. 위반 조합 마지막 PUT 422 | — |
| C2 카드 전 계획 | `all_five` at 0.2(카드 0.5 전) | planning_division window_start=0, 두 항목 충족 | 카드 뒤 결정 대본과 값 비교 |
| C3 창 밖 약속 이행 | `all_five` collab_help "1분 뒤" → `+1` DM(창 밖) | 창 닫힘 promise_kept=null → finalize true, 리포트 근거(flag 없음) | — |
| C4 무관한 편집 | `restart` adaptability_change의 오탈자 수정 | document_changed_after=true, target_applied=false, adapt_applied_to_doc=0 | 반영 대본(`all_five`)은 1 |
| C5 문서 제공 실패 | `one_element` at 1.4 `inject` send_document 2회 실패 | 첫 시도 failed, document_missing=true, 재실행 | 끝내 실패 시 plan_* 사유 document_missing |
| C6 reporting 재접속 | `early_submit` 제출 → `disconnect` → 팀장 DM 보고 | resume 200·새 JWT, state reporting·deadline_at, kind=report로 completed, connection_gaps 1건 | 팀 채널 보고도 같은지 |

## agent-session 보강 (P2)

- 새 step 키는 없다. `all_five`에 기존 키(`say`)로 step 3개를 더했다: 진행 질문 2회(1.8, +0.1), 완성본 v2 답글(review +0.1, `reply_to_doc` 4번 v2 → 동료 v3). 약속 이행 step은 `+1` 대신 절대 시각 `2.5`(같은 시각)로 바꿨다. 3.85 step의 1번 문서 본문에 원인 가정 문장("주원인 가정: 다음 모임 일정을 놓쳐서.")을 남겨 반대 의견 대상 ①이 성립하게 했다.
- 새 기대값 키 `expect.work_memory`(all_five): `draft_v1`·`final_v2`(파트별 핵심어), `v3_after_reply`, `progress_same_answer`, `board`, `disagree_target`. 프로세스 안 실행은 `services/api/tests/agent/test_session_scripts.py`가 단언한다.
