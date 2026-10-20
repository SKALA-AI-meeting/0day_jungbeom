# e2e-runner 보고서 (P3)

브리프 `docs/handoff/briefs/brief-e2e-runner.md`. 브랜치 `track/e2e-runner`, 기준 main `eba7d8a`(api-fix 병합 포함으로 fast-forward), catalog_version `b2cc7dd7baa915ca`. `docs/common/*`·서비스 코드·`apps/web/`는 고치지 않았다.

## 1단계 중간 보고 (러너·단언·픽스처, mock)

**검증 방식: mock.** 격리 DB(임시 DB) + 실제 api 공개·내부 앱(테스트 루프 uvicorn) + 실제 business-mcp·rag-mcp 하위 프로세스 + FakeLLM(api 대본 테스트의 분류·레이블 표 재사용) + 프로세스 안 리포트 워커(SimWorker: 워커의 `build_draft`·`InternalApi`를 그대로 씀). 러너는 실 스택과 같은 공개 REST·WS로 움직이고, 시계만 DB 시각 이동으로 바꿔 끼운다. 실 스택(사용권)·실 LLM은 아직 쓰지 않았다.

| 범위(브리프) | 상태 | 확인 |
|---|---|---|
| 1. `scripts/make_session.py` | 완료. 관리자 가입 → 채용 건 → 초대 → 내부 test/sessions(`admin_email`로 관리자 회사, api-fix 병합분) → 토큰 출력 | mock 전 테스트가 이 함수로 세션을 만든다. 관리자 리포트·기록 조회가 같은 회사에서 200 |
| 2. `tests/e2e/run.py` | 완료. step 키 12개 전부, `message.new.event_id` 카드 감지(첫 연결 전 카드는 연결 직후 `/state`로 따라잡음), 제출→reporting→보고→completed, report_ready 대기 → draft → 검토(2a 검사 포함) → final → record, 내부 API·DB 수집 | `test_all_five_end_to_end`, `test_early_submit_disconnect`(실제 WS 끊김·resume), `test_restart_reconnects_without_duplicates`(프로세스 안 재시작 흉내) |
| 장애 주입 6종 | 방식 확정·코드 완료(`tests/e2e/stack.py` 표). mock 확인은 doc_fail(C5)만 | `test_one_element_document_failure`: 도구 2회 실패(HTTP 503 4건) → 카드 이력에 document_missing=true → 재실행 done, 버전 중복 없음 |
| 3. 기록 | 완료. `records/<YYYYMMDD-HHMM>-<대본>/` transcript.jsonl·observations·report_draft/final·record·summary.md(카드 예정·fired·첫 메시지와 오차, 단언 표, run_id별 도구·토큰, 토큰 합·p95, LangSmith 필터) | all_five 테스트가 파일 6개와 토큰 가림을 확인 |
| 4. 단언 1~9 | 전부 코드(`tests/e2e/asserts.py`, 함수 이름에 번호) | 아래 표 |
| 5. `tests/eval/` | 완료. 질문 10 + 유출 3 + 선점 3(정본은 prompts 픽스처, `cases.yaml`이 ref와 실행 시각만 더함), 입력 거부 3종, live 기록 작성기 | `test_eval_runs_every_case`(16건 실제 경로로 묻고 판정), `test_evidence_rejections` |
| 6. 대본 기대값 확정 | 2단계(실 실행 뒤) | — |

### 단언별 상태

