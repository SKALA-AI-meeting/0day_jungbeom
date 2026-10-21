# 품질 특성 (ISO/IEC 25010) → 코드의 장치

ISO/IEC 25010:2011 제품 품질 모델의 8개 특성(괄호는 주 부특성)을 이 코드에서 무엇으로 지키는지 정리합니다.
"확인"은 그 장치를 보여 주는 테스트나 실행 방법입니다.

| 특성 | 장치 | 코드 | 확인 |
|---|---|---|---|
| **기능 적합성** (완전성·정확성) | 업무 규칙을 Spring 한 곳에: 한 번에 한 턴, 선택은 타협 단계에서 한 번, 단계 전환 검증, 마크업 검증(활성 세션 409 → 과제 404 → 종류·내용·앵커 400 → 40개 409) | `SessionService`, `ArtifactService.annotate` | `BackendFlowTest.turnRulesAndTaskContract`, `artifactsAreSeededAndMarkupsFollowTheContract` |
| | 심어 둔 체크포인트가 실제 줄을 가리키는지 카탈로그가 스스로 검사, 29개 시나리오 전부 | `artifacts.problems`, `artifacts.catalog` | `test_artifacts.test_catalog_covers_every_scenario` |
| **성능 효율성** (시간 반응성·자원 활용) | LLM 작업은 202 + SSE로 비동기, 동기 경로는 Spring에서 끝남. TOKEN 이벤트는 묶어서 전송. 관찰기·장부·감독은 병렬 노드. 대화록 토큰 예산과 최근 창 | `Controllers.Tasks`, `harness/events.py`, `graph.py`, `harness/context.py` | trace의 `total_ms`, `tokens_in/out` (`GET /api/ai/tasks/{id}`) |
| | 탐지기는 턴 응답 뒤 백그라운드, 카탈로그는 시나리오별 캐시 | `runner._detect_background`, `artifacts.catalog` | `scripts/e2e.py` 이벤트 수 |
| **호환성** (상호운용성·공존) | 계층 간 계약 문서 하나(내부 snake_case, 브라우저 camelCase). MCP Streamable HTTP. Spring은 기동 시 Agent의 작업 종류 목록을 비교 | `docs/architecture/api-contract.md`, `AgentHandlerCheck`, `GET /agent/handlers` | `test_agent_api.test_handlers_endpoint_lists_task_types` |
| | 공개 포트 2개만(18088, 18080), 나머지는 docker network 안 | `docker-compose.yml` | `docker compose -p d20 ps` |
| **사용성** (학습성·오류 방지·접근성) | 지원자 화면: 단계 안내(`MS_HINT`), 마크업 서랍(Esc·Tab 순환·포커스 복귀, 키보드 줄 선택), 오류는 입력을 가리지 않는 토스트, reduced-motion 존중, 다크 모드 토큰 | `frontend/src/modules/candidate/Session.vue`, `components/ArtifactViewer.vue`, `style.css` | 브라우저: `/s/{id}` |
| | 관리자: 로그인 후 이슈 체크리스트 먼저, 카드마다 `actions` 라벨 | `admin/Inbox.vue`, `InboxService` | `/admin/inbox` |
| **신뢰성** (가용성·결함 허용·복구성) | 모델 429/5xx 재시도 → 대체 모델; 작업 재시도(HTTP backoff, RabbitMQ `x-attempt` + DLQ); 재시도 시 멱등(START/TURN은 이미 반영된 결과를 건너뜀) | `harness/recovery.py`, `runner.py`, `queue_consumer.py` | `test_units.test_recovery_retries_then_falls_back` |
| | 멈춘 작업 닫기: watchdog(진행 없는 QUEUED/RUNNING → FAILED), 핸들러 훅, 체크리스트(REVIEW_ERROR, REPORT_FAILED), 첫 메시지 실패 시 재시작. 끝난 작업의 늦은 이벤트는 버림 | `task/TaskWatchdog.java`, `task/*Handler.java`, `task/*Inbox.java`, `SessionService.restart`, `TaskService.onEvents` | `BackendFlowTest.watchdogFailsStaleTasksButNeverWaitingApprovals`, `restartOnlyAfterAFailedStart`, `failedReportReachesTheInboxAndIsRetriedOrDismissed` |
| | 승인 대기 상태는 PostgreSQL checkpointer에 저장되어 Agent 재시작 뒤에도 같은 thread로 재개. 장부·감독 호출 실패는 규칙 기반으로 대체 | `harness/memory.py`, `harness/dialogue.py` | `test_dialogue.test_failures_in_ledger_and_director_never_break_a_turn` |
| **보안** (기밀성·무결성·책임추적성·인증) | JWT(HMAC) + BCrypt, 역할(ADMIN/CANDIDATE)과 회사 격리, 지원자는 자기 세션·`candidateVisible` 작업만 | `security/JwtService.java`, `SecurityConfig`, `SessionService.authorized`, `TaskService.canSee` | `BackendFlowTest.authAndCompanyIsolation` |
| | `/internal/**`은 내부 포트(8081)에서만 + `X-Internal-Key`, Agent API도 내부 키 | `AuthFilters.PortGuard`, `agent_api.internal` | `BackendFlowTest.internalApiOnlyOnInternalPortWithKey`, `test_agent_api.test_internal_key_and_catalog` |
| | 지원자에게 숨기는 것: 관찰 근거, 페르소나 입장, 숨은 축, 심어 둔 체크포인트, 대화 장부(뷰·SSE·도구 이벤트 모두) | `views.candidate_view`, `SessionService.candidateView`, `tools.REDACTED_ARGS`, business-mcp `_artifacts` | `test_agent_api.test_views_hide_secrets_from_candidates`, `BackendFlowTest.dialogueRoundTripsAndNeverReachesTheCandidate`, `scripts/e2e.py` `no_secrets` |
| | 변경 도구는 사람 승인(HITL), 도구 결과 PII 마스킹, 작업마다 이벤트(`task_events`)·trace 저장 | `harness/guardrails.py`, `TaskService.approve`, `TaskService.onEvents` | `test_runner.test_change_tool_needs_approval_even_when_called_directly` |
| **유지보수성** (모듈성·재사용성·분석성·수정성·시험성) | 작업 종류는 양쪽 레지스트리(Spring `TaskHandler`, Agent `Handler`), 체크리스트는 `InboxContributor`, 화면은 모듈 매니페스트 | `task/`, `app/handlers.py`, `frontend/src/modules/` | [extending.md](extending.md) |
| | 프롬프트는 버전 붙은 파일, trace에 버전·span. 테스트 더블: Spring `DISPATCH=none` + H2, Agent `fake_backend` + 프로세스 내 MCP + `MockLLM` | `app/prompts/`, `tests/fake_backend.py`, `BackendFlowTest` | Spring 17개, Agent 53개 테스트 |
| **이식성** (적응성·설치성) | docker compose 한 번으로 전체 기동, 설정은 환경 변수(`DISPATCH`, `DIALOGUE_HARNESS`, `TASK_STALE_MINUTES`, `LLM_MODEL` …). Docker 없이: checkpointer 메모리, RAG 로컬 JSON | `docker-compose.yml`, `application.yml`, `harness/memory.py` | [RUNNING.md](../RUNNING.md) |

## 측정 근거

- 대화 품질(반복·되풀이·칭찬·회피형 끼어들기·마크업 응답)의 전후 비교: [docs/eval/dialogue_harness.md](../eval/dialogue_harness.md) — 표본이 작고(시나리오 1개, 모델 1개) 유의성 검정이 없다는 한계도 그 문서에 있습니다.
- 작업당 지연·토큰: 각 작업의 `trace[]` (관리자 `GET /api/ai/tasks/{id}`), `scripts/e2e.py` 출력.
