# 워커와 인프라

## report-worker (`services/report-worker/`)

리포트 생성은 작은 LangGraph 그래프다. thread `report:{session_id}`, PostgresSaver(워커는 이 thread만 접근).

```
collect → draft → [interrupt: approval] → finalize
```

1. `report.generate` 소비(prefetch 1, manual ack). 본문 `{session_id, attempt}`. 같은 session_id의 draft가 이미 있으면 ack만.
2. **collect**: 내부 API로 session, observations, assistant_calls, assistant_reuse, messages, document_revisions, doc_views.
3. **draft**: 선택 요소마다 섹션 조립(situation은 카탈로그, label→observed 문장 템플릿, evidence는 메시지 원문). label 없으면 observed=null과 안내 문구. AI 활용은 호출이 없으면 used=false, 있으면 LLM(temperature 0)이 위임·맥락·검증 요약 한 문단. 근거 id가 같은 세션 데이터인지 검증(아니면 제거). 금지어 검사 후 `POST /report/draft` → report_ready → **ack**.
4. **interrupt**: 체크포인트에 멈춤. 승인 전 final은 api가 409로 거부한다.
5. `report.approve` 소비 → 같은 thread_id로 `Command(resume=True)` → **finalize**: 승인한 draft와 동일한 내용(해시 비교)으로 `POST /report/final` → reviewed → ack. draft 체크포인트가 아직 없으면(경쟁) nack 없이 15초 뒤 재발행.
6. 실패·예외: attempt+1로 재발행(백오프 5·15·45초) 후 원본 ack. attempt≥3이면 `report.dlq`로 보내고 `report_failed`. api가 내려가 있으면 재발행이 큐에 남고 복구 후 처리된다. "3회"는 최초 포함 총 3회.

## RabbitMQ
- exchange `dayzero`(direct). 큐 `report.generate`, `report.approve`(둘 다 durable, DLX → `report.dlq`), `report.dlq`.
- 메시지 persistent. 관리 UI는 `127.0.0.1:15672`에만 바인딩.

## Docker Compose (`infra/docker-compose.yml`)
서비스: postgres, rabbitmq, api(8000 공개, 8001 내부), business-mcp, rag-mcp, report-worker, web(3000 공개). 앱 서비스는 `/health`(또는 MCP `/mcp` 응답)로 healthcheck하고 의존은 `service_healthy`. 공개 포트는 web·api 8000·rabbitmq 관리(로컬 바인딩)뿐.

## 환경변수
`OPENAI_API_KEY, OPENAI_MODEL=gpt-4o-mini, DATABASE_URL, RABBITMQ_URL, JWT_SECRET, INTERNAL_TOKEN, API_INTERNAL_URL=http://api:8001, BUSINESS_MCP_URL, RAG_MCP_URL, EMBEDDING_MODEL, SCENARIOS_DIR, ENABLE_TEST_API, LANGCHAIN_*, NEXT_PUBLIC_API_URL, NEXT_PUBLIC_WS_URL`

## 완료 기준
- 픽스처로 draft 생성 후 그래프가 멈춤 → approve 메시지로 같은 thread 재개 → final 저장(draft와 동일 해시), 중복 approve는 멱등
- 금지어·타 세션 근거 id 제거 테스트
- api를 내린 상태에서 발행 → 3회 재시도 후 DLQ, 복구 후 report_failed 반영
- `docker compose up`으로 전부 healthy
