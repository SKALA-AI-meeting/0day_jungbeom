# 공통 타깃. 서비스별 세부는 각 폴더의 Makefile이 맡는다(foundation 트랙이 만든다).
COMPOSE     = docker compose -f infra/docker-compose.yml --env-file infra/.env
COMPOSE_DEV = $(COMPOSE) -f infra/docker-compose.dev.yml
SERVICES    = services/api services/business-mcp services/rag-mcp services/report-worker

infra-up:        ## 개발용 인프라만, 로컬 포트 바인딩: postgres 5432, rabbitmq 5672, rag-mcp 9102
	$(COMPOSE_DEV) up -d postgres rabbitmq rag-mcp

infra-down:
	$(COMPOSE_DEV) down

up:              ## 전체 compose (M0.5 확인, M3 통합)
	$(COMPOSE) up -d --build

seed:            ## 관리자·채용 건 시드와 rag 재색인 (api 8000/8001, rag-mcp 9102가 떠 있어야 함)
	uv run --project services/api python scripts/seed.py

test:            ## 모든 서비스 단위 테스트 (LLM mock, live 마커 제외). 없는 폴더만 건너뜀
	@for s in $(SERVICES); do \
	  if [ -f $$s/pyproject.toml ]; then (cd $$s && uv run pytest -q -m "not live") || exit 1; fi; \
	done
	@if [ -f apps/web/package.json ]; then (cd apps/web && pnpm test --silent) || exit 1; fi

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

.PHONY: infra-up infra-down up seed test test-live lint e2e test-e2e eval-live e2e-concurrent e2e-auth e2e-faults
