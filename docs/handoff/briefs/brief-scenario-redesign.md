# 브리프: scenario-redesign 트랙 (P1)

역할: 재설계(인성 5요소·카드 7장·문서 주고받기·미션 단위 카탈로그)를 **백엔드 전체**에 반영한다. worktree `../Day-0_zaeho.worktrees/scenario-redesign`(현재 폴더), 브랜치 `track/scenario-redesign`. 기준 커밋 eeda2a1(main), 계약 커밋 eeda2a1(`docs/common/contracts.md` 고정). catalog_version: **이 트랙이 새로 발급**(`scenarios/version.py`가 `scenarios/missions/<id>/` 폴더 전체를 해시하도록 바꾸고 보고서에 값을 적는다).

## 공통 규칙
- 커밋은 자기 브랜치에만. main 병합·push 금지. 커밋 메시지는 한국어 한 문장 + 본문에 실행한 테스트 명령.
- `infra/.env`·`.env.local` 키 값 출력·복사 금지. 실제 스택: **사용 안 함**. 공용 postgres(localhost:5432)·rabbitmq(5672)·rag-mcp(9102)는 main에서 `make infra-up`으로 떠 있고, 테스트는 기존 conftest 방식의 **임시 DB·임시 스키마·임시 큐**로만 쓴다. `make up`·api 상시 기동·공용 DB 스키마 적용·seed·재색인 금지. LLM은 전부 mock(FakeLLM), 실제 호출은 `live` 마커.
- `docs/common/*`(contracts·scenario-model·rubric·data-model 등)·`docs/decisions.md`·`docs/plan.md`·`docs/handoff.md`는 수정하지 않는다. 계약이 바뀌어야 하면 보고서에 "변경 요청"(영향 경로·요청/응답 예시)으로 적고 미확정 부분만 대기, 독립 작업은 계속한다.
- 다른 트랙(web-redesign)이 같은 시각에 `apps/web/`을 고치고 있다. `apps/web/`은 읽기만 한다.
- TDD, happy path 중심(`docs/dev-process.md`). 완료 기준 한 줄당 테스트 하나. 입력 조합 전수·경계값 나열 금지.

## 읽을 것 (순서대로)
1. `AGENTS.md`, `PRD.md`
2. `docs/common/contracts.md`(정본: REST·WS·State 18필드·MCP 도구·내부 API·큐 메시지·Report·전체 기록), `scenario-model.md`(120분 시각·카드 7장·division_min·관찰 창), `rubric.md`(항목 id·레이블·근거 타입·사유 문장·summary 세 수), `data-model.md`(documents·versions·shares·opens·revisions·final_document·tasks·task_events·observations·connection_gaps), `harness.md`, `testing.md`
3. `docs/api/design.md`(조립·SessionService·스케줄러·제출·문서/보드·관리자 보충·**완료 기준**), `docs/mcp/design.md`(business-mcp 도구·rag 색인 키), `docs/worker-infra/design.md`(카드 단위 평가표·summary·facts·큐·DLQ), `docs/agent/design.md`(State·assistant 라우터 훅의 자리만 확인, 전이표·observe 구현은 P2 agent-session 몫)
4. `docs/plan.md`(scenario-redesign 행·M1.5 완료 기준·"최소 테스트 6건 배정" 표의 scenario 열·파일 소유권·병렬 규칙), `docs/dev-process.md`, `docs/decisions.md`의 2026-10-20 "인성 5요소·문서 주고받기 재설계"·"개발 전 리뷰 3종 반영"·"역할별 모델과 상향 규칙" 절
5. `docs/handoff/reviews/review-redesign-triage.md`(반영 지시서), `review-plan.md` 3·4절
6. `docs/handoff/reports/fixtures-align-report.md`(깨진 테스트 1개, contracts 어긋남 4건 중 2건은 고쳐짐: summary `unmet`, candidate_count=사람 수. 남은 2건: 리포트 최상위 evidence 형태는 섹션 근거와 같은 전체 형태, 시작 직후 State 픽스처는 필요하면 이 트랙이 추가), `tests/fixtures/README.md`와 `tests/fixtures/contracts/*.json` 73개(**생산자인 이 트랙의 응답이 이 파일과 같아야 한다**)
7. 기존 코드와 보고서: `services/api/`(app/services·routers·scheduler·models·agent/runner.py·tests), `services/business-mcp/`, `services/rag-mcp/`, `services/report-worker/`, `scenarios/`(catalog.yaml·prompts·documents·e2e·version.py), `infra/db/schema.sql`, `tests/conftest.py`. 앞선 보고서 `docs/handoff/reports/{foundation,api-admin,api-candidate,business-mcp,rag-mcp,worker,prompts,agent-min}-report*.md`의 "다른 트랙에 알릴 것"과 `docs/handoff.md` "이전 라운드의 미처리 변경 요청"(이 트랙 몫: `app/run.py` 기동 시 runner 초기화·종료 시 aclose, `tests/conftest.py`·`services/api/tests/conftest.py` 갱신).

