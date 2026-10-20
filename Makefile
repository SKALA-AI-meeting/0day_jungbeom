# 공통 타깃. 서비스별 세부는 각 폴더의 Makefile이 맡는다(foundation 트랙이 만든다).
COMPOSE = docker compose -f infra/docker-compose.yml --env-file infra/.env
SERVICES = services/api services/business-mcp services/rag-mcp services/report-worker

infra-up:        ## 개발용 인프라만: postgres, rabbitmq, rag-mcp
	$(COMPOSE) up -d postgres rabbitmq rag-mcp

infra-down:
	$(COMPOSE) down

up:              ## 전체 compose (M0.5 확인, M3 통합)
	$(COMPOSE) up -d --build

seed:
	cd services/api && uv run python -m scripts.seed

test:            ## 모든 서비스 단위 테스트 (LLM mock)
	@for s in $(SERVICES); do (cd $$s && [ -f pyproject.toml ] && uv run pytest -q) || exit 1; done
	@cd apps/web && [ -f package.json ] && pnpm test --silent || true

test-live:       ## 실제 LLM 호출 테스트만
	cd services/api && uv run pytest -q -m live

lint:
	uv run ruff check . && uv run ruff format --check .
	@cd apps/web && [ -f package.json ] && pnpm lint || true

e2e:             ## 전체 compose가 떠 있어야 한다
	uv run python tests/e2e/run.py --script scenarios/e2e/all_four.yaml

.PHONY: infra-up infra-down up seed test test-live lint e2e