| 단언 | 함수 | mock 확인 | 비고 |
|---|---|---|---|
| 1 | `assert_1_cards` | all_five·one_element·restart 통과 | 문서 카드 seq=파트×10은 DB 조회 |
| 2 | `assert_2_report` | 결함 1건 검출(아래 변경 요청 1) | 금지어 정규식은 워커와 따로 둠 |
| 2a | `assert_2a_review` | 통과 | 메모 없는 조정 400, 재조정 409, 메모 200, reviewer_total |
| 2b | `assert_2b_no_preempt` | 통과(FakeLLM 고정 문장이라 의미 없음) | 정규식 근사. 실패 시 transcript 재확인 |
| 3 | `assert_3_ai_usage` | 미확인(mock 어시스턴트는 고정 문장) | 마스킹 단언 추가: `assistant_reuse`의 `expect.masked` |
| 3a | `assert_3a_labels` | all_five·one_element 통과 | "팀장 DM으로만 알린 대본"은 현재 대본에 없음(아래 남은 것) |
| 3b | `assert_3b_tool_choice` | 미확인 | `no_assistant`에 `expect.tool_choice`·질문 step 추가 |
| 3c·3e·3f·3g | 각 함수 | all_five 통과 | 3g의 킥오프 시각은 팀장 LLM 문장이라 mock은 고정 문장에 시각을 넣음 |
| 3d | `assert_3d_early_submit` | 통과 | |
| 4 | `assert_4_report_flow` | 해시 동일·중복 review 멱등 통과. 워커 체크포인트는 mock 한계로 실패 고정 | 실 워커에서 확인 |
| 5 | `assert_5_restart` | 통과(프로세스 안 재시작) | 실 프로세스 재시작은 2단계 |
| 6 | `assert_6_faults` | doc_fail 통과 | 나머지 5종은 실 스택 필요 |
| 7 | `run.py --concurrent` | 미확인 | mock 시계가 DB 전체 시각을 당겨 동시 세션을 못 돌림 |
| 8 | `auth.checks` | 10건 전부 일치 | 타 기업 404, 지원자 doc_id로 내부 docs/send 403(testing.md 갱신 반영) |
| 9 | `assert_9_cost` | 값 기록 확인(FakeLLM이라 토큰 0) | |

### 변경 요청·질문 (mock에서 찾음)

1. **`honest_no_misattribution`이 늘 기록 없음 → fix 트랙 몫(결정됨)**. 재현: `make test-e2e`의 `test_all_five_end_to_end`. 관찰의 `claims_colleague_work`가 `{value: false, evidence_ids: []}`라 워커가 label 항목을 `classify_failed`로 바꾼다. 관찰이 aux 지표의 evidence_ids에 보고 메시지 id를 넣도록 고칠 예정이다. 단언(all_five 정직 충족 4)은 그대로 두고, mock 테스트는 이 결함을 `EXPECTED_FAILURES`로 고정했다(고쳐지면 지운다).
2. **타 기업 접근은 404로 결정됨**: testing.md를 404로 고쳤고 auth 단언도 404로 바꿨다.
3. **"동료 문서 PUT 403"은 지원자 doc_id로 내부 docs/send → 403으로 결정됨**: auth 단언을 그 호출로 바꿨다(mock 403 확인).
4. **`one_element`의 끝내 미전달 기대값은 삭제(결정됨)**: 끝내 실패하면 세션 failed가 설계다.
5. (정보) C5의 `document_missing`은 재실행 성공 시 false로 지워진다. 러너는 카드 행 이력(`event_history`)으로 중간 상태를 본다. `inject.fail_times`는 도구 호출 단위로 정했다(그래프 2회 × MCP 안 재시도 2 = HTTP 4건).

### 대본 변경(소유: e2e-runner)

- `one_element`: 보드 step에 위반 조합(2번 colleague로 다 채움 → `expect: 422`) 뒤 되돌려 확정(C1 남은 검증). `rubric_items_if_never_delivered` 삭제.
- `assistant_reuse`: 이메일·전화번호를 담은 어시스턴트 호출 1건과 `expect.masked`(요청 본문 마스킹 저장, api-fix).
- `no_assistant`: 킥오프 인사말, 팀장 DM·동료 DM 회사 문서 질문과 `expect.tool_choice`(3b).
- `README.md`: board `expect`, `inject` 단위, `tool_choice`·`masked` 키, 인수표 C1.

### 2단계에서 할 것(사용권 받은 뒤)

