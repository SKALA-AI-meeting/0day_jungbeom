# 배포 (Docker Compose)

## 서비스와 의존

서비스: postgres, rabbitmq, api(8000 공개, 8001 내부), debate-mcp(9101), rag-mcp(9102), assessment-mcp(9103), report-worker, web(3000 공개).

- healthcheck: api·MCP 3개는 `/health`, web은 `/api/health`, report-worker는 30초마다 갱신하는 `/tmp/heartbeat`(90초 이상 오래되면 unhealthy).
- 의존(`service_healthy`): api ← postgres·rabbitmq·debate-mcp·rag-mcp·assessment-mcp. report-worker ← postgres·rabbitmq·api·assessment-mcp. rag-mcp ← postgres. web ← api.
- 공개 포트는 web 3000·api 8000·rabbitmq 관리(로컬 바인딩)뿐. MCP 3개는 `expose`만.
- `../scenarios`를 api·rag-mcp에 읽기 전용 마운트(카탈로그·자료·아바타 에셋).
- `docker-compose.dev.yml`(로컬 개발): postgres·rabbitmq·rag-mcp만 docker, 나머지는 로컬 hot reload. debate-mcp·assessment-mcp는 가벼우니 로컬 실행.

## 환경변수 (`infra/.env.example`)

## RabbitMQ

- exchange `dayzero`(direct). 큐 `report.generate`, `report.approve`(durable, DLX → `report.dlq`), `report.dlq`. 본문은 계약 "큐 메시지" 표.
- persistent, publisher confirm 뒤 api가 `*_enqueued_at` 기록, manual ack, 같은 session_id 중복은 stage로 멱등. 미발행은 api 스케줄러가 60초마다 재발행.
- 관리 UI는 `127.0.0.1:15672`에만 바인딩.
