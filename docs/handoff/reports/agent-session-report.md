# agent-session 보고서 (P2, M2 = 세션 그래프 전체)

브랜치 `track/agent-session`. 기준 커밋은 `903eacd`(main 4b849b8 + P2 브리프)이고 계약 커밋은 37bed0b, catalog_version은 `b2cc7dd7baa915ca`다. 미션 파일은 바꾸지 않아 버전이 그대로다. 커밋은 5개다(`f835025`, `68ddb95`, `6718168`, `95c972c`, 마지막 커밋). push와 병합은 하지 않았다.

검증 방식 표기
- **mock**: FakeLLM(`tests/agent/brain.py`의 Brain이 호출 종류별로 정해진 값을 낸다)
- **격리 DB**: 실행마다 임시 DB `dayzero_test_<랜덤>`를 만들고 끝나면 DROP한다
- **실 MCP**: business-mcp·rag-mcp를 하위 프로세스로 띄운다(rag는 2-gram 임베딩)
- **live**: gpt-4o-mini 제한 키(`infra/.env.local`)를 쓰고 `MODEL_*`는 비웠다

6분 세션은 `tests/agent/script_driver.py`가 돌린다. 세션의 모든 timestamptz 열(분업 확정 JSON 포함)을 과거로 당겨 세션 시각을 앞으로 보낸다. 스케줄러 tick은 실제 now로 돈다. 지원자 행동은 공개 앱 REST와, WS가 쓰는 것과 같은 접수 함수로 넣는다.

## 완료 기준 줄별 결과

| 완료 기준 (docs/agent/design.md M2 이하) | 테스트 (`cd services/api && uv run pytest -q tests/agent/…`) | 결과 | 방식 |
|---|---|---|---|
| 6분 세션 + 대본 3개, 카드 전부 정시(±10초)·행마다 event_id 메시지 | `test_session_scripts.py` 3건 (`assert_cards_on_time`) | 통과 | mock·격리 DB·실 MCP |
| 분업 되돌림 1회 뒤 확정 | `test_division_refuse_script`: 위반안(2번 동료)에 되돌림 1회, 다음 결정 수락. 위반안 task_event 없음 | 통과 | 〃 |
| 미합의 중 카드 도래 | `test_session_recovery.py::test_undecided_division_uses_default_and_disagree_falls_back`: collab_help에서 기본안 확정(colleague_default)·안내 DM 1건 | 통과 | 〃 |
| 조기 제출 → 보고 요청 즉시 실행 → 보고 → completed | `test_early_submit_script`: 보고 요청 due_at=submitted_at, reporting, resume·state, 팀장 DM 보고(kind=report)로 completed_at=reported_at | 통과 | 〃 |
| 제출+5분 상한 / 요청 뒤 제출(보고 있으면 바로) | `test_division_refuse_script`(보고 없음 → deadline_at에 completed), `test_all_five_script`(보고 뒤 제출 → 즉시 completed) | 통과 | 〃 |
| api 재시작 후 fired 이벤트 재실행과 /state 이어하기 | `test_restart_reruns_fired_card_without_duplicates`: 문서 3개를 보낸 뒤 공유 메시지 전에 죽게 했다. 새 러너가 60초 뒤 같은 run_id로 실행해 done이 되고 attempts는 2, 버전은 그대로 v1, 메시지 seq는 1·30·40·50 한 벌. GET /state 200 | 통과 | 〃 |
| 허용 밖 도구 거부 | `test_session_flow.py::test_tool_outside_allowlist_is_rejected`(agent-min) | 통과 | 〃 |
| 미공개 문서 질문에 "아직 공유되지 않은 자료" | `test_unreleased_document_question_answers_not_shared`, grounding g05(`test_context_rules.py`) | 통과(live도 통과) | mock·live |
| 보내지 않은 지원자 문서 질문에 "아직 못 봤어요" | `test_context_excludes_future_notice_and_unsent`: 응답이 고정 문장으로 시작하고, 저장만 한 본문은 어떤 LLM 입력에도 없음 | 통과 | mock |
| 팀장 DM 판단 요청에 "주담당이 정해 주세요" | `test_manager_dm_rules`: 픽스처 5건 중 판단 요청(md03·04)만 고정 문장. 팀장 도구는 3개 | 통과(live 5/5) | mock·live |
| 강제 LLM 실패 3회에 세션 failed | `test_llm_failing_three_times_fails_session`: 메시지는 폴백 "잠시만요."(seq 9). 킥오프 카드는 3회 실패해 failed가 되고 세션 failed(card_failed:kickoff), retries ≥ 2 | 통과 | mock |
| LangSmith trace에 run_id | `test_all_five_script`: 모든 LLM 호출의 metadata·tags에 이벤트 run_id. 그래프 config는 `agent_run_id`(아래 남은 문제 1) | 통과 | mock |
| 근거 정확성 픽스처 10건 | `test_grounding_fixtures`: 동료 5건은 기대 도구 호출, 모델에 준 검색 결과에 허용 문서, meta 인용 = 본문 인용, 미공개 고정 문장을 본다. 어시스턴트 5건은 허용 도구의 rag 결과(공개 문서만, 허용 문서 포함, g09 not_released)만 본다 | 통과 | mock·실 MCP |
| 작업 기억 | `test_all_five_script`: v1 4번에 "재참여", v2 3번에 "후속 모임"·5번에 "이번 분기". 3번 v1은 골격. v2 답글 뒤 4번 v3. 진행 질문 2회에 같은 답. 보드는 3·4·5 doing → done(colleague task_event, set_division 없음). 재실행에 버전이 늘지 않는 것은 위 재시작 테스트가 본다. 지시 반영 검사 1회 재생성은 recovery 미합의 테스트가 본다 | 통과 | mock |
| 반대 의견 대상 | 보낸 대본(all_five)은 1번 v1의 "주원인 가정: 다음 모임 일정을 놓쳐서." 문장을 인용한다. 안 보낸 세션(recovery 미합의)은 "처음 정한 방향"을 가리킨다. 두 경우 모두 본문 끝이 카탈로그 고정 의견과 같고, 앞 문장에 "보내" 없음 | 통과 | mock |
| 관찰 7장 픽스처·창 밖 related_card·정직 facts 대조 | `test_observe.py`(14건): 카드 7장의 레이블·aux 키·근거 타입·지표 키·워커 rubric 값, 창 밖 메시지는 related_card일 때만, 동료 몫을 자기 것으로 말한 보고 → misattributes(평가표 0·0·0·1), 활동 없음은 no_evidence이고 LLM 미호출, 허용 밖·근거 없는 레이블은 unclassified | 통과 | mock(순수 함수) |
| 최소 테스트 agent 열 5건 | 아래 6건 배정 표 | 통과 | — |
| 선점 금지 6건 픽스처 | `test_preemption_rules_reach_colleague`: 그 시각에 열린 창의 금지 규칙, any 규칙, 해도 되는 것이 동료 입력 `[지금 지킬 것]`에 들어감 | mock 통과 / live 2/6 | mock·live |
| `cd services/api && uv run pytest` | 117 passed, 4 deselected(live) | 통과 | — |
| 루트 `make test` | api 117 · business-mcp 9 · rag-mcp 10 · report-worker 27 passed, web 11 | 통과 | — |
| 루트 `make lint` | ruff check·format, eslint·prettier | 통과 | — |
| live 1회 `make test-live` | 4 passed(통과를 요구하지 않는 결과 출력 테스트 포함). 결과는 맨 아래 | 실행함 | live |

