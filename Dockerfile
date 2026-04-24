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

# Copy dependency manifest first for layer caching. README.md is
# referenced by pyproject.toml's `readme = "README.md"`, so hatchling
# needs it present during uv sync.
COPY pyproject.toml uv.lock README.md ./

# Install third-party deps into /app/.venv (no dev extras, project itself
# deferred — it needs backend/ on disk).
RUN uv sync --frozen --no-dev --no-install-project --all-extras

# Copy application source
COPY backend/ backend/

# Copy synthetic FHIR fixture data (only used when SERVICE=fixture, but the
# layer is <1 MB and keeping a single image makes deploys simpler)
COPY data/ data/

# Install the vigil project itself as a proper non-editable wheel into the
# venv so `backend.*` imports resolve from site-packages instead of relying
# on uvicorn's CWD→sys.path side effect. This is the canonical uv production
# pattern (docs.astral.sh/uv/guides/integration/docker/).
RUN uv sync --frozen --no-dev --no-editable --all-extras

# Non-root user for container security. Chown /app so the runtime user can
# write into .venv (uv metadata + cache) and backend/api/ (SQLite DB fallback
# path), and create the volume mount-point for the review queue (see F2).
RUN adduser --disabled-password --gecos "" vigil \
    && mkdir -p /var/lib/vigil \
    && chown -R vigil:vigil /app /var/lib/vigil
USER vigil

# Put the venv's bin on PATH so `uvicorn` resolves to /app/.venv/bin/uvicorn
# without an absolute path in CMD.
ENV PATH="/app/.venv/bin:${PATH}"

# Expose all service ports; the active one depends on SERVICE env var
EXPOSE 7001 8000 8080 9000

# Entry point dispatcher — reads SERVICE env var.
# Invokes uvicorn directly from the pre-built venv rather than via
# `uv run`. `uv run` re-validates the workspace at startup and tries
# to install the project as an editable wheel, which fails with
# `Permission denied` because the vigil user can't write into a
# root-owned .venv. The deps are already installed — just run them.
CMD ["sh", "-c", "\
  case \"$SERVICE\" in \
    mcp)     exec uvicorn backend.mcp_server.server:app \
                 --host 0.0.0.0 --port ${MCP_PORT:-7001} ;; \
    a2a)     exec uvicorn backend.a2a_agent.app:app \
                 --host 0.0.0.0 --port ${A2A_PORT:-9000} ;; \
    api)     exec uvicorn backend.api.main:app \
                 --host 0.0.0.0 --port ${API_PORT:-8000} ;; \
    fixture) exec uvicorn backend.fhir_fixture.main:app \
                 --host 0.0.0.0 --port ${FIXTURE_PORT:-8080} ;; \
    *)    echo \"ERROR: SERVICE must be mcp | a2a | api | fixture (got: $SERVICE)\"; exit 1 ;; \
  esac"]
