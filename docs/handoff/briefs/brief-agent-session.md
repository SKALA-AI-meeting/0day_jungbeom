# 브리프: agent-session 트랙 (P2, M2 = 세션 그래프 전체)

역할: agent-min(respond 경로)을 **M2 세션 그래프 전체**로 완성한다. worktree `../Day-0_zaeho.worktrees/agent-session`(현재 폴더), 브랜치 `track/agent-session`. 기준 커밋 main 최신(4b849b8 이후, scenario-redesign 병합 포함), 계약 커밋 37bed0b, catalog_version `b2cc7dd7baa915ca`(미션 `planning`).

## 공통 규칙
- 커밋은 자기 브랜치에만. 키 값 출력 금지. TDD happy path(완료 기준 한 줄당 테스트 하나). 주석은 역할·알아야 할 로직·예외 의도 수준(AGENTS.md).
- `docs/common/*`·`docs/plan.md`·`docs/handoff.md`·`services/api/app/services/`·라우터·`scenarios/missions/` **문구**·`tests/fixtures/contracts/`는 수정 금지. 필요하면 보고서 "변경 요청"(영향 경로·예시)으로 올리고 독립 작업은 계속.
- 같은 시각에 agent-assistant(`app/agent/assistant/`)·web-integrate(`apps/web/`)·web-polish가 돈다. **`app/agent/{llm,guard,mcp_client}/`의 공개 함수·반환형·허용 도구 표는 동결**(agent-assistant가 import만 한다). 바꿔야 하면 추가만 하고 기존 시그니처는 유지.
- LLM은 테스트에서 FakeLLM. 실제 호출은 `@pytest.mark.live`(gpt-4o-mini, `infra/.env.local`의 제한 키; 역할별 `MODEL_*`는 비워 둔다). `make test-live`는 보고서에 결과만 적고 통과를 요구하지 않는다(모델 상향 판단 자료).
- 실제 스택: **사용 안 함**. 공용 postgres·rabbitmq는 기존 conftest의 임시 DB·스키마로만. MCP 서버 2개는 테스트 프로세스 안(fastmcp 인메모리 또는 서브프로세스)에서.

## 읽을 것
AGENTS.md, `docs/agent/design.md` 전체(인터페이스·전이표·노드·페르소나·observe·복구·**완료 기준**), `docs/common/harness.md`·`contracts.md`(MCP 도구 11개·허용 목록·내부 API·State 18필드·관찰 PATCH)·`scenario-model.md`·`rubric.md`(지표·레이블·근거 타입 단일 표), `docs/plan.md`(agent-session 행·6건 배정 agent 열·소유권), `docs/dev-process.md`, `docs/decisions.md` 2026-10-20·10-21 절, `docs/handoff/reports/scenario-redesign-report.md`의 "다른 트랙에 알릴 것"(agent-session: Stimulus `division`·`task_event_ids`, `DOCUMENT_MISSING` 접두어, 보고 감지는 분류 PUT kind=report → reported_at, State 18필드 `current_card`·`report_requested`, 보드 블록 입력 get_shared_documents, or_on_submit 카드 즉시 실행, 관찰 `metrics.<지표> = {value, evidence_ids}`·`aux.related_message_ids`·`window_missed`, 분류 실패면 aux 미사용, promise_kept 종료 PATCH)와 68행 레이블 규칙 변경 요청, `docs/handoff/reports/agent-min-report.md`(1단계 구조 메모), `scenarios/missions/planning/`(mission·cards·persona·prompts·fixtures: preemption 6·manager_dm 5·context_leak 6·grounding), `scenarios/e2e/*.yaml`(대본 7개, README의 step 키), 기존 코드 `services/api/app/agent/`·`app/agent/runner.py`(Stimulus·RunResult·AssistantRunner)·`app/services/{runs,events,board,documents,session,context}.py`·`app/scheduler.py`·`services/business-mcp/`·`services/rag-mcp/`·`services/report-worker/report_worker/rubric.py`(워커가 읽는 관찰 형태).