## 6건 배정 (agent 열)

| 사례 | 파일::함수 | 그래프가 만든 입력 |
|---|---|---|
| ① 보드만으로 분업 | `test_session_scripts.py::test_all_five_script` | 보드 PUT 5건 → division 자극 → `division.division_node`. set_division 없이 `confirm_division`이 work_notes.parts·보드 doing |
| ② 카드 전 계획 | `test_observe.py::test_plan_before_card_is_judged_the_same` (+ all_five의 0.2분 결정 → planning_division window_start=0, 평가표 2/2) | `observe._division_by_candidate`, 창 시작 0 |
| ③ 창 밖 약속 이행 | `test_all_five_script`(1.5분 약속 → 2.5분 이행 → 종료 PATCH true, 근거 = 이행 메시지), `test_observe.py::test_out_of_window_message_only_when_related` | `observing.close` → `observe.promise_kept` → update_observation |
| ④ 무관한 편집 | `test_observe.py::test_unrelated_edit_does_not_count_as_applied` | document_changed_after true, target_applied false → adapt_applied_to_doc 0 |
| ⑤ 문서 제공 실패 | `test_session_recovery.py::test_document_send_failure_marks_document_missing`, `test_observe.py::test_document_missing_reason_when_draft_not_delivered` | send 2회 실패 → `RunResult.error="document_missing: …"`, 다음 시도에 성공하면 done·표시 해제. 끝내 실패하면 카드 failed·document_missing·세션 failed. draft_delivered false → 두 항목 사유 document_missing |
| ⑥ reporting 재접속 | `test_early_submit_script` | 제출 → resume(새 JWT) → state reporting → 팀장 DM 보고 → completed |

## 수정 파일

- `services/api/app/agent/session/`
  - `common.py`(새): RunDeps(역할별 LLM, 세션 조회), prepare/resumed, post·compose·컨텍스트 블록
  - `nodes.py`: route, 분류, respond(동료·팀장)와 코드가 보장하는 고정 문장
  - `division.py`(새): confirm_division, 기본안, negotiate, 보드 자극
  - `cards.py`(새): 카드 7장과 흐름 카드·texture 실행
  - `drafts.py`(새): v1·v2·v3 쓰기, 지시 반영 검사, 보내기 재시도
  - `observing.py`(새): 창 열기·닫기, 종료 PATCH
  - `classify.py`: kind 7개, decision·parts·instructions·related_card 등
  - `prompts.py`: 팀장 DM 채널, `[지금 지킬 것]`·`[쓸 파트]`·미공개 표시
  - 나머지: `store.py`(observe 입력·정직 사실·mark_reported), `state.py`, `seq.py`, `graph.py`, `runner.py`
