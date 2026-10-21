# 개발 프로세스와 환경

작업 방식의 정본이다. `AGENTS.md`와 `docs/plan.md`는 핵심 규칙만 적고 이 문서를 가리킨다.

## 작업 방식

- **오케스트레이터는 조율만** 한다: 브리프 작성, 개발·리뷰 서브에이전트 기동, 결과 확인, 병합, 사용자 확인 요청. 코드와 문서는 서브에이전트가 쓴다.
- **개발과 리뷰 모두 Claude 서브에이전트**(Agent 도구, 모델 지정). 동시 개발 서브에이전트는 웨이브를 넘어 합쳐서 최대 4개이고 리뷰 서브에이전트는 수에 넣지 않는다. herdr pane은 만들지 않는다. 웨이브별 순서는 `docs/plan.md` 1절.
- **모델 배정**(작성 모델 ≠ 리뷰 모델):

| 일 | 개발 | 리뷰 |
|---|---|---|
| api·agent(상태·그래프가 복잡한 트랙) | Opus | Sonnet |
| 그 밖의 트랙(gm-fix·stage-kit·e2e·web-integrate·fix-*·report-refresh·arch-refresh 등), playtest 페르소나 | Sonnet | Opus |
| 오케스트레이터가 쓰는 계약·문서 정리 | 오케스트레이터 | Sonnet |
- 트랙마다 git worktree와 브랜치 `track/<이름>`(`sh scripts/worktree.sh <이름>`, `infra/.env`·`.env.local` 복사). 다른 트랙의 폴더를 수정하지 않고, 같은 서비스를 나눈 트랙은 `docs/plan.md` 4절 소유 파일을 따른다.
- 브리프는 `docs/handoff/briefs/brief-<트랙>.md`(템플릿은 `docs/handoff.md`), 완료 보고는 `docs/handoff/reports/<트랙>-report.md`, 리뷰 원문을 남길 때는 `docs/handoff/reviews/`. 트랙이 끝나 병합되면 브리프·보고·리뷰는 지운다(git 이력에 남음).
- 트랙은 완료 시 자기 완료 기준을 직접 실행해 결과와 검증 방식(mock / 격리 DB / 실 API / 실 LLM)을 보고한다. test·lint만으로 실제 연결 완료를 인정하지 않는다.
- **단계 루프**: 트랙 완료 보고 → 리뷰 서브에이전트(읽기 전용, 차단 항목만) → 차단 반영(같은 개발 서브에이전트에 이어서 지시, 재리뷰는 1회까지) → 커밋 → 대상 브랜치 위 rebase → `make test`·`make lint`(아래 "병합 규칙") → squash 병합(docs 트랙은 main, 코드 트랙은 `track/debate`) → worktree·브랜치 정리 → `docs/handoff.md` 진행 표 갱신 → 단계 끝이면 사용자 확인.
- 작성 모델과 리뷰 모델은 다르게 한다(위 표). UI 화면 리뷰는 Opus 서브에이전트가 실제 화면·스크린샷을 보고 한다.
- 정해지지 않은 사항은 추측으로 진행하지 않고 사용자에게 하나씩 묻는다.
- 코드에는 짧은 주석을 단다: 모듈·클래스·함수의 역할, 읽는 사람이 알아야 하는 로직(왜 그렇게 하는지), 예외 처리의 의도. 줄마다 설명하는 주석은 쓰지 않는다.
- 필요 없어진 문서·파일은 남기지 않고 지운다. 이력은 git에 있다.

### 오케스트레이터 체크리스트

- 기동 전: 선행 병합·계약 커밋·catalog_version을 브리프에 적음, 활성 트랙끼리 쓰기 경로 대조(공용 conftest·package/lock·schema·infra·문서 포함), worktree·env 두 파일 준비, 테스트 격리·실 스택 사용권 확인.
- 완료 보고 확인: 기준 커밋·수정 파일·명령/결과·검증 방식, CR마다 담당·영향·해결 커밋 또는 대기 사유, 기대 실패 목록(`tests/expected-failures.txt`) 대조: 자기 몫은 지웠고 승인 없이 늘지 않았는지.
- 병합 전: 대상 브랜치 위 rebase 상태에서 `make test`·`make lint`(병합 규칙), 소유 밖 수정·미승인 공용 변경·키·임시 산출물·`REVIEW.md` 없음, squash 대상 = 리뷰된 변경. 병합 뒤 진행 표 갱신, worktree·브랜치 정리.
- 단계 끝: 게이트 기준 확인 → 사용자에게 결과 요약과 확인 요청 → 확인 뒤 다음 웨이브.

## 도구

