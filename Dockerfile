# Vigil Python services — single image, multi-service entry point
#
# Build once, run four ways:
#   docker build -t vigil .
#   docker run -e SERVICE=mcp     vigil   → MCP server       :7001
#   docker run -e SERVICE=a2a     vigil   → A2A agent        :9000
#   docker run -e SERVICE=api     vigil   → FastAPI proxy    :8000
#   docker run -e SERVICE=fixture vigil   → FHIR fixture     :8080
#
# In Fly.io each service is its own app sharing this image; the CMD
# is overridden per app via fly.toml [processes] or [deployment].
# On Render.com the Blueprint in render.yaml maps SERVICE per service.

FROM python:3.11-slim AS base

WORKDIR /app

# System deps: curl for healthchecks only
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv==0.4.29

# Copy dependency manifest first for layer caching.
# README.md is listed as `readme = "README.md"` in pyproject.toml — the
# build backend (hatchling) opens it when uv materializes the project,
# so it must be present in the image even though we pass
# --no-install-project at build time. `uv run` at container start also
# re-validates the workspace and fails without it.
COPY pyproject.toml uv.lock README.md ./

# Install runtime deps only (no dev extras)
RUN uv sync --frozen --no-dev --no-install-project --all-extras

# Copy application source
COPY backend/ backend/

# Copy synthetic FHIR fixture data (only used when SERVICE=fixture, but the
# layer is <1 MB and keeping a single image makes deploys simpler)
COPY data/ data/

# Non-root user for container security
RUN adduser --disabled-password --gecos "" vigil
USER vigil

# Expose all service ports; the active one depends on SERVICE env var
EXPOSE 7001 8000 8080 9000

# Entry point dispatcher — reads SERVICE env var
CMD ["sh", "-c", "\
  case \"$SERVICE\" in \
    mcp)     exec uv run uvicorn backend.mcp_server.server:app \
                 --host 0.0.0.0 --port ${MCP_PORT:-7001} ;; \
    a2a)     exec uv run uvicorn backend.a2a_agent.app:app \
                 --host 0.0.0.0 --port ${A2A_PORT:-9000} ;; \
    api)     exec uv run uvicorn backend.api.main:app \
                 --host 0.0.0.0 --port ${API_PORT:-8000} ;; \
    fixture) exec uv run uvicorn backend.fhir_fixture.main:app \
                 --host 0.0.0.0 --port ${FIXTURE_PORT:-8080} ;; \
    *)    echo \"ERROR: SERVICE must be mcp | a2a | api | fixture (got: $SERVICE)\"; exit 1 ;; \
  esac"]