## 허용 파일 (docs/plan.md 소유권 scenario-redesign 행 + 공용 변경 담당)
`scenarios/missions/`(prompts 포함, 새로 만듦), `scenarios/catalog.yaml`(삭제·이관), `scenarios/version.py`, `scenarios/prompts/`(missions로 이관), `scenarios/documents/`(missions로 이관), `scenarios/e2e/` 초기 대본, `infra/db/schema.sql`, `services/api/` 전부(라우터·모델·SessionService·scheduler·queue 경계·`tests/conftest.py`·assistant 라우터 훅. `app/agent/`는 기존 테스트가 새 State·계약에서 통과하게 하는 **최소 수정만**, 전이표·observe·카드 실행은 금지), `services/business-mcp/`, `services/rag-mcp/`(색인 키·catalog_version만), `services/report-worker/`, `tests/fixtures/contracts/`(계약 예시와 어긋남이 **발견될 때만** 변경 요청과 함께), `scripts/seed.py`, `scripts/make_session.py`(있으면).
사전 승인된 공용 변경(이 파도의 공용 변경 담당은 이 트랙): 루트 `tests/conftest.py`, 각 서비스 `pyproject.toml`·lockfile, `Makefile`, `infra/docker-compose*.yml`(scenarios 마운트 경로), `infra/.env.example`(새 env 이름 추가, 값 없이). `apps/web/`·`docs/common/`은 금지.

## 범위 (docs/plan.md M1.5 scenario-redesign 행)
1. **미션·스키마**: `scenarios/missions/planning/` 카탈로그(요소 5개 → cards[] 7장: planning_division 10·collab_help 30·planning_checkin 45·responsibility_delay 60(공개 70)·adaptability_change 75·collab_disagree 90·honesty_report 110, 요소별 meaning·how_we_see, fixed_opinions(반대 의견 내용 고정), 적응성 카드 새 내용(핵심 기능 축소·일정 당김), 레이블 7세트, 선점 금지 6건·팀장 DM 규칙 픽스처 문장, 대본 초기본), 프롬프트·회사 문서 이관, `version.py`(미션 폴더 전체 해시), `catalog.yaml` 삭제, `schema.sql`(documents·document_versions·document_shares·document_opens·document_revisions·final_document·tasks·task_events·observations(카드 단위 키)·connection_gaps·sessions.completed_at·deadline_at·positions.mission_id).
2. **API·도구 계약 검증**: 조립(`scenario-model.md` 수치와 일치), SessionService 전이 전부(reporting·cancelled·regenerate 포함, 멱등), 시작 시 tasks 5행 null·지원자 문서 5개·최종본 생성, 문서/보드/reporting 라우터, 스케줄러(이벤트 ±10초, 재시작 재실행, 미발행 재발행, 만료 큐 발행), 내부 API(`update_observation` PATCH `{card_id, window_start, metrics_patch, run_id}`, division PUT, task_events, send 멱등), 관리자 record·regenerate·notes·candidates 평탄화 `met·unmet·no_record·score_source·by_element`+`display_group`, candidate_count=사람 수, business-mcp 도구(send_document·get_shared_documents·set_division·record_observation·update_observation 등 계약 표 전부), rag-mcp 색인 키, assistant 라우터 훅(candidate.py에 자리만), `app/run.py` runner 초기화·aclose. 깨진 `services/api/tests/test_candidate.py`를 새 State로 고침.
3. **워커·픽스처 인수**: report-worker 카드 단위 평가표·summary 세 수·facts·honesty_facts·notes·ai_usage.events·record_ref, document_missing 사유, 큐 2종·재시도·DLQ 유지. 생산자(api·MCP·worker)의 실제 응답이 `tests/fixtures/contracts/`와 같은지 양쪽에서 확인(`load_contract`로 비교하는 테스트).