| 영역 | 선택 | 명령 |
|---|---|---|
| Python | 3.12, `uv`로 가상환경·lockfile. 서비스마다 `pyproject.toml` | `uv sync`, `uv run pytest` |
| 린트·포맷 | ruff (lint + format), 설정은 저장소 루트 `ruff.toml` 하나 | `uv run ruff check . && uv run ruff format --check .` |
| Node | 22, pnpm. `apps/web` | `pnpm install`, `pnpm dev`, `pnpm test` |
| 프론트 린트 | Next 기본 eslint + prettier | `pnpm lint` |
| 테스트 | pytest(+ pytest-asyncio), vitest. 연결·e2e는 `tests/` | 서비스 폴더에서 `make test` |
| 인프라 | Docker Compose. 개발 중에는 **인프라만** docker, 앱은 로컬 | `make infra-up`, `make infra-down` |
| Makefile | 루트 `Makefile`에 공통 타깃: `infra-up`, `infra-down`, `up`, `seed`, `test`, `lint`, `e2e`, `stage`, `stage-advance`, `e2e-stages`. 검사는 실패 코드를 그대로 돌려주고, 아직 없는 서비스 폴더만 건너뛴다 | |
| seed | 루트 `scripts/seed.py`(httpx만 사용, 관리자 가입·채용 건 생성·rag 재색인 호출). be-foundation 소유 | `make seed` |

## 로컬 실행 (개발 중)

```
make infra-up           # postgres(5432), rabbitmq(5672), rag-mcp(9102)를 127.0.0.1에 공개 (compose + compose.dev.yml)
cd services/api && uv run python -m app.run --reload      # 한 프로세스에서 공개 8000 + 내부 8001 두 리스너
cd services/debate-mcp && uv run python -m debate_mcp     # 9101 (G-F 전에는 services/business-mcp, business_mcp)
cd services/assessment-mcp && uv run python -m assessment_mcp  # 9103 (G-F 뒤)
cd services/report-worker && uv run python -m report_worker
cd apps/web && pnpm dev                                   # 3000
```

### 토론형 스택으로 단계별 확인

단계 시드·단계별 화면 테스트·playtest는 G-E 전에도 이 순서로 띄운다(`docs/common/testing.md` "단계별 테스트").

1. `infra/.env`(compose)와 `infra/.env.local`(로컬, 호스트명 `localhost`, `API_INTERNAL_URL=http://localhost:8001`)을 준비한다. 테스트용 값: `ENABLE_TEST_API=1`, 결정적 실행이면 `LLM_FAKE=1`(실제 모델이면 비움), `AGENT_RUNNER=session`(기본값).
2. 전체 compose(8개 서비스: web·api·debate-mcp·rag-mcp·assessment-mcp·report-worker·postgres·rabbitmq)는 `make up`, 앱을 로컬에서 고치며 볼 때는 `make infra-up` 뒤 위 명령으로 앱을 띄운다.
3. `make seed`(자료 원문 시드 → 관리자·채용 건 → rag 재색인). rag-mcp 첫 기동은 BGE-M3를 받는다.
4. `make stage STAGE=<keyword|problem|solution|proposal|ended> [MIN=15] [LLM=fake|live]` → 출력된 초대 링크를 브라우저로 연다. 시간을 당길 때는 `make stage-advance SID=<id> TO=deadline|idle|card:<id>|<초>`.
5. 단계별 화면 테스트는 `make e2e-stages [STAGE=<단계>]`. 기록은 `tests/e2e/records/stages/<단계>/`.

`LLM=fake`와 `live`는 스택 env(`LLM_FAKE`)로 갈리므로 바꿀 때는 api·report-worker를 다시 띄운다. 통합 스택 사용권 규칙(아래)은 그대로다.

