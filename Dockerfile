# Vigil Python services — single image, multi-service entry point
#
# Build once, run three ways:
#   docker build -t vigil .
#   docker run -e SERVICE=mcp   vigil   → MCP server  :7001
#   docker run -e SERVICE=a2a   vigil   → A2A agent   :9000
#   docker run -e SERVICE=api   vigil   → FastAPI proxy :8000
#
# In Fly.io each service is its own app sharing this image; the CMD
# is overridden per app via fly.toml [processes] or [deployment].

FROM python:3.11-slim AS base

WORKDIR /app

# System deps: curl for healthchecks only
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv==0.4.29

# Copy dependency manifest first for layer caching
COPY pyproject.toml uv.lock ./

# Install runtime deps only (no dev extras)
RUN uv sync --frozen --no-dev --all-extras

# Copy application source
COPY backend/ backend/

# Non-root user for container security
RUN adduser --disabled-password --gecos "" vigil
USER vigil

# Expose all service ports; the active one depends on SERVICE env var
EXPOSE 7001 8000 9000

# Entry point dispatcher — reads SERVICE env var
CMD ["sh", "-c", "\
  case \"$SERVICE\" in \
    mcp)  exec uv run uvicorn backend.mcp_server.server:app \
              --host 0.0.0.0 --port ${MCP_PORT:-7001} ;; \
    a2a)  exec uv run uvicorn backend.a2a_agent.app:app \
              --host 0.0.0.0 --port ${A2A_PORT:-9000} ;; \
    api)  exec uv run uvicorn backend.api.main:app \
              --host 0.0.0.0 --port ${API_PORT:-8000} ;; \
    *)    echo \"ERROR: SERVICE must be mcp | a2a | api (got: $SERVICE)\"; exit 1 ;; \
  esac"]
