# 시스템 아키텍처 (캡스톤 레퍼런스 아키텍처 적용)

## 1. 요구사항 → 아키텍처 결정

| 요구사항 | 결정 | 코드 |
|---|---|---|
| LLM 응답은 수 초~수십 초 | 질문은 **작업으로 접수해 202**를 바로 돌려주고, 진행은 **SSE 이벤트**로 보낸다 | `POST /api/ai/tasks`, `Controllers.Tasks`, `SseHub` |
| 업무 규칙은 한 곳에서 | business-mcp는 DB에 직접 접근하지 않고 Spring `/internal/**`만 호출 | `SessionService`, `mcp_servers/business/server.py` |
| 브라우저에 노출되는 주소 최소화 | 공개 포트는 frontend·backend뿐, 나머지는 docker network 안 | `docker-compose.yml`, `AuthFilters.PortGuard` |
| 데이터를 바꾸는 도구는 사람이 확인 | 변경 도구 앞에서 Agent가 상태를 저장하고 멈춘 뒤, 승인받으면 **같은 thread id로 재개** | `report_graph.py`(interrupt), `TaskService.approve` |
| 답변에는 근거 문서가 있어야 | 문서는 미리 색인하고 rag-mcp가 Vector DB에서 근거를 찾는다 | `rag_pipeline/`, `mcp_servers/rag/` |
| 사람이 결정할 일은 한곳에 | Agent가 멈춘 작업과 Agent가 닫지 못한 실패를 관리자 **이슈 체크리스트**로 모은다 | `InboxService`, `TaskHandler.inboxItem`, `InboxContributor` |
| 어떤 작업도 조용히 멈추지 않게 | 진행 없는 작업은 **watchdog**이 FAILED로 닫고, 작업 종류별 훅이 업무 상태를 정리 | `task/TaskWatchdog`, `TaskHandler.onFinished` |
| 작업 종류를 쉽게 더할 수 있게 | Spring `TaskHandler`·Agent `Handler` 레지스트리, 기동 시 양쪽 목록 비교 | `task/TaskHandlers`, `app/handlers.py`, [extending.md](extending.md) |

## 2. 구성도 (전체)

```
브라우저 ─HTTPS─► frontend(nginx :80, 공개) ─/api/**─► backend(Spring Boot :8080, 공개)
                                                         │  JWT · 업무 API · 작업 접수 · SSE 중계
                                              내부 HTTP / RabbitMQ (agent.tasks, DLQ)
                                                         ▼
                                  agent(FastAPI :8000, 내부) ── Harness ── LangGraph
                                    │ MCP Streamable HTTP /mcp
              ┌─────────────────────┼──────────────────────┐
        business-mcp :9101    rag-mcp :9102          detector-mcp :9103 ──► Gemini
              │ /internal/** (:8081, X-Internal-Key)      │
              ▼                                           ▼
        backend ── JDBC ──► postgres(업무·작업 이력)   vectordb(pgvector: 문서 chunk·임베딩)
        agent ── checkpointer ──► postgres(agentstate)
        OpenAI ◄── agent 만 HTTPS (키는 .env)
        오프라인: rag-indexer = Documents → Chunking → Embedding → Indexing → vectordb
```

## 3. 처리 순서 (표 5-3)