## 허용 파일
`services/api/app/agent/{session,observe,llm,guard,mcp_client}/`, `services/api/app/agent/runner.py`(Protocol 추가만), `services/api/tests/agent/`(conftest 포함, 새 폴더), `services/api/tests/test_agent_*.py`, `scenarios/e2e/`의 대본 **기대값 보강**(step 키 추가는 README에 적고 e2e-runner에 알림), `services/api/pyproject.toml`(의존성 추가 시). `app/services/context.py`는 runner 선택 부분만.

## 범위 (docs/agent/design.md M2)
- 전이표 전체: kickoff(팀장 1·동료 인사 2) → 카드 7장 inject(brief/text, sends_document 카드는 동료 문서 생성·send_document, checkin·review 공유, 반대 의견은 카탈로그 fixed_opinions·target_rule) → respond(classify recipient·kind: question∣instruction∣redivide∣progress_query∣doc_feedback∣report∣other) → division 자극(work_notes·동료 담당 갱신, set_division 없이) → report_request → end(열린 창 닫기, promise_kept PATCH).
- observe: 카드 단위 창(키 card_id·window_start, planning_division은 0), `compute_metrics`(rubric.md 지표, 기록 기반) + `classify`(FakeLLM, temperature 0, 허용 레이블 외 unclassified, 지원자 활동 없으면 no_evidence·LLM 미호출), record_observation·update_observation, 창 밖 메시지는 related_card만, 정직 카드 facts 대조(misattributes).
- 작업 기억: 지시 누적(도움 카드 "재참여", 적응성 뒤 "후속 모임"), 초안 v1(45)·완성본 v2(90)·답글 뒤 v3, both 파트 골격 포함, 진행 질문에 같은 progress, 보드 doing→done.
- 복구: LLM 재시도 2회 → 규칙 폴백(seq 9), 3회 실패 세션 failed, 같은 run_id 재실행 멱등(handled_stimuli·seq 슬롯), 문서 전송 실패는 `RunResult(ok=False, error="DOCUMENT_MISSING: ...")`, 체크포인터 PostgresSaver.
- 컨텍스트 허용 목록(미래 카드·레이블·어시스턴트 대화·보내지 않은 문서 제외), guard, 팀장 DM 규칙(판단 요청은 "주담당이 정해 주세요"), 선점 금지 6건.
- `AGENT_RUNNER=session`이 기본으로 동작하도록(테스트는 명시).

## 완료 기준 (docs/agent/design.md "완료 기준" M2 이하 전부)
6분 세션 + 대본 3개(all_five·early_submit·division_refuse)로 카드 전부 정시(±10초)·분업 되돌림·조기 제출 보고 요청·reporting·재시작 재실행·허용 밖 도구 거부·미공개 문서 답변·보내지 않은 문서 답변·팀장 DM 판단 요청·LLM 3회 실패 failed·LangSmith run_id, 근거 정확성 픽스처 10건, 작업 기억 검사, 반대 의견 대상, 관찰 7장 픽스처, 최소 테스트 agent 열 5건(보드만으로 분업·카드 전 계획·창 밖 약속 이행·무관한 편집·문서 제공 실패), 선점 금지 6건 픽스처. `cd services/api && uv run pytest`, 루트 `make test`·`make lint`. live 1회(`make test-live`) 결과는 보고에.

## 보고
`docs/handoff/reports/agent-session-report.md`: 기준 커밋, 완료 기준 줄별 명령·결과·검증 방식(mock/격리 DB/실 LLM), 6건 배정 표(파일·함수), 수정 파일, 남은 문제, 변경 요청, 다른 트랙에 알릴 것(e2e-runner: 대본 step 키·기대값, web-integrate: 실제 세션에서 보이는 메시지·문서 흐름, prompts: 문구 요청), live 결과로 본 "모델 상향 판단 자료"(레이블 정확도·규칙 준수·카드 실패율). 마지막 응답은 경로 한 줄. 컨텍스트가 부족하면 /compact 후 이어간다.
