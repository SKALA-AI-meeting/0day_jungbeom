# 설정과 실행 모드

env 이름과 기본값의 예시는 `infra/.env.example`, 코드의 기본값은 각 서비스 `config.py`가 정본이다. 이 문서는 실행 모드마다 무엇이 어디에 붙는지와 env가 어떤 순서로 읽히는지를 적는다.

## 실행 모드

| | 로컬 개발 | 전체 compose | 격리 e2e 스택 |
|---|---|---|---|
| 명령 | `make infra-up` + 앱 로컬 실행([quickstart.md](quickstart.md)) | `make up` / `make down` | `make e2e-stack-up` / `make e2e-stack-down` |
| compose 파일 | `docker-compose.yml` + `docker-compose.dev.yml` | `docker-compose.yml` | `docker-compose.yml` + `docker-compose.e2e.yml`, 프로젝트 `dayzero-debate` |
| 컨테이너 | postgres·rabbitmq·rag-mcp | 8개 전부 | 8개 전부 |
| env 파일 | 컨테이너 `infra/.env`, 로컬 앱 `infra/.env.local` → `infra/.env` | `infra/.env` | `infra/.env.e2e` |
| web | `localhost:3000`(`pnpm dev`) | `localhost:3000` | `localhost:3100` |
| api 공개 | `localhost:8000` | `localhost:8000`(`API_PORT`) | `localhost:8100` |
| api 내부(8001) | `localhost:8001`(로컬 프로세스) | 컨테이너 네트워크만 | `127.0.0.1:8101` |
| postgres(호스트) | `127.0.0.1:5432` | 열지 않음 | `127.0.0.1:5442` |
| rabbitmq | `127.0.0.1:5672`, 관리 UI `127.0.0.1:15672` | 관리 UI `127.0.0.1:15672`만 | 관리 UI `127.0.0.1:15674`만 |
| rag-mcp(호스트) | `127.0.0.1:9102` | 열지 않음 | `127.0.0.1:9112` |
| debate·assessment MCP | 로컬 9101·9103 | 컨테이너 네트워크만 | 컨테이너 네트워크만 |
| rag-mcp가 부르는 내부 API | `http://host.docker.internal:8001`(로컬 api) | `http://api:8001` | `http://api:8001` |
| 시드 | `make seed` | 호스트에서 닿는 경로 없음(아래) | `make e2e-stack-seed` |
| 테스트 API | `ENABLE_TEST_API=1`이면 `localhost:8001/internal/test/*` | 컨테이너 안에서만 | `127.0.0.1:8101/internal/test/*` |

- **같은 DB·큐를 쓰는 api는 하나만 띄운다.** 세션 메일박스·WS 송신 큐·스케줄러가 api 프로세스 메모리에 있어 둘이면 같은 세션을 두 번 처리한다. 다른 DB·큐를 쓰는 격리 스택(위 e2e 스택)은 함께 띄워도 된다.
- 로컬 개발 모드와 전체 compose는 호스트 포트 3000·8000을 함께 쓰므로 동시에 띄우지 않는다. 같은 기계에서 두 번째 스택이 필요하면 격리 e2e 스택을 쓰거나 `API_PORT`·`WEB_PORT`·`RABBITMQ_UI_PORT`와 프로젝트 이름(`-p`)을 바꾼다.
- 전체 compose 모드는 postgres·rag-mcp를 호스트에 열지 않아 `scripts/seed.py`가 자료 원문 시드와 재색인을 할 수 없다. 자료가 필요한 확인은 로컬 개발 모드나 격리 e2e 스택에서 한다.

## env를 읽는 순서

| 대상 | 순서(앞이 이김) |
|---|---|
| compose 컨테이너 | `docker-compose*.yml`의 `environment:`(서비스 주소) > `env_file`(`infra/.env` 또는 `infra/.env.e2e`) |
| 로컬 Python 서비스(api·MCP 3개·report-worker) | 이미 설정된 프로세스 env > `infra/.env.local` > `infra/.env`(`python-dotenv`, 덮어쓰지 않음) |
| 로컬 web(`pnpm dev`) | 프로세스 env와 `apps/web/.env*`(Next.js 규칙). `infra/.env`는 읽지 않는다 |
| web 컨테이너 | `NEXT_PUBLIC_*`는 **이미지 빌드 시점**의 build arg(`apps/web/Dockerfile`). 컨테이너 env를 바꿔도 번들은 바뀌지 않으므로 다시 빌드한다. 값이 없으면 `http://localhost:8000`·`ws://localhost:8000` |
| `scripts/seed.py` | `--database-url`(기본 env `SEED_DATABASE_URL`, 없으면 `localhost:5432`), `--api`(기본 8000), `--rag`(기본 9102) |
| api DB 테스트 | `TEST_DATABASE_URL`(기본 `localhost:5432`). 없거나 닿지 않으면 skip |

