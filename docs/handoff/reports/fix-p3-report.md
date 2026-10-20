# fix-p3 완료 보고

- 브랜치: `track/fix-p3`, 시작 커밋: `60d2f76`.
- 범위: 브리프 1~5 구현, 6은 채널 계약 부재로 지시대로 보류.
- 검증 방식: FakeLLM·메모리 그래프·httpx mock·실행별 임시 DB·vitest. 공용 앱, 공용 DB `dayzero`, 실 LLM, 공용 RabbitMQ는 사용하지 않았다. 기존 연결 테스트의 API·MCP는 임시 포트와 임시 DB로 실행하고 픽스처가 종료한다.

## 항목별 변경과 검증

| 항목 | 수정 파일 | 테스트·결과 |
|---|---|---|
| 1. 진행 알림 | `services/api/app/agent/session/nodes.py` | `tests/agent/test_fix_p3.py::test_started_reaches_hub_while_classification_waits`: FakeLLM 분류를 Event로 멈춘 사이 hub에 started가 먼저 도착하고, 응답 저장 뒤 finished가 한 번 도착함. 통과 |
| 2. 메시지 페이징 | `services/api/app/agent/session/common.py`, `store.py` | `tests/agent/test_fix_p3.py::test_refresh_reads_dm_after_fifty_assistant_messages`: 정확히 같은 created_at·t_min의 assistant 50건 뒤 DM 조회, 기존 체크포인트 재조회, 커서 재조회 중복 없음, 페이지 상한 소진 오류. 격리 DB에서 통과 |
| 3. 정직 aux 근거 | `services/api/app/agent/observe/__init__.py` | `tests/agent/test_observe.py::test_honesty_aux_keeps_report_evidence_for_true_and_false`: related_card 없는 보고도 판정 근거 id 유지, true·false 모두 근거 포함, 실제 워커 평가 `honest_no_misattribution=1`, no_record_reason=null. 통과 |
| 4. 팀장 보고 문구 | `scenarios/missions/planning/prompts/manager.md`, `cards.yaml` | `services/api/tests/test_scenario.py::test_manager_report_request_rules_are_scoped_to_report_card`: 보고 요청에서만 재촉 문장 사용, 현황 대행 금지, honesty_report·미선택 report_request 양쪽 조립 확인. 통과. 실제 모델의 발화 준수는 미검증 |
| 5. 짧은 연결 끊김 | `apps/web/components/admin/report-view.tsx`, `format.ts` | `report-view.test.tsx` 신규 vitest 1건: 1분 이상 목록 유지, 1분 미만은 기본 접힌 “짧은 끊김 2회”, 펼친 내용은 HH:MM:SS와 지속 초 표시, 기존 카드 창 겹침 칩 유지. 통과 |
| 6. 입력 중 채널 | 수정 없음 | State.active_runs와 agent.progress 모두 채널이 없어 보류. 아래 변경 요청 |

테스트 파일 경로의 `tests/agent/`는 `services/api/tests/agent/`다. 워커 코드와 공용 계약·픽스처는 수정하지 않았다.

페이징은 이미 API 안에서 DB를 읽는 `DbAgentStore`에 `(created_at, id)` 커서 조회를 추가했다. MCP list_messages에는 offset·정확한 커서 입력이 없어서 그 계약과 다른 트랙의 MCP 코드를 변경하지 않았다. 최근 메시지에 created_at을 보존하고, 기존 체크포인트에 없으면 처음부터 다시 읽는다. 50건씩 최대 5페이지를 읽고 끝에 도달하지 못하면 `list_messages:page_limit_exceeded`로 실패하며 부분 조회를 성공으로 처리하지 않는다.

진행 알림은 분류 전 시작하고, 응답·채팅 분업 양쪽 공통 종료 노드에서 끝낸다. 응답 저장 실패는 finished 대신 failed다. 정직 aux는 창 안의 팀 채널·팀장 DM에서 kind=report인 메시지 id를 근거로 삼으며, 다른 aux도 false라는 이유로 기존 판정 근거를 제거하지 않는다.

## 카탈로그 인수

새 `catalog_version`: **`80517d9fb102c7df`**.

카탈로그 문구가 바뀌었으므로 기존 채용 건의 고정 scenario에는 소급 적용되지 않는다. 새 문구 검증에는 새 버전으로 조립한 채용 건·세션을 사용해야 한다. 이 트랙에서는 seed·색인·배포를 실행하지 않았다.

## 변경 요청

6번은 브리프의 보류 조건에 해당한다. `docs/common/contracts.md`의 State 예시와 agent.progress 표에는 `{run_id, actor, node}`만 있고 채널이 없다. 실제 `services/api/app/routers/candidate.py::_run_view`, `SessionAgentRunner.run`의 progress 발행, `apps/web/components/office/types.ts`, `reducer.ts::progressLabels`도 같다.

오케스트레이터가 계약·픽스처 담당에게 다음 변경을 배정해야 한다.

