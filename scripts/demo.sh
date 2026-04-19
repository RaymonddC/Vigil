#!/usr/bin/env bash
# I1 — Clean-clone demo startup script.
#
# Brings up the full Vigil stack in order:
#   1. HAPI FHIR (Docker) + health check
#   2. Seed synthetic patients
#   3. MCP server (background)
#   4. A2A agent (background)
#   5. FastAPI proxy (background)
#   6. Next.js dev server (background)
#   7. Health check all services
#
# Usage:
#   ./scripts/demo.sh          # start all services
#   ./scripts/demo.sh --stop   # stop all background services
#
# Acceptance: <3 min startup on warm Docker pull, video-recordable.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_DIR="$PROJECT_ROOT/.demo-pids"
LOG_DIR="$PROJECT_ROOT/.demo-logs"

# Ports
HAPI_PORT="${HAPI_PORT:-8080}"
MCP_PORT="${MCP_PORT:-7001}"
A2A_PORT="${A2A_PORT:-9000}"
PROXY_PORT="${PROXY_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[demo]${NC} $*"; }
warn() { echo -e "${YELLOW}[demo]${NC} $*"; }
err()  { echo -e "${RED}[demo]${NC} $*" >&2; }

# ---------------------------------------------------------------------------
# Stop mode
# ---------------------------------------------------------------------------

stop_services() {
    log "Stopping background services..."
    if [ -d "$PID_DIR" ]; then
        for pidfile in "$PID_DIR"/*.pid; do
            [ -f "$pidfile" ] || continue
            pid=$(cat "$pidfile")
            name=$(basename "$pidfile" .pid)
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null || true
                log "  Stopped $name (PID $pid)"
            fi
            rm -f "$pidfile"
        done
    fi
    log "Background services stopped."
    log "Run 'docker compose down' to stop HAPI FHIR."
}

if [ "${1:-}" = "--stop" ]; then
    stop_services
    exit 0
fi

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

mkdir -p "$PID_DIR" "$LOG_DIR"

# Clean up any stale PIDs
stop_services 2>/dev/null || true

# ---------------------------------------------------------------------------
# Step 1: HAPI FHIR
# ---------------------------------------------------------------------------

log "Step 1/6: Starting HAPI FHIR..."
cd "$PROJECT_ROOT"
docker compose up -d

log "  Waiting for HAPI FHIR at localhost:$HAPI_PORT..."
DEADLINE=$((SECONDS + 120))
until curl -sf "http://localhost:$HAPI_PORT/fhir/metadata" > /dev/null 2>&1; do
    if [ $SECONDS -gt $DEADLINE ]; then
        err "HAPI FHIR did not start within 120s"
        exit 1
    fi
    sleep 2
done
log "  HAPI FHIR ready."

# ---------------------------------------------------------------------------
# Step 2: Seed synthetic patients
# ---------------------------------------------------------------------------

log "Step 2/6: Seeding synthetic patients..."
uv run python data/seed_hapi.py --fhir-base "http://localhost:$HAPI_PORT/fhir" --src data/patients
log "  Seed complete."

# ---------------------------------------------------------------------------
# Step 3: MCP server
# ---------------------------------------------------------------------------

log "Step 3/6: Starting MCP server on :$MCP_PORT..."
export LLM_PROVIDER="${LLM_PROVIDER:-stub}"
uv run python -m backend.mcp_server.server > "$LOG_DIR/mcp.log" 2>&1 &
echo $! > "$PID_DIR/mcp.pid"

DEADLINE=$((SECONDS + 30))
until curl -sf "http://localhost:$MCP_PORT/health" > /dev/null 2>&1; do
    if [ $SECONDS -gt $DEADLINE ]; then
        err "MCP server did not start within 30s"
        cat "$LOG_DIR/mcp.log" | tail -20
        exit 1
    fi
    sleep 1
done
log "  MCP server ready."

# ---------------------------------------------------------------------------
# Step 4: A2A agent
# ---------------------------------------------------------------------------

log "Step 4/6: Starting A2A agent on :$A2A_PORT..."
uv run python -m backend.a2a_agent > "$LOG_DIR/a2a.log" 2>&1 &
echo $! > "$PID_DIR/a2a.pid"

DEADLINE=$((SECONDS + 30))
until curl -sf "http://localhost:$A2A_PORT/.well-known/agent-card.json" > /dev/null 2>&1; do
    if [ $SECONDS -gt $DEADLINE ]; then
        warn "A2A agent did not start within 30s (non-fatal, continuing)"
        break
    fi
    sleep 1
done
log "  A2A agent ready (or skipped)."

# ---------------------------------------------------------------------------
# Step 5: FastAPI proxy
# ---------------------------------------------------------------------------

log "Step 5/6: Starting FastAPI proxy on :$PROXY_PORT..."
uv run uvicorn backend.api.main:app --host 127.0.0.1 --port "$PROXY_PORT" > "$LOG_DIR/proxy.log" 2>&1 &
echo $! > "$PID_DIR/proxy.pid"

DEADLINE=$((SECONDS + 20))
until curl -sf "http://localhost:$PROXY_PORT/api/health" > /dev/null 2>&1; do
    if [ $SECONDS -gt $DEADLINE ]; then
        err "FastAPI proxy did not start within 20s"
        cat "$LOG_DIR/proxy.log" | tail -20
        exit 1
    fi
    sleep 1
done
log "  FastAPI proxy ready."

# ---------------------------------------------------------------------------
# Step 6: Next.js frontend
# ---------------------------------------------------------------------------

log "Step 6/6: Starting Next.js frontend on :$FRONTEND_PORT..."
cd "$PROJECT_ROOT/frontend"
pnpm dev --port "$FRONTEND_PORT" > "$LOG_DIR/frontend.log" 2>&1 &
echo $! > "$PID_DIR/frontend.pid"
cd "$PROJECT_ROOT"

DEADLINE=$((SECONDS + 30))
until curl -sf "http://localhost:$FRONTEND_PORT" > /dev/null 2>&1; do
    if [ $SECONDS -gt $DEADLINE ]; then
        warn "Next.js did not respond within 30s (may still be compiling)"
        break
    fi
    sleep 2
done
log "  Next.js frontend ready."

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
log "=== All services running ==="
log "  HAPI FHIR:      http://localhost:$HAPI_PORT/fhir"
log "  MCP Server:      http://localhost:$MCP_PORT/health"
log "  A2A Agent:       http://localhost:$A2A_PORT/.well-known/agent-card.json"
log "  FastAPI Proxy:   http://localhost:$PROXY_PORT/api/health"
log "  Frontend:        http://localhost:$FRONTEND_PORT"
echo ""
log "Stop with: ./scripts/demo.sh --stop && docker compose down"
log "Run E2E:   cd tests/e2e && npx playwright test --config playwright.config.ts"
