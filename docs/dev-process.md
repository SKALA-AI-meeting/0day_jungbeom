# 개발 프로세스와 환경

## 도구

| 영역 | 선택 | 명령 |
|---|---|---|
| Python | 3.12, `uv`로 가상환경·lockfile. 서비스마다 `pyproject.toml` | `uv sync`, `uv run pytest` |
| 린트·포맷 | ruff (lint + format), 설정은 저장소 루트 `ruff.toml` 하나 | `uv run ruff check . && uv run ruff format --check .` |
| Node | 22, pnpm. `apps/web` | `pnpm install`, `pnpm dev`, `pnpm test` |
| 프론트 린트 | Next 기본 eslint + prettier | `pnpm lint` |
| 테스트 | pytest(+ pytest-asyncio), vitest. 연결·e2e는 `tests/` | 서비스 폴더에서 `make test` |
| 인프라 | Docker Compose. 개발 중에는 **인프라만** docker, 앱은 로컬 | `make infra-up`, `make infra-down` |
| Makefile | 루트 `Makefile`에 공통 타깃: `infra-up`, `infra-down`, `seed`, `test`, `lint`, `e2e`. 검사는 실패 코드를 그대로 돌려주고, 아직 없는 서비스 폴더만 건너뛴다 | |
| seed | 루트 `scripts/seed.py`(httpx만 사용, 관리자 가입·채용 건 생성·rag 재색인 호출). foundation 소유 | `make seed` |

## 로컬 실행 (개발 중)

```
make infra-up           # postgres(5432), rabbitmq(5672), rag-mcp(9102)를 127.0.0.1에 공개 (compose + compose.dev.yml)
cd services/api && uv run python -m app.run --reload      # 한 프로세스에서 공개 8000 + 내부 8001 두 리스너
cd services/business-mcp && uv run python -m business_mcp # 9101
cd services/report-worker && uv run python -m report_worker
cd apps/web && pnpm dev                                   # 3000
```

- `infra/docker-compose.dev.yml`(override)이 인프라 포트를 로컬에 바인딩하고, 컨테이너 안의 rag-mcp가 호스트의 api 내부 포트를 보도록 `API_INTERNAL_URL=http://host.docker.internal:8001`을 준다.
- `infra/.env`를 각 서비스가 `python-dotenv`로 읽는다. 로컬에서는 호스트명을 `localhost`로 바꾼 `infra/.env.local`을 우선 읽는다(둘 다 git 무시).
- `app.run`은 uvicorn `Server` 두 개를 같은 asyncio 루프에서 띄운다. hub·세션 Lock·스케줄러가 한 프로세스에 있어야 하므로 두 앱을 별도 프로세스로 띄우지 않는다. foundation 산출물.
- **실행 중인 통합 스택은 한 번에 하나**다. 트랙 pane은 단위 테스트(mock)로 개발하고, 실제 스택이 필요하면 공용 인프라(`make infra-up`은 main 저장소에서 한 번)에 자기 worktree의 앱을 붙인다. api를 두 개 띄우면 스케줄러와 Lock 전제가 깨지므로 금지. 포트 오프셋은 두지 않는다.
- 전체 compose 기동은 M0.5 완료 기준과 M3 통합에서만 한다.

## TDD 방식

- 테스트를 먼저 쓰되 **happy path 중심**이다. 각 기능의 정상 경로 1개와 계약·평가 항목이 요구하는 실패 경로(권한 403, 공개 전 423/not_released, 승인 전 409, 재시도·DLQ, 멱등)만 쓴다. 입력 조합 전수, 경계값 나열, 스타일 테스트는 쓰지 않는다.
- 기준: 테스트 하나가 완료 기준의 한 줄에 대응해야 한다. 완료 기준에 없는 테스트는 추가하지 않는다.
- LLM 호출은 테스트에서 항상 mock(`FakeLLM`이 고정 응답). 실제 모델을 쓰는 테스트는 `@pytest.mark.live`로 표시한다. 각 서비스 `pyproject.toml`의 `[tool.pytest.ini_options]`에 `markers = ["live: 실제 LLM 호출"]`과 `addopts = "-m 'not live'"`를 두어 기본 실행에서 빠지고(`make test`도 같은 필터), `make test-live`만 `-m live`로 덮어쓴다.
- MCP·api 사이는 계약 예시 JSON을 픽스처로 공유한다(`tests/fixtures/contracts/`).

## 브랜치·커밋·리뷰

- `main`은 항상 기동 가능. 트랙은 `track/<이름>` 브랜치, worktree `../Day-0_zaeho.worktrees/<이름>`.
- 트랙 완료 → 자기 완료 기준 실행·보고 → Codex 리뷰 pane(읽기 전용) → 지적 반영 → 오케스트레이터가 트랙 브랜치를 `main` 위로 rebase하고 **그 브랜치에서** `make test`·`make lint` 통과 확인 → `main`에 **squash 병합** → worktree 제거.
- 커밋 메시지는 한국어 한 문장. 본문에 실행한 테스트 명령을 적는다.
- 리뷰 기준: 계약 준수, 완료 기준 충족, 소유권 밖 파일 수정 없음, 테스트가 happy path 범위를 넘지 않음.

## 비밀값
- `infra/.env`(compose), `infra/.env.local`(로컬). 둘 다 git 무시. 예시는 `infra/.env.example`.
- pane 브리프에 키 값을 넣지 않는다. 키는 파일에서만 읽는다.
