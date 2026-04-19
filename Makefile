.PHONY: up down seed dev mcp agent test lint ci demo-warmup

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
	uv run python -m backend.a2a_agent.main

proxy:
	uv run uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
frontend:
	cd frontend && pnpm dev

# Quality
test:
	uv run pytest -v --tb=short

lint:
	uv run ruff check backend/ tests/
	uv run mypy backend/

ci: lint test

# Demo
demo: up seed mcp agent proxy frontend

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
