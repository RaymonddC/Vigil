#!/usr/bin/env bash
# scripts/tunnel.sh — ngrok tunnel fallback for Vigil demo day
#
# Opens three ngrok tunnels:
#   - FastAPI proxy   :8000  → public HTTPS URL (printed as BACKEND_URL)
#   - MCP server      :7001  → public HTTPS URL (printed as MCP_URL)
#   - A2A agent       :9000  → public HTTPS URL (printed as A2A_URL)
#
# HAPI (:8080) is NEVER tunneled — SEC-10.
#
# Prerequisites:
#   - ngrok installed and authenticated (ngrok config add-authtoken <token>)
#   - All three backend services running locally (make mcp agent proxy)
#   - VIGIL_API_KEY exported in env for --request-header injection
#
# Usage:
#   export VIGIL_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
#   ./scripts/tunnel.sh
#
# After tunnels open, update Vercel env vars:
#   vercel env add NEXT_PUBLIC_BACKEND_URL   (paste BACKEND_URL)
#   vercel env add NEXT_PUBLIC_MCP_URL       (paste MCP_URL)
#   vercel env add NEXT_PUBLIC_A2A_URL       (paste A2A_URL)
# No redeploy needed — Vercel picks up env updates on next request.

set -euo pipefail

: "${VIGIL_API_KEY:?ERROR: VIGIL_API_KEY must be set. Run:
  export VIGIL_API_KEY=\$(python -c \"import secrets; print(secrets.token_urlsafe(32))\")}"

echo "=== Vigil ngrok tunnel setup ==="
echo "VIGIL_API_KEY: ${VIGIL_API_KEY:0:8}... (truncated)"
echo ""

# Check ngrok is available
if ! command -v ngrok &>/dev/null; then
  echo "ERROR: ngrok not found. Install from https://ngrok.com/download"
  exit 1
fi

# Check services are up
for port in 8000 7001 9000; do
  if ! curl -sf "http://localhost:${port}/$([ "$port" = "8000" ] && echo "api/health" || echo "health")" > /dev/null 2>&1; then
    echo "WARNING: Service on :${port} not reachable. Run 'make mcp agent proxy' first."
  fi
done

# ngrok config file approach (multiple tunnels in one process)
NGROK_CONFIG=$(mktemp /tmp/vigil-ngrok-XXXXXX.yml)
cat > "$NGROK_CONFIG" <<EOF
version: "2"
tunnels:
  vigil-api:
    proto: http
    addr: 8000
    inspect: false

  vigil-mcp:
    proto: http
    addr: 7001
    inspect: false

  vigil-a2a:
    proto: http
    addr: 9000
    inspect: false
EOF

echo "Starting ngrok tunnels (config: $NGROK_CONFIG)..."
echo "Press Ctrl+C to stop all tunnels."
echo ""
echo "After tunnels open, query the ngrok API for URLs:"
echo "  curl -s http://localhost:4040/api/tunnels | python -m json.tool"
echo ""
echo "Then update Vercel:"
echo "  vercel env add NEXT_PUBLIC_BACKEND_URL <api-url>"
echo "  vercel env add NEXT_PUBLIC_MCP_URL     <mcp-url>"
echo "  vercel env add NEXT_PUBLIC_A2A_URL     <a2a-url>"
echo ""

# Trap to clean up config file on exit
trap "rm -f $NGROK_CONFIG" EXIT

ngrok start --all --config="$NGROK_CONFIG"