- `services/api/app/agent/observe/__init__.py`(새): Window·Inputs, compute_metrics, classify, observe, promise_kept
- `services/api/app/agent/llm/`: `roles.py`(새, 오케스트레이터 추가 요청), `openai.py`(base_url 추가만), `__init__.py`(export 추가만). 기존 공개 함수·반환형은 그대로다.
- `services/api/app/services/context.py`: runner 선택 부분만. 기본값을 `AGENT_RUNNER=session`으로 바꾸고 역할별 make_llm을 붙였다.
- `services/api/tests/agent/`:
  - 새 파일: brain, script_driver, test_session_scripts, test_session_recovery, test_observe, test_context_rules, test_llm_roles
  - 바꾼 파일: test_live
- `scenarios/e2e/all_five.yaml`: 기대값 `work_memory`와 step 3개를 보강했다. `README.md`에 메모를 남겼다.

## 남은 문제

1. **agent-min부터 있던 결함을 고쳤다.** 그래프 config `metadata.run_id`가 있으면, LangGraph는 같은 run_id 재호출을 끝난 실행으로 보고 아무 노드도 돌리지 않았다. 그래서 카드 재시도(최초 포함 3회)가 실제로는 1회였다. 메타데이터 키를 `agent_run_id`로 바꿨다. LLM 호출 trace의 `metadata.run_id`·`tags run_id:` 표기는 그대로다. 중단된 실행을 route 없이 이어 가는 경우에 대비해 진입 노드가 세션 조회를 직접 채운다(`common.resumed`).
2. **(수정 라운드에서 정정)** 처음 보고에는 일반 응답 연속 실패 카운터가 없고 카드 3회 실패로 대신 충족한다고 적었다. 이 둘은 별개 조건이라 그 서술은 틀렸다. 이제 api가 `sessions.llm_failures`로 일반 응답 LLM 실패를 센다. 연속 3회면 세션 failed, 정상 응답이면 0이다(R7, 아래 수정 라운드).
3. **(수정 라운드에서 정정)** 처음 보고에는 토큰 예산을 respond만 차감한다고 적었는데, 이는 필수 요구사항 미구현이었다. 이제 모든 실행의 LLM 사용량을 세션 예산에서 빼고, 소진 뒤 카드는 규칙 문장으로 나간다(R6). **6k 토큰 초과 시 요약 접기는 여전히 하지 않았다.** recent는 80개, 페르소나별 30개이고, 누적되는 instructions·feedback은 크기 제한이 없다. 이 항목은 harness Context의 미완료로 남는다.
4. **(수정 라운드에서 정정)** 처음 보고에는 보드 재배정에 한도를 적용하지 않는다고 적었다. 이제 보드 PUT·동료 set_division·채팅 재분업이 같은 한도(적응성 카드 전 1회·뒤 1회, `sessions.redivisions`)를 쓴다. 넘으면 보드는 422, 채팅은 고정 안내다(R8).
5. **반대 의견의 의견 본문은 카탈로그 문장을 그대로 붙인다.** 모델은 앞 문장(청하기) 하나만 생성하고, 대상 인용 문장은 코드가 만든다. "말투만 생성"을 고정 문장 보장 쪽으로 해석한 것이다.
6. **메시지 분류(kind 등)는 observe 역할 모델을 쓴다.** 고정 분류 작업이라서다. 동료 문서·진행 기록은 colleague 역할을 쓴다.
7. **e2e `disconnect` step은 WS를 실제로 끊지 않는다.** 드라이버는 resume·state 경로만 확인한다. connection_gaps 단언은 e2e-runner 몫이다.
8. **대본 안에서 페르소나 문장은 mock이다.** 레이블은 대본 expect를 모의 LLM이 낸다. 그래서 mock 테스트가 보는 것은 그래프·지표·평가표 입력의 정합이지 분류 정확도가 아니다. 정확도는 live 결과를 보면 된다.

## 변경 요청

1. **SessionService(foundation)**: `RunResult.fallback_used`를 세션 카운터 llm_failures로 받는다. 연속 3회면 fail(session), 성공하면 0으로 되돌린다(harness.md Recovery). 영향 경로는 `app/services/runs.py`·`session.py`·schema다.
2. **docs/agent/design.md 레이블 규칙(scenario-redesign 요청 재확인)**: 지금 "하지 않음" 레이블은 근거 없이도 허용한다. observe_labels.md를 따른 것이다. design.md의 "레이블이 있으면 evidence ≥1" 문구를 고쳐 달라.
3. **contracts.md 분류 PUT 본문**: `reply_to_doc {document_id, version}`를 저장한다. design.md respond 행에 있는 필드인데 계약 Classification 모델에는 없다. 지금은 DB 직접 저장이라 통과한다.
4. **design.md 재시도 메모**: 위 남은 문제 1처럼 그래프 config 메타데이터 키를 `agent_run_id`로 바꿨다. harness.md Observability의 "run_id를 metadata로"에 이 사실을 적어 달라.

