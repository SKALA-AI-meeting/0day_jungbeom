# 워커와 인프라

## report-worker (`services/report-worker/`)

리포트 생성은 작은 LangGraph 그래프다. thread_id = `report:{session_id}`, PostgresSaver 체크포인터.

```
collect → draft → [interrupt: approval] → finalize
```

1. `report.generate` 큐 소비(prefetch 1). 메시지 `{session_id, attempt}`.
2. **collect**: api 내부 API로 session, observations, assistant_calls, messages를 읽는다.
3. **draft**: 선택 요소마다 섹션 조립(카탈로그의 situation 문장, label→observed 문장 템플릿, evidence는 메시지 원문 인용, label 없으면 observed=null과 안내 문구). AI 활용은 assistant_calls가 없으면 used=false, 있으면 LLM(temperature 0)이 위임·맥락·검증 관점 요약 한 문단. 금지어 검사(점수·합격·불합격·순위·등급 패턴) 후 `POST /internal/sessions/{id}/report/draft` → 상태 `report_ready`.
4. **interrupt**: 그래프가 체크포인트에 멈춘다. 관리자가 리포트 화면에서 draft를 읽고 "검토 완료"를 누르면 api가 `report.approve` 큐에 `{session_id}`를 발행.
5. 워커가 `report.approve`를 소비해 같은 thread_id로 `Command(resume=True)` 재개 → **finalize**: draft를 최종본으로 확정(generated_at·reviewed_at 기록) `POST /internal/sessions/{id}/report/final` → 상태 `reviewed`.
6. 실패나 예외는 nack → 재큐(attempt+1, 백오프 5·15·45초). attempt≥3이면 `report.dlq`로 보내고 `report_failed` 호출. approve 메시지도 같은 재시도 규칙.

## RabbitMQ
- exchange `dayzero`, 큐 `report.generate`, `report.approve`(둘 다 DLX → `report.dlq`), `report.dlq`.
- 관리 UI 15672 노출(로컬).

## Docker Compose (`infra/docker-compose.yml`)
서비스: postgres(pgvector 이미지), rabbitmq(management), api, business-mcp, rag-mcp, report-worker, web. 헬스체크 후 의존 순서로 기동. `.env`는 `infra/.env.example` 복사.

## 환경변수
`OPENAI_API_KEY, OPENAI_MODEL=gpt-4o-mini, DATABASE_URL, RABBITMQ_URL, JWT_SECRET, INTERNAL_TOKEN, BUSINESS_MCP_URL, RAG_MCP_URL, LANGCHAIN_TRACING_V2, LANGCHAIN_API_KEY, LANGCHAIN_PROJECT, ENABLE_TEST_API, NEXT_PUBLIC_API_URL, NEXT_PUBLIC_WS_URL`

## 완료 기준
- 픽스처 observations로 draft 생성 후 그래프가 멈춤, approve 메시지로 재개되어 final 저장(같은 thread_id 확인), 금지어 테스트
- api를 내린 상태에서 발행 → 3회 재시도 후 DLQ에 메시지, api 복구 후 report_failed 반영 확인
- `docker compose up`으로 전부 healthy