## env 목록

| 이름 | 읽는 곳 | 뜻·기본값 |
|---|---|---|
| `OPENAI_API_KEY`, `OPENAI_API_KEY_PERSONAL`, `GEMINI_API_KEY` | api·report-worker LLM 래퍼 | 모델 id로 키를 고른다(gpt-4o-mini → `OPENAI_API_KEY`, 그 밖 gpt-* → 개인 키, gemini-* → Gemini 키). 비어 있으면 설정 오류 |
| `OPENAI_MODEL` | 같음 | 역할 env가 비었을 때의 모델, 기본 `gpt-4o-mini` |
| `MODEL_INTENT`·`MODEL_TURN`·`MODEL_PERSONA`·`MODEL_ASSISTANT`·`MODEL_EVALUATOR` | 같음 | 역할별 모델. 타임아웃·재시도는 [architecture/harness.md](../architecture/harness.md) "역할별 모델" |
| `DATABASE_URL`, `RABBITMQ_URL` | api·rag-mcp·report-worker | DB·큐 주소 |
| `JWT_SECRET`, `INTERNAL_TOKEN`, `ASSESSMENT_MCP_TOKEN` | api·MCP·report-worker | 서명 키와 내부 토큰. `ASSESSMENT_MCP_TOKEN`은 api 결정적 노드·report-worker·assessment-mcp에만 |
| `API_INTERNAL_URL` | MCP 3개·report-worker | 내부 API, compose 기본 `http://api:8001` |
| `DEBATE_MCP_URL`·`RAG_MCP_URL`·`ASSESSMENT_MCP_URL` | api(report-worker는 assessment만) | MCP 주소(`/mcp`까지) |
| `EMBEDDING_MODEL`, `HF_HOME` | rag-mcp | `BAAI/bge-m3`, 모델 캐시 위치(compose 볼륨 `hfcache`) |
| `SCENARIOS_DIR` | api·rag-mcp·report-worker | 카탈로그 위치(compose `/scenarios`). 기본값이 없으면 저장소 `scenarios/`, 지정한 경로가 없으면 설정 오류 |
| `ENABLE_TEST_API` | api | `1`이면 `/internal/test/*`(단계 시드·시간 당기기). 운영은 비운다 |
| `LLM_FAKE` | api·report-worker | `1`이면 LLM 호출만 결정적 고정 응답 |
| `LLM_FAULT` | api·report-worker | `<role>:timeout:<N>` 장애 주입(e2e 전용) |
| `AGENT_RUNNER` | api | `session`(기본, 토론 그래프) ∣ `fake`(단위 테스트 주입용) |
| `SESSION_COST_HARD_USD` | api | 토론 비용 하드 상한, 기본 `2`(`.env.example`에 없음) |
| `CONTACT_EMAIL` | api | 입장·디브리핑 문의 창구, 기본 `recruit@example.com`(`.env.example`에 없음) |
| `WEB_ORIGIN`, `WEB_BASE_URL` | api | CORS 허용 origin(쉼표 구분), 초대 링크의 웹 주소 |
| `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT` | api·report-worker | LangSmith trace |
| `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL`, `NEXT_PUBLIC_MOCK` | web(빌드 시점) | api·WS 주소, `1`이면 mock 모드 |
| `API_PORT`, `WEB_PORT`, `RABBITMQ_UI_PORT` | compose | 공개 포트 번호 |
| `SEED_DATABASE_URL`, `TEST_DATABASE_URL` | `scripts/seed.py`, api 테스트 | 위 "env를 읽는 순서" |
| `WEB_URL`, `E2E_INTERNAL_URL`, `E2E_DATABASE_URL`, `E2E_RESTART_CMD` | Playwright·e2e 러너 | 대상 스택 주소, `restart` 대본의 재시작 명령 |
| `PLAYTEST_PORT` | playtest 드라이버 | 드라이버 서버 포트, 기본 9400 |

`.env.example`에 없는 키를 코드에 더하면 `.env.example`과 이 표를 함께 고친다.