## 다른 트랙에 알릴 것

- **agent-assistant**
  - 공용 생성 함수 `from app.agent.llm import make_llm, model_for, key_for, ROLES`
    - `make_llm(role: str, env: Mapping[str, str] | None = None) -> BaseLLM`. role ∈ colleague·manager·observe·assistant·report이고, 어시스턴트는 `make_llm("assistant")`를 쓴다.
    - `model_for(role, env=None) -> str`: `MODEL_<ROLE>`, 비면 `OPENAI_MODEL`, 기본 gpt-4o-mini
    - `key_for(model, env=None) -> (api_key, base_url|None)`: gpt-4o-mini → OPENAI_API_KEY, 그 외 gpt-* → OPENAI_API_KEY_PERSONAL, gemini-* → GEMINI_API_KEY + Google OpenAI 호환 base_url. 키가 비면 ValueError
  - `OpenAILLM(api_key, model, timeout, retry_delays, base_url=None)`: base_url만 추가했다.
  - `app.agent.session.runner.checkpoint_conninfo`는 이름·시그니처를 그대로 유지했다.
  - `SessionAgentRunner(..., roles=None)`: 키워드 인자 하나를 추가했다.
- **e2e-runner**
  - all_five에 진행 질문 2회(1.8, +0.1), v2 답글(review +0.1, 4번 v2)을 넣었다. 약속 이행 step은 `at: 2.5`(절대)로 바꿨다. 3.85 write에는 원인 가정 문장을 남겼다.
  - 새 expect 키는 `work_memory`이고, step 키는 늘지 않았다.
  - 실제 그래프에서 보이는 메시지:
    - 진행 답 형식: "지금 4번은 …이에요."
    - 기본안 안내: "아직 분업이 안 정해져서 일단 …로 진행할게요."
    - 폴백: seq 9 "잠시만요."
    - 반대 의견은 "… 1번에 “문장”라고 쓰신 부분이요. <고정 의견>"
  - 응답 meta에는 `slot`이 있다.
- **web-integrate**
  - 세션 안 메시지 흐름: 킥오프는 팀장(team)과 동료 인사(dm) 2건이다. 분업 카드는 동료 dm이고, 보드 확정 뒤에는 동료 수락 dm 1건이 나온다.
  - 중간 점검·리뷰에서는 동료 문서 카드 메시지(본문 "n번 제목 vK", `shared_doc`)가 파트마다 나오고, 그다음 공유 메시지가 온다. 보드 task.updated(by colleague)는 doing → done이다.
  - collab_disagree는 review 공유 다음 메시지다. 보고 요청은 팀장 team과 notice 시스템 줄("최종본은 오른쪽 탭에서 제출합니다…")이다.
  - 동료 v2 답글에 고쳐 달라고 하면 v3 문서 카드와 동료 답이 이어진다.
- **prompts**
  - 새 블록 `[지금 지킬 것]`(현재 창의 must_not_preempt와 in_window_help), `[쓸 파트]`(파트 문서 생성), `[진행 기록]`(진행 명사구 JSON)을 README 블록 표에 넣어 달라.
  - 분류 지시문(`classify.CLASSIFY_SYSTEM`)이 아직 코드에 있다.
  - 문구 요청 1: manager.md 6절의 "다 됐다고 전해도 되죠?"를 팀장이 이후 모든 답에 붙인다(live). 카드 brief에만 쓰는 문장임을 분명히 해 달라.
  - 문구 요청 2: 동료가 공유 메시지에 문서 본문 전체를 붙인다. "문서 본문은 문서 카드로 가니 메시지는 한 줄"을 강조해 달라.
  - 문구 요청 3: colleague.md 예시의 "후속 모임"은 적응성 카드 내용을 미리 비춘다(미래 암시). 다른 예시로 바꿔 달라.
  - 문구 요청 4: 선점 금지 위반이 live에 나왔다. 아래 판단 자료를 본다.

## 모델 상향 판단 자료 (live, gpt-4o-mini, 1회. `make test-live` 출력)