| 번호 | 구간 | 처리 | 프로토콜 |
|---|---|---|---|
| 1 | Vue → Spring | `POST /api/ai/tasks` (TURN). 규칙 검증 후 메시지를 저장하고 **202 taskId** | HTTPS |
| 2 | Spring → Agent | 작업 상태를 저장한 뒤 실행 요청 (`DISPATCH=rabbit`: 큐에 발행, `http`: POST /agent/tasks) | 내부 HTTP / AMQP |
| 3 | Agent → LLM | Harness가 Instructions·Context를 붙여 호출, 모델이 도구를 제안 | HTTPS |
| 4 | MCP Client → MCP Server | `tools/call`. 변경 도구(`save_report`)는 Guardrails가 승인 전까지 멈춘다 | MCP /mcp |
| 5 | business-mcp → Spring | 업무 데이터는 `/internal/**` 로 읽고 바꾼다 (Spring이 규칙을 다시 검증) | 내부 HTTP |
| 6 | rag-mcp → Vector DB | 질문과 가까운 문서 chunk와 출처를 반환 | SQL |
| 7 | Agent → Spring → Vue | 진행 이벤트 `TOKEN · TOOL_START · TOOL_END · PROGRESS · APPROVAL_REQUIRED · DONE · FAILED` 를 SSE로 중계 | HTTP / SSE |
| 8 | Spring 내부 | DONE/FAILED(또는 watchdog 시간 초과) → `TaskFinishedEvent` → `TaskHandler.onFinished` → 필요하면 체크리스트 항목 | — |

## 4. API 계약 (표 5-8, 5-9)

| Method | Path | 설명 | 응답 |
|---|---|---|---|
| POST | `/api/ai/tasks` | 작업 생성 (`type`: TURN · REPORT). START·ACCOUNT_REVIEW는 세션 시작·가입 때 Spring이 만든다 | 202 taskId |
| GET | `/api/ai/tasks/{id}` | 상태·결과·trace 조회 (trace는 관리자에게만; SSE 이벤트에는 없음) | status, result, trace[] |
| GET | `/api/ai/tasks/{id}/stream` | 진행 이벤트 | text/event-stream |
| POST | `/api/ai/tasks/{id}/approval` | 승인·반려 (같은 thread id로 재개) | 202 |
| GET | `/api/ai/tasks?mine=true` | 내 작업 이력 (관리자는 회사 전체) | 목록 |

그 밖의 공개 API: `/api/auth/{signup,login,me}`, `/api/auth/candidate/{signup,login}`, `/api/me`(계정·심사 진행 `/review/stream`·내 세션), `/api/meta`, `/api/scenarios/{id}`, `/api/invites/{token}`,
`/api/sessions/{id}`(조회·노트·종료·`/restart`·`/annotations`), `/api/admin/{inbox,accounts,sessions,invites}`, `/api/admin/sessions/{id}/report/dismiss`.
새 자원(과제·마크업·체크리스트)의 필드는 [api-contract.md](api-contract.md)가 기준이다.
Vue는 AI 서버 주소를 모른다. 작업 상태는 `QUEUED → RUNNING → (WAITING_APPROVAL →) DONE | FAILED | REJECTED`.

| 작업 종류 | 만드는 곳 | 지원자에게 보임 | 사람 승인 | 끝난 뒤 (`TaskHandler.onFinished`) |
|---|---|---|---|---|
| ACCOUNT_REVIEW | 지원자 가입 | 아니요(단계만 `/api/me/review/stream`) | 애매할 때 | 결정 없이 끝나면 계정 `REVIEW_ERROR` → 체크리스트 |
| START | 세션 시작, `/restart` | 예 | 없음 | 실패 시 지원자가 다시 시작 |
| TURN | 지원자 메시지 | 예 | 없음 | — |
| REPORT | 세션 종료, 관리자 재요청 | 아니요 | 공개 전 항상 | `report_status` 반영, 실패 시 REPORT_FAILED → 체크리스트(다시 만들기/넘기기) |

## 5. 구성 요소별 금지 사항 준수 (표 5-4)

| 구성 요소 | 금지 사항 | 어떻게 막았나 | 확인 |
|---|---|---|---|
| Vue 3 | 권한 판단, AI 서버 직접 호출 | `api.js`는 `/api/**` 만 호출. 권한은 JWT 역할·회사로 Spring이 판단 | nginx 설정, `BackendFlowTest.authAndCompanyIsolation` |
| Spring Boot | LLM 호출 | Spring에는 모델 SDK가 없고 Agent HTTP·큐 클라이언트만 있음 | 의존성 목록 |
| FastAPI Agent | DB 직접 쓰기 | 업무 데이터는 business-mcp만 경유. Agent에는 업무 DB 접속 정보가 없음(checkpointer 전용 DB만) | `tests/test_runner.py` |
| business-mcp | 업무 규칙 복제 | 규칙은 Spring `SessionService`에만 있고 MCP는 전달만 함. 단계 전환·순서·종료 규칙은 Spring이 재검증 | `BackendFlowTest.turnRulesAndTaskContract` |
| rag-mcp | 업무 데이터 변경 | 도구 3개 모두 조회. 저장소 쓰기 코드 없음 | `mcp_servers/rag/server.py` |

