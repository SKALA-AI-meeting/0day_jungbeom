# 시스템 아키텍처 (캡스톤 레퍼런스 아키텍처 적용)

## 1. 요구사항 → 아키텍처 결정

| 요구사항 | 결정 | 코드 |
|---|---|---|
| LLM 응답은 수 초~수십 초 | 질문은 **작업으로 접수해 202**를 바로 돌려주고, 진행은 **SSE 이벤트**로 보낸다 | `POST /api/ai/tasks`, `Controllers.Tasks`, `SseHub` |
| 업무 규칙은 한 곳에서 | business-mcp는 DB에 직접 접근하지 않고 Spring `/internal/**`만 호출 | `SessionService`, `mcp_servers/business/server.py` |
| 브라우저에 노출되는 주소 최소화 | 공개 포트는 frontend·backend뿐, 나머지는 docker network 안 | `docker-compose.yml`, `AuthFilters.PortGuard` |
| 데이터를 바꾸는 도구는 사람이 확인 | 변경 도구 앞에서 Agent가 상태를 저장하고 멈춘 뒤, 승인받으면 **같은 thread id로 재개** | `report_graph.py`(interrupt), `TaskService.approve` |
| 답변에는 근거 문서가 있어야 | 문서는 미리 색인하고 rag-mcp가 Vector DB에서 근거를 찾는다 | `rag_pipeline/`, `mcp_servers/rag/` |

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
| 7 | Agent → Spring → Vue | 진행 이벤트 `TOKEN · TOOL_START · TOOL_END · APPROVAL_REQUIRED · DONE · FAILED` 를 SSE로 중계 | HTTP / SSE |

## 4. API 계약 (표 5-8, 5-9)

| Method | Path | 설명 | 응답 |
|---|---|---|---|
| POST | `/api/ai/tasks` | 작업 생성 (`type`: TURN · REPORT) | 202 taskId |
| GET | `/api/ai/tasks/{id}` | 상태·결과·trace 조회 | status, result, trace[] |
| GET | `/api/ai/tasks/{id}/stream` | 진행 이벤트 | text/event-stream |
| POST | `/api/ai/tasks/{id}/approval` | 승인·반려 (같은 thread id로 재개) | 202 |
| GET | `/api/ai/tasks?mine=true` | 내 작업 이력 (관리자는 회사 전체) | 목록 |

그 밖의 공개 API: `/api/auth/{signup,login,me}`, `/api/meta`, `/api/scenarios/{id}`, `/api/invites/{token}`(조회·세션 시작), `/api/sessions/{id}`(조회·노트·종료), `/api/admin/{sessions,invites}`.
Vue는 AI 서버 주소를 모른다. 작업 상태는 `QUEUED → RUNNING → (WAITING_APPROVAL →) DONE | FAILED | REJECTED`.

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