| 항목 | 결과 |
|---|---|
| 관찰 레이블 정확도(픽스처 7장, temperature 0) | **7/7 일치**. 다만 aux가 bool이 아닌 문자열로 온 경우가 2건이다(mentions_schedule·mentions_impact에 근거 문장). 지표는 truthy로 처리돼 동작하지만 형식은 어긋난다 |
| 관찰 레이블(all_five 대본 전체, 분류·페르소나 모두 실모델) | **5/7**. planning_checkin은 feedback 기대에 acknowledge, honesty_report는 fair_report 기대에 hides_incomplete가 나왔다. 앞선 live 실행(같은 날)은 6/7(honesty만 불일치) |
| 카드 실패율(all_five) | 9장 모두 done. 이번 실행은 attempts 전부 1이고, 앞선 실행은 review·collab_disagree가 2(1회 재시도) |
| 대본 진행 | 실모델 분류가 대본 의도와 갈라져 동료 4번 문서가 체크인 시점에 없었다. 그래서 open·답글·import step 3개를 건너뛰었다(driver_log) |
| 팀장 DM 규칙(5건) | **5/5**(판단 요청 2건은 코드 고정 문장). 단 md03은 돌린 뒤 1번 내용 조언을 덧붙인다 |
| 선점 금지(6건) | **2/6**. 위반 내용: division_schedule_first는 안을 확정처럼 말함, change_redirect_first는 바뀐 방향을 대신 정리함, report_direct_to_manager는 "제가 대신 팀장님께 말씀드릴게요", ghostwrite_candidate_part는 "작성해 드릴게요". 앞선 실행은 4/6(report·ghostwrite 위반) |
| 미공개 문서(g05) | 통과(코드 고정 문장) |
| 비용(all_five 1회) | llm_calls 50, 토큰 약 24만(입력이 대부분), 폴백 0 |

해석: **관찰 분류는 gpt-4o-mini로 유지할 만하다.** **동료 역할은 선점 금지(평가 보호)를 자주 어긴다.** 그래서 프롬프트 보강(문구 요청 4)을 먼저 하고, 그래도 안 되면 `MODEL_COLLEAGUE`만 올리는 것이 decisions.md 상향 규칙에 맞는다. 팀장은 규칙을 지키지만 보고 요청 문장을 반복한다(문구 요청 1).

## 수정 라운드(Codex)

`REVIEW.md` 차단 R1~R9와 권장 5건을 반영했다. 오케스트레이터 결정에 따라 R7·R8의 공용 API 변경(`app/services/runs.py`·`board.py`·`scheduler.py`·`app/agent/runner.py`의 RunResult 필드 추가·`app/models`·`infra/db/schema.sql`)을 이 트랙에서 이번만 했다. 검증 방식: mock(FakeLLM), 격리 DB, 실 MCP 하위 프로세스. 관찰 live는 다시 한 번 돌렸다.

