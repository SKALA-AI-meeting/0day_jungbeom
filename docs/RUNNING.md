# Day Zero 실행 가이드

캡스톤 레퍼런스 아키텍처(Vue 3 → Spring Boot 3 → FastAPI Agent → MCP Server → PostgreSQL / pgvector)를 docker compose로 띄웁니다.

## 1. 한 번에 띄우기

```bash
# 루트 .env 에 OPENAI_API_KEY (필수), GOOGLE_API_KEY (디텍터 모델 판정, 없으면 규칙만) 를 둡니다.
docker compose -p d20 up -d --build
```

| 접속 | 주소 | 비고 |
|---|---|---|
| 화면 | http://localhost:18088 | 지원자: `/` (데모 초대) 또는 `/i/<token>`, 관리자: `/admin` |
| Spring Boot API | http://localhost:18080 | 공개 포트는 이 둘뿐 (`FRONTEND_PORT`, `BACKEND_PORT` 로 변경) |

내부 서비스(agent :8000, business-mcp :9101, rag-mcp :9102, detector-mcp :9103, postgres, vectordb, rabbitmq)와 Spring의 `/internal/**`(:8081)는 docker network 안에서만 열립니다.

데모 계정(테스트용, `SEED_DEMO=true`): 관리자 `demo@dayzero.dev` / `dayzero-demo-pass`, 재사용 초대 토큰 `demo`.

## 2. 구성

```
frontend/   Vue 3 (Vite, nginx)        화면. Spring 만 호출 (/api/**), SSE 수신
backend/    Spring Boot 3 (Java 21)    업무 API, 작업 접수(202)·상태 저장, SSE 중계, JWT 인증, /internal/**
agent/      FastAPI + LangGraph        Agent 서버 (Harness), MCP 서버 3개, RAG 색인 파이프라인
  app/harness/            Harness 8요소
  app/prompts/*.md        버전 관리되는 프롬프트
  mcp_servers/business    Spring /internal/** 을 호출하는 업무 도구 (DB 직접 접근 없음)
  mcp_servers/rag         pgvector 검색, 출처 반환 (읽기 전용)
  mcp_servers/detector    외부 디텍터 (규칙 + Gemini)
  rag_pipeline/           Documents → Chunking → Embedding → Indexing → Vector DB (오프라인)
analysis/   공개 설문 데이터 분석 (가치 축 선정)  → docs/criteria/
scripts/e2e.py            compose 위에서 초대→대화→리포트 승인까지 한 번에 확인
```

## 3. 테스트

```bash
cd backend && ./gradlew test                      # Spring 통합 테스트 6개 (H2, 보안·작업 계약·승인·초대)
cd agent && uv run --python 3.12 pytest -q        # Agent 17개 (Harness, 러너, MCP 연동, 승인 interrupt/재개)
cd agent && uv run --python 3.12 python ../scripts/e2e.py http://localhost:18080   # 실제 LLM 종단 간
```

## 4. 로컬 개발(Docker 없이)

Spring `DISPATCH=http`, Agent는 `uvicorn app.agent_api:app --port 8000`, MCP 서버는 각각 `python -m mcp_servers.<name>.server`.
`DATABASE_URL` 이 없으면 checkpointer는 메모리, `VECTOR_DB_URL` 이 없으면 RAG 색인은 로컬 JSON(`EMBEDDING_PROVIDER=local` 이면 키 없이도 동작)입니다.
