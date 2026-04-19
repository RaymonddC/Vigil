#!/usr/bin/env bash
# scripts/tunnel-cf.sh — cloudflared tunnel fallback for Vigil demo day
#
# Opens quick-tunnels (no account needed) for three services:
#   FastAPI proxy :8000, MCP server :7001, A2A agent :9000
#
# HAPI (:8080) is NEVER tunneled — SEC-10.
#
# Quick tunnels are ephemeral — URLs change on restart.
# For a persistent URL, use a named Cloudflare Tunnel (see DEPLOY.md §4).
#
# Prerequisites:
#   cloudflared installed: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
#
# Usage:
#   export VIGIL_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
#   ./scripts/tunnel-cf.sh
#
# Tunnel URLs are printed to stdout once cloudflared starts. Update Vercel:
#   vercel env add NEXT_PUBLIC_BACKEND_URL  <api-url>
#   vercel env add NEXT_PUBLIC_MCP_URL      <mcp-url>
#   vercel env add NEXT_PUBLIC_A2A_URL      <a2a-url>

set -euo pipefail

: "${VIGIL_API_KEY:?ERROR: VIGIL_API_KEY must be set.}"

if ! command -v cloudflared &>/dev/null; then
  echo "ERROR: cloudflared not found."
  echo "Install: curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && sudo dpkg -i cloudflared.deb"
  exit 1
fi

echo "=== Vigil cloudflared tunnel setup ==="
echo "Starting three quick-tunnels in background..."
echo ""

# Start tunnels in background, capture URLs from log output
LOGDIR=$(mktemp -d /tmp/vigil-cf-XXXXXX)

cloudflared tunnel --url http://localhost:8000 --logfile "$LOGDIR/api.log" &
CF_API_PID=$!

cloudflared tunnel --url http://localhost:7001 --logfile "$LOGDIR/mcp.log" &
CF_MCP_PID=$!

cloudflared tunnel --url http://localhost:9000 --logfile "$LOGDIR/a2a.log" &
CF_A2A_PID=$!

echo "Tunnel PIDs: api=$CF_API_PID, mcp=$CF_MCP_PID, a2a=$CF_A2A_PID"
echo "Waiting for tunnel URLs (up to 30s)..."

extract_url() {
  local logfile="$1"
  local timeout=30
  local elapsed=0
  while [ $elapsed -lt $timeout ]; do
    url=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$logfile" 2>/dev/null | head -1)
    if [ -n "$url" ]; then
      echo "$url"
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  echo "(timeout — check $logfile)"
}

API_URL=$(extract_url "$LOGDIR/api.log")
MCP_URL=$(extract_url "$LOGDIR/mcp.log")
A2A_URL=$(extract_url "$LOGDIR/a2a.log")

echo ""
echo "=== Tunnel URLs ==="
echo "  BACKEND  (FastAPI proxy): $API_URL"
echo "  MCP      (tool server):   $MCP_URL"
echo "  A2A      (agent):         $A2A_URL"
echo ""
echo "AgentCard: $A2A_URL/.well-known/agent-card.json"
echo ""
echo "Update Vercel env (no redeploy needed):"
echo "  vercel env add NEXT_PUBLIC_BACKEND_URL $API_URL"
echo "  vercel env add NEXT_PUBLIC_MCP_URL     $MCP_URL"
echo "  vercel env add NEXT_PUBLIC_A2A_URL     $A2A_URL"
echo ""
echo "Press Ctrl+C to stop all tunnels."

# Wait for all background jobs; kill them on Ctrl+C
cleanup() {
  echo "Stopping cloudflared tunnels..."
  kill $CF_API_PID $CF_MCP_PID $CF_A2A_PID 2>/dev/null || true
  rm -rf "$LOGDIR"
}
trap cleanup EXIT INT TERM

wait $CF_API_PID $CF_MCP_PID $CF_A2A_PID