| 항목 | 반영 | 확인 (`services/api/tests/agent/…`) |
|---|---|---|
| R1 관찰 저장 실패 뒤 창 전환 누락 | inject는 실행을 마친 행을 `stimulus.injected`에만 둔다. 처리 완료(handled_stimuli) 확정은 observe가 관찰 저장·창 전환까지 마친 뒤에 한다. 실패하면 같은 run_id 재시도가 카드(멱등: 같은 슬롯·같은 run 문서는 재생성하지 않음)부터 다시 돈다 | `test_session_recovery.py::test_observation_failure_retries_window_switch`: record_observation 1회 실패 → attempts 2·done, planning_division 관찰 저장, current_card=planning_checkin, 카드 메시지 seq 1·30·40·50 한 벌 |
| R2 재시도 때 sent·progress 미복원 | 같은 run의 문서 카드가 있으면 그 `shared_doc.version`으로 sent·progress를 복원한다(카드 `_send_parts`, 답글 `_revise`) | `test_restart_reruns_fired_card_without_duplicates`를 넓혔다: 재시작 뒤 work_notes.sent {3:1,4:1,5:1}·progress 복원, 리뷰 v2 → v2 답글 → 4번 v3. 버전은 3:[1,2], 4:[1,2,3], 5:[1,2] |
| R3 문서 첫 300자만 관찰 | 저장본은 직전 저장본 대비 바뀐 부분만 싣고 절단하지 않는다. 최종본은 바뀐 섹션 전체다. 보낸 버전(share)은 본문을 싣는다 | `test_observe.py::test_document_input_keeps_changed_sections_and_share_body`: 350자 뒤 3·5번 변경이 분류 입력에 들어가고 바뀌지 않은 섹션은 빠짐 |
| R4 aux 타입 미검사 | aux는 참/거짓만, promised_t_min은 숫자만 받는다. 그 밖(문자열 "false"·설명문)은 null이고 그 지표는 분류 실패다. 분류 입력 `[카드]`에 aux 형식을 적었다 | `test_aux_with_wrong_type_is_null`. live 관찰 7장 재실행: 레이블 7/7, aux 전부 올바른 타입(형식 명시 전에는 4건이 문자열 → null이 됐음). 처음 보고의 "truthy로 처리돼 동작한다"는 해석은 철회한다 |
| R5 질문을 보고로 분류 | 규칙·LLM 분류 모두 질문·진행 조회는 report가 아니다(진행 조회는 progress_query, 그 밖은 question) | `test_report_classification_excludes_questions`, `test_llm_report_on_question_is_downgraded` |
| R6 예산 우회 | 실행 끝 `account` 노드가 이번 실행의 모든 LLM 사용량(분류·페르소나·문서·진행·관찰, 재시도 포함)을 세션 예산에서 뺀다. 소진 뒤 처리: 카드는 규칙 문장(brief 안 따옴표 문장, 없으면 카드별 최소 문장), 문서는 규칙 문서(이전 버전 + 최신 지시), 분류는 규칙, 진행 기록은 규칙 문구, 응답은 안내문이다. 관찰 분류는 평가 기록이라 예산 뒤에도 돈다(사용량은 셈) | `test_session_limits.py::test_budget_counts_every_call_and_cards_use_rule_text`: 킥오프 뒤 예산 0, 분업 카드는 LLM 호출 0회로 규칙 문장 발행·done |
| R7 일반 응답 연속 실패 | `RunResult.reply_fallback`(응답 자체가 LLM 실패 폴백일 때만, 분류 폴백 제외)을 추가했다. `finish_run`이 같은 트랜잭션에서 메시지 실행마다 llm_failures를 +1 또는 0으로 갱신하고, `run_stimulus`가 3이면 fail(session, "llm_failures")한다. 그 사이에 죽어도 스케줄러 `_retry`가 수렴시킨다. 메시지 실행은 끝난 run을 다시 돌리지 않아 같은 run_id 중복 집계가 없다 | `test_three_consecutive_reply_failures_fail_session`: 카드 정상 세션에서 실패 1 → 정상 1(0으로) → 실패 3 → failed(llm_failures). 킥오프 카드는 done |
| R8 보드·채팅 재분업 한도 | `board.use_redivide`가 확정 뒤 재배정마다 단계(적응성 카드 fired 전·후)를 검사한다. 단계마다 1회, 보드는 첫 변경 뒤 1분(세션 분) 안 연속 변경을 같은 재분업으로 본다. `sessions.redivisions`에 기록한다. 보드 PUT·내부 PUT /division이 같은 함수를 쓰고 넘으면 422 invalid_division이다. 그래프는 같은 기록으로 미리 확인해 고정 안내를 낸다 | `test_redivide_limit_shared_by_board_and_chat`: 카드 전 보드 재배정 1회 200 → 1분 뒤 422 → 채팅 재분업은 고정 안내·분업 그대로 → 적응성 카드 뒤 1회 200, redivisions [before_change, after_change] |
| R9 반대 의견 대상 시각 | 카드 due_at까지 보낸 1번 버전 중 최신만 쓴다. 재실행이면 처음 고른 대상(work_notes.disagree_target)을 그대로 쓴다 | `test_disagree_target_uses_versions_until_card_time`(89분 v1·91분 v2, 기준 90 → v1) |
| 권장: 정시 단언 | 대본 3개에서 fired−due ≤10초에 더해 fired→done ≤10초, fired→첫 카드 메시지 ≤90초를 단언한다 | `test_session_scripts.py::assert_cards_on_time` |
| 권장: reporting 중 redivide | 제출 뒤 redivide는 negotiate로 보내지 않는다. respond가 변경 도구 없이 "제출해서 바꾸지 않는다"로 답한다 | 코드(분류 라우팅). 전용 테스트는 없다 |
| 권장: 관찰 문서 마스킹 | 관찰 입력의 문서 변경분·보낸 본문에 `app.masking.mask`(이메일·전화번호)를 적용한다 | R3 테스트에서 이메일 마스킹 확인. 페르소나 컨텍스트의 공유 문서 미리보기는 아직 마스킹하지 않는다(공용 경계 과제로 남김) |
| 권장: 기존 관찰 조회 | record_observation 전에 같은 (card_id, window_start) 관찰이 있으면 다시 분류하지 않는다 | R1 테스트 경로 |
| 권장: 요약 접기 | 하지 않았다. 남은 문제 3에 미완료로 남겼다 | — |

명령과 결과
- `cd services/api && uv run pytest -q` → 126 passed, 4 deselected
- `make test` → api 126 · business-mcp 9 · rag-mcp 10 · report-worker 27 passed, web 11
- `make lint` → 통과
- live 관찰 재실행(`uv run pytest -q -m live -k observe`) → 7/7 일치

보고서 서술 정정
- 멱등 복구 완료 주장의 범위: 카드 메시지·문서 버전·관찰 행이 한 벌로 수렴하는 것은 R1·R2 테스트로 확인했다. 실제 WS 단절·전달 지연은 여전히 e2e-runner 인수 범위다.
- 변경 요청 1(카운터)은 R7로 처리했다. 집계 범위는 "응답이 폴백 문장(seq 9)이 된 경우"다. LLM 재시도 실패와 도구 상한 초과(답 없이 도구만 고름)를 센다. 분류 폴백과 예산 안내문은 세지 않는다. 정상 응답이면 0으로 되돌린다.
- 변경 요청 3(reply_to_doc): 메시지 참조는 `meta.reply_to_doc {doc_id, version}`이고, 분류 저장은 `meta.classification.reply_to_doc {document_id, version}`(그래프가 DB에 직접 저장)이다. 관찰은 메시지 meta.reply_to_doc을 읽는다. contracts.md 정합화가 필요하다.
- 모델 상향 판단 자료: 관찰 7/7은 R3·R4 반영과 aux 형식 명시 뒤 다시 확인한 값이다. all_five 5/7은 대본 step 3개(문서·답글·import)를 건너뛴 실행이라 입력 경로 문제가 섞여 있다. 팀장 5/5는 코드 접두문과 정규식 결과일 뿐이고, 뒤에 정답을 덧붙이지 않는다는 의미 조건까지 본 것은 아니다. 선점 금지 2/6은 이번 라운드에서 다시 재지 않았다. 프롬프트 보강 뒤 같은 6건을 다시 확인한다.