## 6. 두 경로

- **동기·업무 경로**(수백 ms): 로그인, 초대 조회, 세션·리포트 조회, 노트 저장 → Spring에서 끝난다.
- **비동기·AI 경로**(수 초~수십 초): TURN·START·REPORT → 202 → 큐 → Agent → 이벤트 → SSE.

## 7. 배포 (표 5-10, 5-11)

| 서비스 | 기술 | 포트 | 공개 | 먼저 실행 |
|---|---|---|---|---|
| frontend | Vue 3 + nginx | 80 → 호스트 18088 | 공개 | backend |
| backend | Spring Boot 3 | 8080 → 호스트 18080 (8081 내부 전용) | 공개 | postgres, rabbitmq |
| agent | FastAPI | 8000 | 내부 | postgres, rabbitmq, business-mcp, rag-mcp, detector-mcp |
| business-mcp / rag-mcp / detector-mcp | FastMCP 4.1 | 9101 / 9102 / 9103 | 내부 | backend / rag-indexer / 없음 |
| rag-indexer | 파이프라인(1회 실행) | — | 내부 | vectordb |
| postgres | PostgreSQL 16 | 5432 | 내부 | 없음 |
| vectordb | pgvector (pg16) | 5432 | 내부 | 없음 |
| rabbitmq | RabbitMQ 3.13 | 5672 | 내부 | 없음 |

## 8. 도메인 설계 요약
세션은 소통 → 조율 → 타협 → 설득 네 단계로 진행되고, 타협 단계의 선택지·상대 페르소나의 갈등 유형·가치 축은 [docs/criteria](../criteria/)에 근거와 함께 있다. 지원자 화면에는 숨겨진 축·상황·페르소나 입장이 내려가지 않고(`views.candidate_view`), 관리자 화면에만 근거가 나간다.

- **지원자 계정**: 초대 토큰으로 가입 → `PENDING_REVIEW` → ACCOUNT_REVIEW 그래프(스키마 → 정상성 → 결정). 분명한 경우만 Agent가 결정하고(`auto_clean`/`auto_schema`), 나머지는 관리자 승인 뒤 같은 thread로 재개 (`account_review.py`, `AccountService`).
- **같이 보는 과제**: START에서 Agent가 시나리오별 과제 3개(설계·결과·코드)를 시드한다(`artifacts.catalog`). 과제마다 일부러 심은 문제(체크포인트)는 Agent에만 있고,
  관리자 뷰가 지원자 마크업과 줄 범위(±1)로 맞춰 `artifact_checks`(발견/놓침)를 계산한다. 페르소나는 `open_shared_artifact`로 과제를 열어 마크업에 답한다.
- **대화 장부**: 턴마다 쟁점·약속·입장·요약을 갱신해 Spring `sessions.dialogue_json`에 저장하고 다음 턴의 컨텍스트로 쓴다. 관리자 상세에만 보인다. `DIALOGUE_HARNESS=0`이면 이전 흐름 ([harness.md](harness.md)).
- **렌더링**: 페르소나 발화와 과제 본문은 Markdown·LaTeX 원문으로 저장하고, 화면에서 markdown-it + KaTeX + DOMPurify로 그린다.

관련 문서: [harness.md](harness.md) · [extending.md](extending.md) · [quality-attributes.md](quality-attributes.md) · [dialogue-harness.md](dialogue-harness.md) · [../rubric-mapping.md](../rubric-mapping.md)