- 실 스택(`make infra-up` + 이 worktree의 api·business-mcp·worker, `AGENT_RUNNER=session`·`ASSISTANT_RUNNER=graph`, DB `dayzero`)으로 대본 7개, `--concurrent`, `--auth`, `--faults all`, `make eval-live`. 기록 커밋.
- `expect.rubric`·labels 확정, 모델 상향 판단 자료 1장, 파일럿 인계.
- mock에서 못 본 것: `stack.py` 프로세스 제어·프록시, 장애 5종(fired_kill·tool_kill·publish_down·final_ack_kill·report_3fail), 동시 실행, 실 워커 체크포인트, 어시스턴트 그래프 경유 3·3b, LangSmith 링크.
- 3a의 "책임감 알림을 팀장 DM으로만 알린 대본"은 지금 대본에 없다. 실 실행 전에 `restart` 또는 새 대본에 팀장 DM 알림 step을 넣을지 정한다.

### 파일

| 파일 | 내용 |
|---|---|
| `scripts/make_session.py` | 새로 |
| `tests/e2e/{run,client,asserts,records,faults,stack,auth,script}.py`, `__init__.py` | 러너·단언·기록·장애 주입·인증 |
| `tests/e2e/{conftest,test_runner}.py` | mock 테스트 6건 |
| `tests/e2e/README.md` | 실행 안내 |
| `tests/eval/{cases.yaml,evaluate.py,conftest.py,test_eval.py}`, `__init__.py` | 근거 정확성 픽스처·실행기, 테스트 3건(+live 1) |
| `scenarios/e2e/{one_element,assistant_reuse,no_assistant}.yaml`, `README.md` | 위 대본 변경 |
| `Makefile` | 타깃 추가만: `test-e2e`·`eval-live`·`e2e-concurrent`·`e2e-auth`·`e2e-faults` |

### 명령과 결과

```
make test-e2e   # 9 passed, 1 deselected(live). 결정 반영 뒤 다시 실행해도 같음
make lint       # 통과
make test       # api 162 · business-mcp 9 · rag-mcp 10 · report-worker 27 passed, web 12
```

## 2단계 중간 상태 (실 스택, 다른 머신에서 재개)

**검증 방식: 실 스택.** `make infra-up` 인프라(postgres·rabbitmq·rag-mcp 재빌드본) + 이 worktree의 api(`AGENT_RUNNER=session ASSISTANT_RUNNER=graph ENABLE_TEST_API=1`)·business-mcp·report-worker, DB `dayzero`, LLM gpt-4o-mini(제한 키), LangSmith 프로젝트 `day-zero`. 기준: main `595362b` 위로 rebase(fix-p3 병합 **전**, catalog_version `b2cc7dd7baa915ca`). `make seed` → indexed 6. 사용자 결정으로 중간에 멈췄고 스택은 모두 내렸다(8000·8001·9101·3000 LISTEN 없음 확인).

### 돌린 것과 결과

| 실행 | 기록 | 결과 |
|---|---|---|
| all_five | `tests/e2e/records/20261021-0711-all_five/` | **세션 failed**(review·collab_disagree 카드 3회 실패). 통과: 3g·9. 실패: 1·2·2a·2b·3a·3c·3e·3f·4. 토큰 172,798, 지연 p95 10.1초. 카드 fired 오차 1.1~2.4초, 카드 메시지 지연 ≤4.3초(실패 카드 제외) |
| division_refuse | `tests/e2e/records/20261021-0723-division_refuse/` | **해당 단언 전부 통과**(1·2·2a·2b·3a·3e·3g·4·9). 토큰 124,620, p95 9.7초. fired 오차 2.5~3.7초, review 카드 메시지 지연 14.6초 |
| no_assistant | 없음 | 실행 중 중단(기록 없음) |
| assistant_reuse·early_submit·one_element·restart, auth(8), concurrent(7), faults(6), eval live | 없음 | 안 돌림 |

### 찍은 결함 (all_five, fix-p3 병합 전 코드)