다른 트랙에 알릴 것(추가)
- **foundation·api**:
  - `sessions.redivisions jsonb` 열을 추가했다.
  - `RunResult.reply_fallback`을 추가했다.
  - `runs.finish_run(db, run_id, result, session_id=None, stimulus=None)`에 선택 인자 2개를 추가했다.
  - `runs.llm_failures_exceeded`를 추가했다.
  - `board.use_redivide`·`redivide_stage`·`redivide_allowed`를 추가했다.
  - 보드 PUT 422 문장 "일정상 지금 더 바꾸긴 어렵겠어요. 지금 분담대로 마무리해 주세요."를 새로 쓴다.
- **web-integrate**: 확정 뒤 보드 재배정이 한도를 넘으면 422 invalid_division이 온다. 화면은 기존 422처럼 문장을 보여 주면 된다.
- **e2e-runner**: 최종 인수 범위에 넣을 것:
  - 실제 WS 단절과 connection_gaps
  - 관찰 저장 장애(R1)
  - 리뷰 중 재시작 뒤 v3(R2)

### 재확인 반영 (RC1~RC6)

`REVIEW.md ## 재확인`의 잔여 차단 6건과 공유 문서 미리보기 마스킹을 반영했다. 검증 방식: mock(FakeLLM), 격리 DB, 실 MCP 하위 프로세스. live는 이번 라운드에 돌리지 않았다.

| 항목 | 반영 | 확인 (`services/api/tests/agent/…`) |
|---|---|---|
| RC1 응답 저장 뒤 끊긴 v3 | 응답 슬롯(seq 1·9)이 이미 있으면 생성 없이 `_restore`가 같은 run의 문서 카드(`shared_doc.version`)로 sent·progress를 맞춘다 | `test_session_recovery.py::test_reply_saved_before_checkpoint_restores_v3_memory`: v3·응답 저장 직후 예외 → 같은 run_id 복구 → sent["4"]=3·"v3까지 보낸 상태", 버전 [1,2,3], 응답 1건 |
| RC2 삭제·순서 변경 | 파트 문서는 현재 본문 전체와 지운 줄을, 최종본은 바뀐 섹션마다 현재 섹션과 지운 줄(섹션째 지웠으면 그 섹션)을 싣는다 | `test_observe.py::test_changed_text_keeps_deletions_and_reorders`(줄 삭제·순서 변경·최종본 섹션 안 삭제) |
| RC3 보고 분류 | **(재확인 2에서 보강, 이 줄의 "해결" 주장은 부분 해결이었다)** 문장 단위로 판정한다. 결과를 진술한 문장(묻지 않는 문장 중 썼다·완료·비어 있다 등)이 있으면 보고다. 묻는 문장은 물음표나, 마침표를 찍은 의문 끝맺음(나요·까요 등)·의문사로 알아본다. 진행 조회는 진행을 묻는 문장이 있고 결과 진술이 없을 때만이다. LLM이 report라 해도 결과 진술이 없으면 question 또는 progress_query로 바꾼다 | `test_report_classification_follows_intent`·`test_llm_report_kept_only_with_result_statement` 6건씩(규칙·LLM). 반례: "진행했고 … 썼습니다" → report, "완료됐나요." → question, 보고 + 질문 혼합 → report |
| RC4 도구 루프 예산 | `_tool_loop`가 매 LLM 호출 전에 잔액을 본다. 바닥이면 예산 안내(seq 9, reply_fallback 아님)로 끝낸다. **관찰 분류 예외의 범위**: 페르소나·카드·문서·분류 호출은 잔액이 `OBSERVE_RESERVE`(3만 토큰) 이하가 되면 멈춘다. 관찰 분류만 그 남은 몫으로 계속 돈다. 잔액이 0이면 관찰도 부르지 않고 label null(분류 실패)로 둔다. **(재확인 2 정정)** 보장하는 것은 "매 호출 전 잔액 검사"까지다. 호출 하나의 입력·출력이 남은 잔액보다 클 수 있으므로 세션 합계가 300k를 넘지 않는다는 강한 보장은 아니다(마지막 호출 하나만큼 넘을 수 있음) | `test_session_limits.py::test_tool_loop_checks_budget_before_every_call`(LLM 1회 뒤 중단), `test_observe_classification_stays_inside_session_budget`, 기존 예산 테스트(관찰 몫 0으로 설정) |
| RC5 reply_fallback 복원 | **(재확인 2 정정: 이 줄은 응답 저장 직후 경계만 다뤘다. 그래프 완료 뒤 finish_run 전 경계는 재확인 2에서 고쳤다)** 응답 meta의 `fallback`을 State 메시지에 싣는다. 응답이 이미 저장된 재실행은 그 값(llm_unavailable·tool_call_limit)으로 reply_fallback을 복원한다. 메시지 실행은 finish_run 전에 끊긴 run만 다시 돌고 카운터는 finish_run과 같은 트랜잭션이라, 같은 run_id는 한 번만 센다 | `test_reply_fallback_restored_on_rerun`: 카운터 2에서 seq 9 응답 저장·agent_runs started 상태로 같은 run_id 복구 → 3·failed, 응답 1건 |
| RC6 보드 묶음과 채팅 결정 | `sessions.redivisions` 행에 `via`(board·chat)를 둔다. 같은 단계의 기록이 있으면 보드로 시작한 재분업의 1분 안 보드 PUT(행 묶음)만 허용한다. 채팅 결정은 하나가 1회다. 경로가 다른 변경은 새 재분업이라 거부한다 | `test_chat_decisions_are_each_one_redivide`: 채팅 결정 1회 수락 → 바로 다음 채팅 결정 고정 안내·분업 그대로 → 보드 PUT 422, redivisions [(before_change, chat)]. 기존 보드 한도 테스트도 통과 |
| 미리보기 마스킹 | `prompts.board_block`의 보낸 문서 미리보기에 `app.masking.mask` | 코드(관찰 입력과 같은 함수) |

