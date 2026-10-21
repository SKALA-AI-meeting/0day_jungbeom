# 공통 타깃. 서비스 목록은 docs/worker-infra/design.md "Docker Compose"(8개 서비스)와 같다.
COMPOSE     = docker compose -f infra/docker-compose.yml --env-file infra/.env
COMPOSE_DEV = $(COMPOSE) -f infra/docker-compose.dev.yml
SERVICES    = services/api services/debate-mcp services/rag-mcp services/assessment-mcp services/report-worker
# 저장소 루트에서 도는 검사: 계약 픽스처(G-C)와 미션 카탈로그 정합성
ROOT_TESTS  = tests/test_contract_fixtures.py scenarios/missions/debate/tests
XFAIL       = tests/expected-failures.txt

# 기대 실패 목록에서 접두어(셸 변수 p) 아래 줄을 그 폴더 기준 경로로 꺼내 건너뛰기 인자로 만든다.
# 노드 id(::)는 FLAG_NODE, 파일·디렉터리는 FLAG_PATH. 주석·빈 줄은 무시한다.
XFAIL_ARGS = awk -F'|' -v p="$$p" -v fn="$$fn" -v fp="$$fp" '!/^[[:space:]]*(\#|$$)/ { \
	gsub(/[[:space:]]+/, "", $$1); if (index($$1, p) != 1) next; x = substr($$1, length(p) + 1); \
	if (index(x, "::")) { if (fn != "") print fn " " x } else print fp " " x }' $(XFAIL)

infra-up:        ## 개발용 인프라만, 로컬 포트 바인딩: postgres 5432, rabbitmq 5672, rag-mcp 9102
	$(COMPOSE_DEV) up -d postgres rabbitmq rag-mcp

infra-down:
	$(COMPOSE_DEV) down

up:              ## 전체 compose 8개 서비스(G-F 확인, 통합)
	$(COMPOSE) up -d --build --wait

down:
	$(COMPOSE) down

seed:            ## 자료 원문 시드 → 관리자·채용 건 → rag 재색인 (postgres 5432, api 8000, rag-mcp 9102)
	uv run --project services/api python scripts/seed.py

test:            ## 단위 테스트 전부(LLM mock, live 제외). 기대 실패 목록(tests/expected-failures.txt)의 테스트는 건너뛴다
	@p=""; fn=--deselect; fp=--ignore; skips=$$($(XFAIL_ARGS)); \
	  echo "== root $(ROOT_TESTS)"; uv run pytest -q -p no:cacheprovider $$skips $(ROOT_TESTS) || exit 1
	@for s in $(SERVICES); do \
	  if [ -f $$s/pyproject.toml ]; then \
	    p="$$s/"; fn=--deselect; fp=--ignore; skips=$$($(XFAIL_ARGS)); \
	    echo "== $$s $$skips"; \
	    (cd $$s && uv run pytest -q -m "not live" $$skips) || exit 1; \
	  fi; \
	done
	@if [ -f apps/web/package.json ]; then \
	  p="apps/web/"; fn=""; fp=--exclude; skips=$$($(XFAIL_ARGS)); \
	  echo "== apps/web $$skips"; (cd apps/web && pnpm test --silent $$skips) || exit 1; \
	fi

test-live:       ## 실제 LLM 호출 테스트만
	cd services/api && uv run pytest -q -m live

lint:
	uv run ruff check . && uv run ruff format --check .
	@if [ -f apps/web/package.json ]; then (cd apps/web && pnpm lint) || exit 1; fi

e2e:             ## 전체 compose가 떠 있어야 한다
	uv run --project services/api python tests/e2e/run.py --script scenarios/e2e/all_five.yaml

E2E_PYTEST = PYTHONPATH=services/api:. uv run --project services/api pytest -q -p no:cacheprovider \
	-o asyncio_mode=auto -o asyncio_default_fixture_loop_scope=session \
	-o asyncio_default_test_loop_scope=session -o markers="live: 실제 LLM 호출"

test-e2e:        ## e2e 러너·단언·근거 정확성 픽스처 단위 테스트(mock: 격리 DB·FakeLLM, infra-up 필요)
	$(E2E_PYTEST) -m "not live" tests/e2e tests/eval

eval-live:       ## 근거 정확성 픽스처를 실제 모델로 1회(결과는 tests/e2e/records/eval-live-<일시>.md)
	$(E2E_PYTEST) -m live tests/eval

e2e-concurrent:  ## 단언 7(대본 5개 동시). 스택이 떠 있어야 한다
	uv run --project services/api python tests/e2e/run.py --concurrent

e2e-auth:        ## 단언 8(인증 경계). 스택이 떠 있어야 한다
	uv run --project services/api python tests/e2e/run.py --auth

e2e-faults:      ## 단언 6(장애 주입 6종). 인프라만 떠 있으면 러너가 앱을 띄운다
	uv run --project services/api python tests/e2e/run.py --faults all

.PHONY: infra-up infra-down up down seed test test-live lint e2e test-e2e eval-live e2e-concurrent e2e-auth e2e-faults
