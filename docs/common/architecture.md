# 아키텍처

MVP 원칙: **평가 항목이 요구하는 조각만 분리하고 나머지는 합친다.** 분리하는 것은 MCP 서버 2개, 큐와 워커, 프론트뿐이다. 에이전트는 api 프로세스 안의 모듈이다.

## 구성 요소

| 구성 요소 | 책임 | 기술 |
|---|---|---|
| web | 기업 관리자 화면, 지원자 가상 오피스 | Next.js App Router, Tailwind. `/admin/*`, `/s/[token]` |
| api | 인증, 화면 API, WebSocket, DB 쓰기, 세션 시계·이벤트 스케줄러, LangGraph 에이전트 모듈(동료·팀장·어시스턴트·관찰) | FastAPI + LangGraph, 한 프로세스 |
| business-mcp | 세션·메시지·보드·문서·관찰의 조회·변경 도구. api 내부 엔드포인트 호출 | FastMCP, Streamable HTTP `:9101/mcp` |
| rag-mcp | 회사 문서 검색·조회·색인 | FastMCP, Streamable HTTP `:9102/mcp`, BGE-M3, pgvector |
| report-worker | 세션 종료 후 리포트 생성, 재시도, DLQ | Python, RabbitMQ consumer |
| infra | 컨테이너, 큐, DB, 관측 | Docker Compose, RabbitMQ, PostgreSQL 16 + pgvector, LangSmith(env) |

## 원칙

1. **DB 쓰기는 api만 한다.** MCP와 워커는 api의 `/internal/*`을 부른다. 예외는 LangGraph checkpointer 테이블(api 안의 에이전트 모듈이 직접)과 rag-mcp의 `doc_chunks`.
2. **시간의 주인은 api다.** 세션 시작·종료 시각과 이벤트 예정 시각을 DB에 두고, 5초마다 도는 스케줄러가 때가 된 이벤트를 집어 그래프를 호출한다. 프로세스가 재시작돼도 예약은 남는다.
3. **에이전트는 자극에 반응하는 함수다.** 자극은 지원자 메시지, 이벤트 도래, 세션 종료 세 가지. 자극마다 그래프를 한 번 실행하고 체크포인트에 남긴다. 세션 하나 = thread 하나.
4. **시나리오는 데이터다.** `positions.scenario` JSON이 카드 목록과 시점을 담고 코드는 해석만 한다.

## 요청 흐름

### 지원자 메시지
1. web → api WS `message.send`
2. api: 민감정보 마스킹 → 저장 → 세션 소켓에 `message.new` 브로드캐스트 → `agent.run(session_id, stimulus=message)`
3. 그래프: `agent.progress` 이벤트를 WS로 중계하며 실행. 회사 질문이면 rag-mcp 검색. 응답은 business-mcp `post_message`
4. business-mcp → api `POST /internal/messages` → 저장 → 브로드캐스트

### 이벤트 도래
1. 스케줄러가 `session_events`에서 `due_at <= now AND fired_at IS NULL`을 집어 `fired_at`을 찍고 `agent.run(stimulus=event)`
2. `observe`가 직전 창을 닫고 `record_observation`, `inject`가 카드를 실행. 시스템 카드는 LLM 없이 고정 문장과 `release_document` 예약

### 세션 종료
1. 제출 또는 `ends_at` 도달 → `status=completed` → `agent.run(stimulus=end)`로 마지막 창 정리와 팀장 응답
2. api가 RabbitMQ `report.generate`에 `{session_id}` 발행
3. report-worker → `POST /internal/reports` → `status=report_ready`. 3회 실패 시 `report.dlq`, `status=failed`

## 저장소 구조

```
apps/web/                 Next.js
services/api/             FastAPI + LangGraph (app/routers, app/agent, app/scheduler.py)
services/business-mcp/
services/rag-mcp/
services/report-worker/
scenarios/                catalog.yaml, documents/, e2e/ 대본
scripts/                  seed.py, make_session.py, worktree.sh
tests/e2e/                run.py, records/
infra/                    docker-compose.yml, .env.example, db/schema.sql
docs/
```

## ISO/IEC 25010 대응

| 품질 특성 | 설계 반영 |
|---|---|
| 기능 적합성 | PRD 기능 ID(F-xx)별 완료 조건을 e2e 단언으로 검증 |
| 신뢰성 | 체크포인트 재개, 이벤트 예약이 DB에 있어 재시작에도 유지, 리포트 큐 재시도·DLQ, LLM 폴백 |
| 성능 효율성 | 응답당 도구 호출 3회, 토큰 예산, 검색 결과 3청크 제한 |
| 보안성 | 역할 분리 JWT, 모든 조회에 company_id, 초대 토큰 1회성·72시간, 내부 API 시크릿, 비밀값 env |
| 유지보수성 | 시나리오 데이터화, 서비스별 컨테이너, 계약 문서가 정본 |
| 이식성 | Docker Compose 한 번에 기동. 외부 의존은 OpenAI·LangSmith뿐 |
| 호환성 | MCP 표준 전송, REST·WebSocket 계약 문서화 |
| 사용성 | 남은 시간 상시 표시, 새로고침 없는 도착, 진행 표시, 이어하기 |
