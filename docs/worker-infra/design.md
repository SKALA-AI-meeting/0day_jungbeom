# 워커와 인프라

## report-worker (`services/report-worker/`)

리포트 생성은 작은 LangGraph 그래프다. thread `report:{session_id}`, PostgresSaver(워커는 이 thread만 접근).

```
collect → draft → approval[interrupt] → finalize   (draft 생성 노드와 interrupt 노드를 분리: 재개 시 approval 노드만 다시 실행되고 draft 생성은 반복되지 않음)
```

1. `report.generate` 소비(prefetch 1, manual ack). 본문 `{session_id, attempt}`. 처리 전에 thread `report:{session_id}`의 상태를 조회한다. 이미 interrupt에 멈춰 있으면 collect·draft를 건너뛰고 4단계(draft 저장)부터, final까지 끝났으면 ack만.
2. **collect**: 내부 API로 session, observations, assistant_calls, assistant_reuse, messages, document_revisions, doc_views.
3. **draft**: 선택 요소마다 섹션 조립(situation은 카탈로그, label→observed 문장 템플릿, evidence는 메시지 원문). label 없으면 observed=null과 안내 문구. AI 활용은 호출이 없으면 used=false, 있으면 LLM(temperature 0)이 위임·맥락·검증 요약 한 문단. 근거 id가 같은 세션 데이터인지 검증(아니면 제거). 금지어 검사 후 draft를 state에 담는다. 이어서 **approval** 노드가 `interrupt(draft)`로 멈춘다(이 시점에 체크포인트가 먼저 저장된다). 노드를 나눈 이유: LangGraph는 재개 시 interrupt가 있던 노드를 처음부터 다시 실행하므로, 같은 노드에 두면 LLM 요약이 재실행된다.
4. 그래프가 멈춘 뒤 워커가 state의 draft로 `POST /report/draft`(멱등) → report_ready → **ack**. 순서가 체크포인트 → draft 저장 → ack이므로 ACK 뒤에 승인이 와도 재개 대상이 항상 있다. draft 저장 전에 죽으면 재전달이 1단계의 상태 조회로 여기부터 다시 한다. 승인 전 final은 api가 409로 거부한다.
5. `report.approve` 소비 → 같은 thread_id로 `Command(resume=True)` → **finalize**: 승인한 draft와 동일한 내용(해시 비교)으로 `POST /report/final` → reviewed → ack. thread에 멈춘 체크포인트가 없으면(generate가 아직 처리 전) nack 없이 15초 뒤 재발행.
6. 실패·예외: attempt+1로 재발행(백오프 5·15·45초) 후 원본 ack. attempt≥3이면 `report.dlq`로 보낸다. "3회"는 최초 포함 총 3회.
7. `report.dlq` 소비(같은 워커의 두 번째 소비자): `POST /report_failed` 호출 후 ack. api가 내려가 있으면 ack하지 않고 60초 뒤 재시도하므로 복구 후 세션이 failed로 반영된다.

## RabbitMQ
- exchange `dayzero`(direct). 큐 `report.generate`, `report.approve`(둘 다 durable, DLX → `report.dlq`), `report.dlq`.
- 메시지 persistent. 관리 UI는 `127.0.0.1:15672`에만 바인딩.

## Docker Compose (`infra/docker-compose.yml`)
서비스: postgres, rabbitmq, api(8000 공개, 8001 내부), business-mcp, rag-mcp, report-worker, web(3000 공개). healthcheck: api·MCP는 `/health`, web은 `/api/health` 라우트, report-worker는 30초마다 갱신하는 `/tmp/heartbeat` 파일(90초 이상 오래되면 unhealthy). 의존은 `service_healthy`. 공개 포트는 web·api 8000·rabbitmq 관리(로컬 바인딩)뿐.

## 환경변수
`OPENAI_API_KEY, OPENAI_MODEL=gpt-4o-mini, DATABASE_URL, RABBITMQ_URL, JWT_SECRET, INTERNAL_TOKEN, API_INTERNAL_URL=http://api:8001, BUSINESS_MCP_URL, RAG_MCP_URL, EMBEDDING_MODEL, SCENARIOS_DIR, ENABLE_TEST_API, LANGCHAIN_*, NEXT_PUBLIC_API_URL, NEXT_PUBLIC_WS_URL`

## 완료 기준
- 픽스처로 draft 생성 후 그래프가 멈춤 → approve 메시지로 같은 thread 재개 → final 저장(draft와 동일 해시), 중복 approve는 멱등
- 금지어·타 세션 근거 id 제거 테스트
- api를 내린 상태에서 발행 → 3회 재시도 후 DLQ, 복구 후 report_failed 반영
- `docker compose up`으로 전부 healthy
