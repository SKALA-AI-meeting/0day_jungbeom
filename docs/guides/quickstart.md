# 처음 실행하기

처음 저장소를 받은 사람이 테스트를 돌리고, 스택을 띄워 지원자 화면을 열어 보기까지의 순서다. 실행 모드별 포트·DB·env 차이는 [configuration.md](configuration.md), 테스트 명령의 범위는 [testing.md](testing.md).

## 1. 필요한 도구

| 도구 | 버전·비고 |
|---|---|
| Python | 3.12, [`uv`](https://docs.astral.sh/uv/)로 가상환경과 lockfile을 다룬다(서비스마다 `pyproject.toml`) |
| Node | 22, `pnpm`(`corepack enable`) |
| Docker | Docker Compose v2. 격리 e2e 스택은 `!override` 태그를 쓰므로 2.24.4 이상 |
| libpq | macOS는 `brew install libpq && brew link --force libpq`(`psql`·드라이버 빌드용) |

## 2. 받기와 의존성

```
git clone <저장소 주소> && cd Day-0_zaeho
for s in services/api services/debate-mcp services/rag-mcp services/assessment-mcp services/report-worker; do (cd $s && uv sync); done
(cd apps/web && pnpm install)
make test && make lint
```

`make test`는 postgres가 없으면 api의 DB 테스트를 건너뛴다(skip). DB까지 확인하려면 아래 3의 `make infra-up` 뒤에 다시 돌린다.

## 3. env 준비

```
cp infra/.env.example infra/.env
```

- `OPENAI_API_KEY`(실제 모델을 쓸 때), `JWT_SECRET`(32바이트 이상 임의 값), `INTERNAL_TOKEN`, `ASSESSMENT_MCP_TOKEN`(임의 문자열)을 채운다. 키 값은 이 파일에만 두고 커밋하지 않는다.
- LLM 없이 결정적으로 돌리려면 `LLM_FAKE=1`. 단계 시드·시간 당기기를 쓰려면 `ENABLE_TEST_API=1`(예시 값 그대로).
- 앱을 로컬에서 띄울 때는 `infra/.env`를 복사한 `infra/.env.local`을 만들고 서비스 주소를 `localhost`로 바꾼다(바꿀 항목은 [configuration.md](configuration.md) "로컬 실행용 `infra/.env.local`"). Python 서비스는 `.env.local`을 먼저 읽는다.

## 4. 띄우기 (로컬 개발 모드)

앱을 고치면서 볼 때의 기본 방식이다. 인프라와 무거운 rag-mcp만 컨테이너로 띄우고 나머지는 로컬에서 띄운다.

```
make infra-up                                                    # postgres 5432, rabbitmq 5672, rag-mcp 9102 (127.0.0.1)
cd services/api && uv run python -m app.run --reload             # 공개 8000 + 내부 8001 + 스케줄러(한 프로세스)
cd services/debate-mcp && uv run python -m debate_mcp            # 9101
cd services/assessment-mcp && uv run python -m assessment_mcp    # 9103
cd services/report-worker && uv run python -m report_worker
cd apps/web && pnpm dev                                          # 3000
make seed                                                        # 자료 원문 시드 → 관리자·채용 건 → rag 재색인
```

- rag-mcp는 첫 기동 때 BGE-M3 모델(약 2.3GB)을 받는다. healthy가 될 때까지 몇 분 걸릴 수 있다.
- `make seed`는 postgres 5432·api 8000·rag-mcp 9102에 붙는다. 관리자 계정 `admin@dayzero.example`(회사 "데모 회사")과 채용 건을 만든다. 비밀번호 기본값과 바꾸는 옵션은 `scripts/seed.py`의 `--email`·`--password`.
- 각 명령은 저장소 루트 기준 경로다. 터미널을 나눠 띄운다.

## 5. 지원자 화면 열기

```
make stage STAGE=keyword MIN=15        # 단계 시드 세션을 만들고 초대 링크·세션 id를 출력
```

출력된 링크를 브라우저로 열면 그 단계부터 진행된다. 시간 초과·침묵 초대·카드를 기다리지 않고 보려면 `make stage-advance SID=<세션 id> TO=deadline|idle|card:<카드 id>`. 관리자 화면은 `http://localhost:3000/admin/login`.

계정은 둘로 나뉜다. `make seed`가 만든 `admin@dayzero.example` 회사와 `make stage`(테스트 API)가 만드는 세션의 회사는 다르다. 단계 시드 세션은 별도 기업의 관리자 `e2e@example.com`이 소유하므로(기업 간 격리), 그 세션의 리포트(`STAGE=ended`가 출력하는 `admin_report_url`)는 `e2e@example.com`으로 로그인해 본다. 이 계정의 비밀번호는 `services/api/app/services/test_sessions.py`의 `SEED_PASSWORD`, 다른 관리자로 만들려면 `scripts/make_session.py --admin-email`.

## 6. 정상 확인과 종료

- api `curl -fs http://localhost:8000/health`, web `http://localhost:3000/api/health`.
- 세션이 끝나면(`make stage STAGE=ended` 또는 제출) report-worker가 리포트 초안을 만든다. 관리자 지원자 목록에서 상태가 "검토 필요"로 바뀌면 정상이다.
- 끝낼 때는 로컬 앱을 멈추고 `make infra-down`. 볼륨(DB 데이터·모델 캐시)은 남는다.

## 다른 실행 방식

- 8개 서비스를 모두 컨테이너로: `make up` / `make down`. 이 모드는 postgres·rag-mcp를 호스트에 열지 않으므로 호스트의 `make seed`가 닿지 않는다. 전체 compose용 시드는 `make seed-compose [SEED_ARGS="--minutes 15"]`다([configuration.md](configuration.md) "실행 모드").
- 단계별 화면 테스트용 격리 스택: `make e2e-stack-up` → `make e2e-stack-seed` → `make e2e-stages` → `make e2e-stack-down`([testing.md](testing.md)).
