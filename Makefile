.PHONY: up down seed dev mcp agent test lint ci demo demo-stop demo-warmup e2e

# Infrastructure
up:
	docker compose up -d
	@echo "Waiting for HAPI FHIR..."
	@until curl -sf http://localhost:8080/fhir/metadata > /dev/null 2>&1; do sleep 2; done
	@echo "HAPI FHIR ready at http://localhost:8080/fhir"

down:
	docker compose down

seed:
	python data/seed_hapi.py --fhir-base http://localhost:8080/fhir --src data/patients

# Backend
mcp:
	uv run python -m backend.mcp_server.server

agent:
	uv run python -m backend.a2a_agent

proxy:
	uv run uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 --reload

# Frontend
frontend:
	cd frontend && pnpm dev

# Quality
test:
	uv run pytest -v --tb=short

lint:
	uv run ruff check backend/ tests/

# Optional type check — FastMCP Context typing is Optional at the SDK layer,
# produces 16 union-attr false positives. Run manually when hardening pre-prod.
typecheck:
	uv run mypy backend/

ci: lint test

# Demo — orchestrated startup with health checks
demo:
	./scripts/demo.sh

demo-stop:
	./scripts/demo.sh --stop
	docker compose down

demo-warmup:
	@echo "=== Pre-flight: reseed HAPI ==="
	$(MAKE) seed
	@echo "=== Pre-flight: ping LLM provider ==="
	uv run python -c "from backend.llm.provider import get_provider; import asyncio; asyncio.run(get_provider().complete('ping', 10))"
	@echo "=== Pre-flight: tick agent ==="
	curl -sS -X POST http://localhost:8000/api/agent/tick
	@echo "=== Pre-flight: warm frontend routes ==="
	curl -sf http://localhost:3000/ > /dev/null
	curl -sf http://localhost:3000/patients > /dev/null
	@echo "=== All services healthy ==="

# E2E tests (requires make demo running)
e2e:
	cd frontend && npx playwright install --with-deps chromium
	cd tests/e2e && npx playwright test --config playwright.config.ts