**최소 테스트 6건(scenario 열, 고정 입력으로 증명)**: ① 보드만으로 분업 확정(담당 없는 5행 → PUT → division·task_events·WS·동료 자극 저장) ② 카드 전 계획(시작 전후 결정 시각·보드 이력 보존) ③ 창 밖 약속 이행(observations PATCH·멱등, 워커가 갱신값 소비) ④ 무관한 편집(revisions 보존, target_applied=false면 미충족) ⑤ 문서 제공 실패(MCP 오류·이벤트 failed 저장·워커 document_missing) ⑥ reporting 재접속(resume·JWT·state.deadline_at·허용 채널). 각각 어느 테스트 파일·함수인지 보고서 표에 적는다.

## 내부 관문 3개 (중간 보고 → Codex 리뷰 → 다음)
관문 1(미션·스키마) → 관문 2(API·도구 계약 검증) → 관문 3(워커·픽스처 인수). **관문마다** 해당 부분 테스트를 통과시키고 커밋한 뒤 `docs/handoff/reports/scenario-redesign-report.md`에 그 관문 절을 추가·갱신하고 **응답을 끝낸다**(경로 한 줄). 오케스트레이터가 같은 탭 오른쪽 Codex 리뷰를 돌리고 "관문 N 리뷰 반영 후 관문 N+1 진행"을 보내면 이어간다. 리뷰 결과는 worktree의 `REVIEW.md`(추적 안 함)에 있다.

## 완료 기준 (관문 3 끝)
`make test`·`make lint` 통과(worktree에서, web 부분은 main 기준 그대로), 조립 결과가 `scenario-model.md` 수치와 일치, `docs/api/design.md` 완료 기준(foundation·api-admin·api-candidate 줄) 전부, 최소 테스트 6건 통과, 생산자 응답 = 공용 픽스처, 새 catalog_version 값. 완료 보고에 명령·결과·검증 방식(mock/격리 DB)을 줄마다 적는다. 임시 DB·스키마·큐를 정리한다.

## 보고
`docs/handoff/reports/scenario-redesign-report.md`에 관문별 절: 기준 커밋, 완료 기준 각 줄의 명령·결과·검증 방식, 6건 배정 표(파일·함수), 수정 파일, 남은 문제, 변경 요청(계약·픽스처·docs/common), 다른 트랙에 알릴 것(web-integrate: 실 API·WS 응답에서 픽스처와 다른 점 / agent-session: State·자극·runner 인터페이스·assistant 훅 / agent-assistant: 훅 시그니처 / e2e-runner: 대본 초기본·make_session), 후속 인수자에게 넘길 것(catalog_version, 7카드 레이블, fixed_opinions, 선점/팀장 DM 픽스처, 대본, 소유권 반환 목록: `app/agent/`→agent-session, `scenarios/missions/` 문구→prompts, `scenarios/e2e/`→e2e-runner). 마지막 응답은 경로 한 줄.