명령과 결과
- `cd services/api && uv run pytest -q` → 142 passed, 4 deselected
- `make test` → api 142 · business-mcp 9 · rag-mcp 10 · report-worker 27 passed, web 11
- `make lint` → 통과

남은 것
- 6k 토큰 요약 접기는 여전히 미완료다(남은 문제 3).
- 보드 행 묶음의 1분 기준은 이 트랙이 정한 운영 규칙이다. 설계 문서(design.md "업무 중 재분업")에 "보드는 첫 재배정 뒤 1분 안 보드 PUT을 한 번의 재분업으로 센다"를 넣어 달라는 변경 요청으로 올린다.

### 재확인 2 반영 (RC3·RC5)

| 항목 | 반영 | 확인 (`services/api/tests/agent/…`) |
|---|---|---|
| RC5 그래프 완료 뒤 finish_run 전 중단 | 응답이 LLM 실패 폴백이면 respond가 `handled_stimuli`에 `reply_fallback:<message_id>` 표시를 함께 남긴다(체크포인트됨). 그래프는 끝났고 실행 기록 전에 끊긴 재실행은 route가 처리 완료로 바로 END로 가는데, 이때 이 표시로 reply_fallback을 복원한다. 응답 저장 직후 경계(`_restore`)도 같은 표시를 남긴다. 중복 집계는 없다: 카운터는 finish_run과 같은 트랜잭션에서 갱신되고, finish_run을 마친 메시지 run은 다시 실행되지 않는다(스케줄러는 started run만 재실행) | `test_session_limits.py::test_reply_fallback_counted_once_after_graph_completed`: 실패 2회 → 세 번째 실행에서 실제 runner가 그래프를 끝낸 뒤 finish_run에서 예외 → 카운터 2 그대로 → 같은 run_id 복구(LLM 호출 0회) → 3·failed, 응답 seq 9 한 건 |
| RC3 확인 요청 | 묻는 문장 판별에 끝맺음 `건가요·는가요·던가요`와 사실 확인 요청(`…했는지/됐는지/인지 … 알려·말해·확인해 주세요`)을 더했다. 규칙 분류는 질문 판정을 지시보다 먼저 한다. 결과 진술 문장이 따로 있으면(혼합 보고) 그대로 보고다 | `test_observe.py::test_report_classification_follows_intent`·`test_llm_report_kept_only_with_result_statement`에 반례 4종을 더했다(규칙·LLM 각 10건): "완료된 건가요." → question, "완료했는지 알려 주세요." → question, "다 썼는지 확인해 주세요." → question, "…썼습니다. 빠진 게 있는지 알려 주세요." → report |

명령과 결과
- `cd services/api && uv run pytest -q` → 151 passed, 4 deselected
- `make test` → api 151 · business-mcp 9 · rag-mcp 10 · report-worker 27 passed, web 11
- `make lint` → 통과

보고 분류의 한계: 판별은 끝맺음·의문사·확인 요청 패턴과 결과 단어에 기댄다. 이 패턴 밖의 질문 형식은 LLM 분류에 맡긴다. LLM이 report라 해도 결과 진술이 없으면 강등하는 보정은 남아 있다.