- 메시지 실행의 응답 채널을 State.active_runs와 agent.progress에 공통으로 제공한다. 예: `{"run_id":"…","actor":"colleague","node":"respond","channel":"dm"}`. 팀장 DM은 `manager_dm`, 팀 채널은 `team`.
- 재접속 스냅샷과 started·tool_start·tool_end 프레임에서 동일 채널을 유지해야 한다. 카드처럼 여러 채널에 발행하는 실행의 채널 표기 규칙도 계약에서 정한다.
- 영향 경로: `docs/common/contracts.md`, `tests/fixtures/contracts/`, `services/api/app/routers/candidate.py`, 세션 실행기 progress 발행, `apps/web/components/office/types.ts`, `reducer.ts`, `office-view.tsx`.
- 이후 프론트는 현재 열린 채널의 실행만 입력 중으로 표시하고 DM·팀 채널 이동과 재접속 복원을 검증한다. 이 트랙에서 채널을 actor로 추측해 넣지는 않았다.

브리프가 참조한 `docs/handoff/reports/e2e-runner-report.md`는 시작 커밋에 없어 읽지 못했다. `docs/handoff.md` P3 요청에 명시된 정직 근거 결함을 기준으로 처리했다. web-integrate 보고서도 현재 worktree에는 1라운드와 2라운드 확인 목록까지만 있다.

## e2e-runner 인계

- `all_five`: 새 catalog_version으로 생성 후 공정 보고의 `honest_no_misattribution`이 기록 없음이 아닌 충족인지 다시 확인한다. 실제 분류 대기 중 started와 응답 저장 뒤 finished 순서도 확인한다.
- 정직 선택·미선택 대본: 팀장이 현황을 대신 요약하지 않고 보고를 요청하는지, 킥오프·일반 답변에 재촉 문장을 붙이지 않는지 실제 모델로 재확인한다. 선택 시 honesty_report, 미선택 시 report_request다.
- web-integrate `apps/web/e2e/session.mjs`: 새 세션에서 짧은 연결 끊김 접힘·초 표시와 기존 카드 겹침 칩을 다시 확인한다. 이 파일과 다른 트랙 대본은 수정하지 않았다.
- 채널별 입력 중 표시는 계약 변경 뒤 재실행해야 하며 현재 완료로 간주하지 않는다.

## 전체 검사

- 표적 검사: `uv run --project services/api pytest -q services/api/tests/agent/test_fix_p3.py services/api/tests/agent/test_observe.py services/api/tests/test_scenario.py` → **45 passed**(임시 DB 환경에서 실행).
- 프론트 표적 검사: `cd apps/web && pnpm test --silent=true components/admin/report-view.test.tsx` → **2 passed**.
- `UV_CACHE_DIR=/private/tmp/fix-p3-uv make lint` → ruff check·format, eslint, prettier 모두 통과.

전체 `make test`는 `/private/tmp/fix-p3-checks.py all` 래퍼로 실행한다. 래퍼가 postgres 관리 DB에서 `fix_p3_checks_<랜덤>` DB를 만들고 DATABASE_URL을 이 DB로 바꾼 뒤 `make test`를 호출한다. API·rag 테스트는 그 안에서 다시 각자 임시 DB를 만들고, worker는 임시 스키마를 쓴다. 래퍼는 마지막에 부모 DB도 제거한다. 공용 RabbitMQ는 접속하지 않도록 닫힌 로컬 포트로 지정했다. 실제 LLM·트레이싱은 사용하지 않고, OpenAI 클라이언트 생성만 필요한 기존 테스트에는 더미 인증값과 닫힌 로컬 URL을 사용했다.

첫 전체 검사에서는 빈 인증값으로 인해 `test_assistant_endpoint_uses_graph_runner`의 클라이언트 생성이 실패했다(165 passed, 1 failed, 5 deselected). 테스트가 호출 전 FakeLLM으로 교체하는 것을 확인한 뒤 검증 환경의 더미 인증값만 보완해 다시 실행했다. 이 때문에 제품 코드나 기존 테스트를 변경하지 않았다.

최종 전체 검사: **`make test` 종료 코드 0**.

| 대상 | 최종 결과 |
|---|---|
| API | 166 passed, 5 deselected(live 제외) |
| business-mcp | 9 passed |
| rag-mcp | 10 passed, 1 deselected(live 제외) |
| report-worker | 26 passed, 1 skipped(RabbitMQ 테스트: 공용 브로커 미사용) |
| web | 11개 파일, 13 passed |

Python 합계 211 passed, web 13 passed다. 실 브로커 DLQ 경로는 이 검증에서 확인하지 않았다. 임시 DB `fix_p3_checks_20762abd`와 그 테스트의 자식 DB·스키마는 픽스처와 래퍼가 제거했다. 최종 `git diff --check`도 통과했다. 검사 원문은 `/private/tmp/fix-p3-make-test.log`에 있다.

## 커밋

첫 작업에서는 `git add`가 본 저장소 Git 관리 경로의 `index.lock` 생성에서 `Operation not permitted`로 거부되어 미커밋 상태로 인계했다. 사용자의 후속 커밋 지시를 받고 같은 `track/fix-p3` 브랜치에서 재시도해 스테이징에 성공했다. 보고서를 포함한 변경 파일 13개를 하나의 커밋으로 묶으며, 커밋 본문에 실행한 테스트 명령을 기록한다.