- `infra/docker-compose.dev.yml`(override)이 인프라 포트를 로컬에 바인딩하고, 컨테이너 안의 rag-mcp가 호스트의 api 내부 포트를 보도록 `API_INTERNAL_URL=http://host.docker.internal:8001`을 준다.
- `infra/.env`를 각 서비스가 `python-dotenv`로 읽는다. 로컬에서는 호스트명을 `localhost`로 바꾼 `infra/.env.local`을 우선 읽는다(둘 다 git 무시).
- `app.run`은 uvicorn `Server` 두 개를 같은 asyncio 루프에서 띄운다. hub·세션별 메일박스·WS 송신 큐·스케줄러가 한 프로세스에 있어야 하므로 두 앱을 별도 프로세스로 띄우지 않는다. be-foundation 소유.
- **테스트 격리.** api는 임시 DB, worker는 임시 스키마·큐, rag-mcp는 임시 DB를 쓴다(각 트랙 보고서에 기록된 방식). 그래서 `schema.sql` 수정이 다른 worktree의 격리 테스트를 깨지 않는다. 격리를 깨는 테스트는 넣지 않는다.
- **실제 스택 사용권.** 공용 postgres·rabbitmq·실행 중 앱은 한 번에 한 작업만 쓴다. 사용권에는 사용자·worktree·커밋·DB/schema·큐·catalog_version을 적고, 스택 재기동·스키마 적용·seed·색인은 사용권 보유 작업에서만 한다.
- **실행 중인 통합 스택은 한 번에 하나**다. 트랙 서브에이전트는 단위 테스트(mock)로 개발하고, 실제 스택이 필요하면 공용 인프라(`make infra-up`은 main 저장소에서 한 번)에 자기 worktree의 앱을 붙인다. api를 두 개 띄우면 스케줄러와 메일박스(세션당 소비자 1개) 전제가 깨지므로 금지. 포트 오프셋은 두지 않는다.
- 전체 compose 기동은 G-F(백엔드 기반), 단계별 확인(stage-kit·stage-e2e·playtest), W5-3 통합 검증에서 한다.

## TDD 방식

- 테스트를 먼저 쓰되 **happy path 중심**이다. 각 기능의 정상 경로 1개와 계약·평가 항목이 요구하는 실패 경로(권한 403, 공개 전 423/not_released, 승인 전 409, 재시도·DLQ, 멱등)만 쓴다. 입력 조합 전수, 경계값 나열, 스타일 테스트는 쓰지 않는다.
- 기준: 테스트 하나가 완료 기준의 한 줄에 대응해야 한다. 완료 기준에 없는 테스트는 추가하지 않는다.
- LLM 호출은 테스트에서 항상 mock(`FakeLLM`이 고정 응답). 실제 모델을 쓰는 테스트는 `@pytest.mark.live`로 표시한다. 각 서비스 `pyproject.toml`의 `[tool.pytest.ini_options]`에 `markers = ["live: 실제 LLM 호출"]`과 `addopts = "-m 'not live'"`를 두어 기본 실행에서 빠지고(`make test`도 같은 필터), `make test-live`만 `-m live`로 덮어쓴다.
- MCP·api 사이는 계약 예시 JSON을 픽스처로 공유한다(`tests/fixtures/contracts/`).

## 브랜치·커밋·리뷰

- `main`은 항상 기동 가능. 트랙은 `track/<이름>` 브랜치, worktree `../Day-0_zaeho.worktrees/<이름>`. docs 트랙은 main, 코드 트랙은 통합 브랜치 `track/debate`가 병합 대상이다(`docs/plan.md` 3절).
- 리뷰는 **리뷰 서브에이전트** 한 번(위 모델 배정, 읽기 전용). 오케스트레이터가 기동한다. 프롬프트에 worktree 경로, 트랙 브리프 경로, 비교 기준(`git diff <기준 커밋>...HEAD`), 아래 리뷰 기준, "소스 수정·git 변경·외부 게시 금지, 차단/권장으로 나눠 답할 것"을 적는다. 원문을 남길 때는 `docs/handoff/reviews/<트랙>-review.md`이고 병합 뒤 지운다.
- 병합 전 오케스트레이터가 대상 브랜치 위로 rebase하고 **그 브랜치에서** `make test`·`make lint`를 돌린다. **병합 규칙**:
  - main(docs 트랙, G-E의 `track/debate` → main): 실패 0.
  - `track/debate`(코드 트랙, G-C~G-E): `make lint` 실패 0, `make test` 실패는 **승인된 기대 실패 목록** `tests/expected-failures.txt`(테스트 노드 id · 담당 트랙 · 사유) 안에만 있어야 하고 목록 밖 실패 0. 병합하는 트랙은 자기 몫의 줄을 지우고, 줄을 늘리려면 오케스트레이터 승인이 필요하다. 목록은 contracts(G-C)가 만들고 be-foundation(G-F)이 옛 테스트 삭제에 맞춰 갱신하며, G-E에서 비어 있어야 한다.
- 커밋 메시지는 한국어 한 문장. 본문에 실행한 테스트 명령을 적는다.
- 리뷰 기준: 계약 준수, 완료 기준 충족, 소유권 밖 파일 수정 없음, 테스트가 happy path 범위를 넘지 않음.

## 비밀값
- `infra/.env`(compose), `infra/.env.local`(로컬). 둘 다 git 무시. 예시는 `infra/.env.example`.
- 브리프에 키 값을 넣지 않는다. 키는 파일에서만 읽는다.