1. **review 카드의 동료 v2 검사 실패가 세션 전체를 failed로 만든다 (agent-session)**. 재현: `python tests/e2e/run.py --script all_five`(실 모델). 4.59분에 3번 v2만 보내고 4·5번 v2를 보내지 못했다(3c: "part 4 v2 lacks 재참여", "part 5 v2 lacks 이번 분기", 보드 3·4·5 doing에서 멈춤). review run은 `agent_runs` failed(llm_calls 2), 이벤트 attempts 3 → `sessions.failed_reason=card_failed:review,collab_disagree` → honesty_report 미발생·리포트 없음. **원인 추정**: `cards.py` 필수 카드의 `drafts.write_part`가 핵심어 검사(`draft_check_failed`)에 걸림. RunResult.error가 로그·DB 어디에도 남지 않아 확정하지 못했다 → 변경 요청: 카드 실패 사유를 로그(또는 agent_runs)에 남길 것. 기대: 핵심어 누락이 세션 실패로 번지지 않음(재생성 또는 누락 표시 후 진행).
2. **중간 점검 창 선점(재촉) 위반 (agent-session·prompts)**. 동료가 "2번 자료는 언제쯤 볼 수 있을까요?"를 카드 메시지 뒤 DM(2.61)·팀 채널(2.67)에서 다시 물었다(창 안 3회). 단언 2b 실패. 기록: transcript `ws_in` 2.54~2.71분.
3. **관찰 레이블·근거 (agent observe, 모델 판단 자료)**. planning_checkin `acknowledge`(기대 feedback). planning_division 근거가 message뿐(보드 task_event를 고르지 않음), planning_checkin 근거에 open 없음. 적응성 이후 카드는 세션 실패로 관찰 없음.
4. (확인 필요) 킥오프 직후 0.16분 팀 채널에 동료가 분업안을 먼저 제시("제 생각해본 분업안은 … 주담당님이 다시 정해 주시면 그대로 따를게요"). 픽스처상 "기본안은 참고로만"은 허용이라 2b 정규식은 잡지 않았다. 사람 판정 필요.

### 남은 것

- **fix-p3 반영 뒤 재실행**: `git rebase main`(catalog_version `80517d9fb102c7df`) → api 재기동 → `make seed` → all_five 재실행으로 honest_no_misattribution 충족 확인, 보고서 "수정 뒤 재실행" 절. 이 경우 `tests/e2e/test_runner.py`의 `EXPECTED_FAILURES["2"]`(mock 정직 결함 고정)를 지우고 `make test-e2e`.
- 대본 5개(no_assistant·assistant_reuse·early_submit·one_element·restart), 단언 6·7·8, `make eval-live`, `expect.rubric` 확정, 모델 상향 판단 자료 1장, 기록 커밋, 최종 보고.

### 다른 머신에서 재개

```
git checkout main && git pull   # e2e-runner는 main에 병합됨(43b9f7f). 새 작업은 sh scripts/worktree.sh e2e-runner 로 다시 브랜치
make infra-up                                  # postgres·rabbitmq·rag-mcp
(cd services/api && AGENT_RUNNER=session ASSISTANT_RUNNER=graph ENABLE_TEST_API=1 uv run python -m app.run) &
(cd services/business-mcp && uv run python -m business_mcp) &
(cd services/report-worker && uv run python -m report_worker) &
make seed                                      # indexed > 0
make test-e2e                                  # mock 회귀(정직 결함 고정 해제 후)
for s in all_five no_assistant assistant_reuse early_submit division_refuse; do
  uv run --project services/api python tests/e2e/run.py --script $s; done
make e2e-auth && make e2e-concurrent           # 단언 8·7 (위 스택 사용)
# 아래는 러너가 앱을 직접 띄우므로 위 세 프로세스를 먼저 내린다(8000·8001·9101)
uv run --project services/api python tests/e2e/run.py --manage-stack --script restart   # 단언 5
uv run --project services/api python tests/e2e/run.py --manage-stack --script one_element # inject(C5)
make e2e-faults                                # 단언 6, rabbitmq 정지·재기동 포함
make eval-live                                 # records/eval-live-<일시>.md
```

6분 세션 1회 약 7~8분(보고·리포트 포함). 이번 세션에서 바꾼 것: `records.py`의 LangSmith 줄이 `infra/.env`의 `LANGCHAIN_TRACING_V2`·`LANGCHAIN_PROJECT`를 읽게 함.
