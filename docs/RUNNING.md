# Day Zero 실행 가이드

캡스톤 레퍼런스 아키텍처(Vue 3 → Spring Boot 3 → FastAPI Agent → MCP Server → PostgreSQL / pgvector)를 docker compose로 띄웁니다.

## 1. 한 번에 띄우기

```bash
# 루트 .env 에 OPENAI_API_KEY (필수), GOOGLE_API_KEY (디텍터 모델 판정, 없으면 규칙만) 를 둡니다.
docker compose -p d20 up -d --build
```

| 접속 | 주소 | 비고 |
|---|---|---|
| 화면 | http://localhost:18088 | 지원자: `/join/<token>`(데모 초대 `demo`)에서 가입 → `/me`, 관리자: `/admin`(로그인 후 `/admin/inbox`) |
| Spring Boot API | http://localhost:18080 | 공개 포트는 이 둘뿐 (`FRONTEND_PORT`, `BACKEND_PORT` 로 변경) |

내부 서비스(agent :8000, business-mcp :9101, rag-mcp :9102, detector-mcp :9103, postgres, vectordb, rabbitmq)와 Spring의 `/internal/**`(:8081)는 docker network 안에서만 열립니다.

데모 계정(테스트용, `SEED_DEMO=true`): 관리자 `demo@dayzero.dev` / `dayzero-demo-pass`, 재사용 초대 토큰 `demo`.

### 주요 환경 변수

| 변수 | 기본 | 뜻 |
|---|---|---|
| `DISPATCH` (backend) | compose `rabbit`, 로컬 `http` | 작업 전달 방식: `rabbit`(큐·재시도·DLQ), `http`(POST /agent/tasks), `none`(테스트) |
| `TASK_STALE_MINUTES` / `TASK_WATCHDOG_INTERVAL_MS` (backend) | 10 / 60000 | watchdog: 진행 없는 QUEUED·RUNNING 작업을 FAILED로 닫는 기준·주기 (`WAITING_APPROVAL`은 제외) |
| `DIALOGUE_HARNESS` (agent) | 1 | 대화 하네스(장부·화자 규칙·반복 가드). `0`이면 이전 대화 흐름(전후 비교용) |
| `LLM_MODEL` / `LLM_FALLBACK_MODEL` (agent) | gpt-4o-mini / gpt-4.1-mini | 기본 모델과 장애 시 대체 모델 |

## 1-1. 화면 흐름

1. **지원자 가입**: `/join/demo` → 이메일·비밀번호·닉네임·희망 직무·경력·동의 → 계정은 `PENDING_REVIEW`, Agent가 심사(`ACCOUNT_REVIEW`).
   분명하면 Agent가 바로 승인·거절하고, 애매하면 관리자 체크리스트로 올라갑니다. 지원자는 `/me/review`에서 단계만 봅니다.
2. **평가**: `/me/start`에서 시나리오 선택 → `/s/{id}` 팀 채널. 오른쪽 "같이 확인할 과제"(설계·결과·코드)를 열어 줄이나 문장을 골라
   질문·우려·제안·확인함 마크업을 남기고, "대화에 인용"으로 `[과제 제목 L12-15]`를 채팅에 넣을 수 있습니다. 첫 메시지가 실패하면 "다시 시작하기".
3. **관리자**: 로그인 → `/admin/inbox`(계정 승인, 리포트 공개 승인, 검토 오류, 리포트 생성 실패) → 결정하면 `/admin/working`에서 반영을 지켜본 뒤 `/admin`.
   세션 상세에는 과제·마크업, 심어 둔 확인 지점(발견/놓침), 대화 장부(쟁점·약속·입장)가 읽기 전용으로 보입니다.

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
scripts/e2e.py            compose 위에서 가입·심사 → 대화·마크업 → 리포트 승인까지 한 번에 확인
scripts/dialogue_eval.py  대화 하네스 전후 비교 (실제 모델, docs/eval/)
```

## 3. 테스트

```bash
cd backend && ./gradlew test                      # Spring 통합 테스트 17개 (H2: 보안, 작업 계약·레지스트리, 승인, 계정 심사, 과제·마크업, 장부, watchdog)
cd agent && uv run --python 3.12 pytest -q        # Agent 53개 (Harness, 러너, MCP 연동, 승인 interrupt/재개, 과제 카탈로그, 대화 하네스)
cd frontend && npx vite build                     # 프론트엔드 빌드
cd agent && uv run --python 3.12 python ../scripts/e2e.py http://localhost:18080   # 실제 LLM 종단 간 (몇 분)
```

## 4. 로컬 개발(Docker 없이)

Spring `DISPATCH=http`, Agent는 `uvicorn app.agent_api:app --port 8000`, MCP 서버는 각각 `python -m mcp_servers.<name>.server`.
`DATABASE_URL` 이 없으면 checkpointer는 메모리, `VECTOR_DB_URL` 이 없으면 RAG 색인은 로컬 JSON(`EMBEDDING_PROVIDER=local` 이면 키 없이도 동작)입니다.
