# 설계 결정 기록

| 날짜 | 결정 | 이유 | 대안 |
|---|---|---|---|
| 2026-10-20 | Recovery: LLM 호출 실패 시 2회 재시도 후 규칙 기반 폴백(고정 문장 "잠시만요"로 응답, 체크포인트에서 재개). 대체 모델은 두지 않음 | PRD 제약상 gpt-4o-mini만 사용 가능. 하네스 Recovery 요소를 PRD 변경 없이 충족 | 같은 모델 다른 설정을 대체 모델로 등록, 팀에 로컬 모델 허용 제안 |
| 2026-10-20 | 기술 스택은 PRD 부록 A.1 그대로: Next.js, FastAPI gateway, LangGraph agent, gpt-4o-mini, BGE-M3 로컬 임베딩, WebSocket, PostgreSQL+pgvector, Streamable HTTP MCP 2개(:9101, :9102), RabbitMQ, 자체 JWT, LangSmith, Docker Compose | 평가 요소(큐, MCP 2개, 관측, 인증)를 빠짐없이 자연스럽게 덮음 | 임베딩을 OpenAI로, 프론트를 Vite SPA로 가볍게 |
