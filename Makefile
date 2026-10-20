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

.PHONY: infra-up infra-down up seed test test-live lint e2e
