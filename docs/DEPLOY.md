# Vigil — Deployment Guide (I5)

Public backend hosting so Prompt Opinion's runtime can call the MCP tools
and the AgentCard is fetchable from `/.well-known/agent-card.json`.

---

## Service map

| Service | Port | Exposed publicly? | Purpose |
|---|---|---|---|
| FastAPI proxy | 8000 | Yes | Dashboard API, approve endpoint |
| MCP server | 7001 | Yes | 4 clinical tools — PO calls this |
| A2A agent | 9000 | Yes | AgentCard + JSON-RPC endpoint |
| HAPI FHIR | 8080 | **Never** (SEC-10) | Internal FHIR store |

HAPI MUST stay on `127.0.0.1:8080` (local) or on a **private internal
network** (cloud) — never behind a public route or tunnel.

---

**Which option should I pick?**

- Free, no credit card, permanent URL → **Option E (Render.com, fixture mode)**. Recommended for most hackathon teams.
- Need HAPI persistence and willing to spend ~$10/mo → Option D (GCP Cloud Run) or Option B (Fly.io).
- Laptop-local demo only → Option A (tunnel).

---

## Option A — Tunnel (recommended for demo day)

Fastest, zero infrastructure. Run everything locally; expose three services
via ngrok or cloudflared. HAPI stays on localhost.

### Quickstart

```bash
# 1. Start HAPI + seed patients
make up seed

# 2. Start backend services (three terminals or tmux panes)
make mcp       # MCP server  :7001
make agent     # A2A agent   :9000
make proxy     # FastAPI     :8000

# 3. Generate API key and export it
export VIGIL_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
echo "VIGIL_API_KEY=$VIGIL_API_KEY"   # save this

# 4a. Start ngrok tunnels (preferred — stable dashboard UI)
chmod +x scripts/tunnel.sh
./scripts/tunnel.sh

# 4b. Alternative: cloudflared quick-tunnels (no account required)
chmod +x scripts/tunnel-cf.sh
./scripts/tunnel-cf.sh
```

After tunnels open, the script prints three URLs. Update your Vercel
frontend environment variables — no redeploy needed:

```bash
vercel env add NEXT_PUBLIC_BACKEND_URL   # paste FastAPI URL
vercel env add NEXT_PUBLIC_MCP_URL       # paste MCP URL
vercel env add NEXT_PUBLIC_A2A_URL       # paste A2A URL
```

Test that PO can reach the agent card:

```bash
curl https://<a2a-url>/.well-known/agent-card.json | python -m json.tool
```

### Security checklist before opening tunnels (SEC-05)

- [ ] `VIGIL_API_KEY` is set and non-empty
- [ ] HAPI is on `127.0.0.1:8080` — verify: `ss -tlnp | grep 8080` shows `127.0.0.1`
- [ ] ngrok auth token is from your own account (prevents free-tier URL hijacking)
- [ ] No `.env` file with secrets visible in any terminal tab being recorded

---

## Option B — Fly.io (persistent public URL)

Deploy to Fly.io for a stable `*.fly.dev` URL that survives restarts.
All three Python services share the same Docker image; HAPI runs as an
internal-only Fly app (no public route).

### Prerequisites

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Authenticate
fly auth login
```

### One-time setup

```bash
# 1. Create Fly apps (run once)
fly apps create vigil-mcp
fly apps create vigil-a2a
fly apps create vigil-api
fly apps create vigil-hapi          # internal only

# 2. Create managed Postgres for HAPI
fly postgres create --name vigil-hapi-db --region sin --vm-size shared-cpu-1x
fly postgres attach vigil-hapi-db --app vigil-hapi

# 3. Set secrets (replace values)
export VIGIL_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

fly secrets set --app vigil-mcp  VIGIL_API_KEY="$VIGIL_API_KEY" GROQ_API_KEY="<key>"
fly secrets set --app vigil-a2a  VIGIL_API_KEY="$VIGIL_API_KEY"
fly secrets set --app vigil-api  VIGIL_API_KEY="$VIGIL_API_KEY" GROQ_API_KEY="<key>"
```

### Deploy

```bash
# HAPI first (other services depend on it)
fly deploy --config deploy/fly.hapi.toml --app vigil-hapi

# Python services (can deploy in parallel)
fly deploy --config deploy/fly.mcp.toml --app vigil-mcp &
fly deploy --config deploy/fly.a2a.toml --app vigil-a2a &
fly deploy --config deploy/fly.api.toml --app vigil-api &
wait

echo "MCP tools:  https://vigil-mcp.fly.dev/mcp"
echo "AgentCard:  https://vigil-a2a.fly.dev/.well-known/agent-card.json"
echo "API health: https://vigil-api.fly.dev/api/health"
```

### Seed HAPI on Fly.io

```bash
# SSH into the HAPI VM and run the seed script via the proxy
fly ssh console --app vigil-api

# Inside the container:
python data/seed_hapi.py --fhir-base http://vigil-hapi.internal:8080/fhir --src data/patients
exit
```

### Update Vercel with Fly.io URLs

```bash
vercel env add NEXT_PUBLIC_BACKEND_URL  https://vigil-api.fly.dev
vercel env add NEXT_PUBLIC_MCP_URL      https://vigil-mcp.fly.dev
vercel env add NEXT_PUBLIC_A2A_URL      https://vigil-a2a.fly.dev
```

### Verify

```bash
# MCP tool/list
curl -X POST https://vigil-mcp.fly.dev/mcp \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $VIGIL_API_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# AgentCard
curl https://vigil-a2a.fly.dev/.well-known/agent-card.json | python -m json.tool

# API health
curl https://vigil-api.fly.dev/api/health
```

---

## Option C — Railway

Simpler GUI-driven alternative to Fly.io. Uses the same `Dockerfile`.

### Deploy via Railway CLI

```bash
# Install railway CLI
npm install -g @railway/cli
railway login

# Create a new project
railway init

# Add three services (MCP, A2A, API) from the same repo
# In Railway dashboard: New Service → GitHub Repo → set SERVICE env var per service

# Environment variables to set per service in Railway dashboard:
# - SERVICE=mcp|a2a|api
# - VIGIL_API_KEY=<generated>
# - GROQ_API_KEY or ANTHROPIC_API_KEY
# - FHIR_BASE_URL=<railway private URL for HAPI service>
```

Railway generates a private URL for internal service communication (similar
to Fly.io's `.internal` DNS). Set `FHIR_BASE_URL` to the Railway private URL
for your HAPI service.

**Note on HAPI on Railway:** Deploy HAPI as a separate Railway service from
the `hapiproject/hapi:v7.2.0` Docker image. Add a Railway Postgres plugin for
the database. Set the Railway internal URL as `FHIR_BASE_URL` in the Python
services — this keeps HAPI off the public internet.

---

## Option D — Google Cloud Platform (Cloud Run)

Deploy all four services to GCP Cloud Run using the GCP free-trial credit
($300). Scales to zero when idle — effectively $0/month post-demo.

Configs live under `deploy/gcp/`:

- `cloud-run-mcp.yaml` — MCP server, public
- `cloud-run-a2a.yaml` — A2A agent + AgentCard, public
- `cloud-run-api.yaml` — FastAPI proxy, public
- `cloud-run-hapi.yaml` — HAPI FHIR, **ingress=internal only (SEC-10)**
- `cloudbuild.yaml` — builds the Dockerfile once and pushes to Artifact Registry
- `README.md` — full step-by-step (enable APIs, create VPC connector, Cloud SQL
  for HAPI, Secret Manager, deploy, seed, point Vercel at the new URLs)

See [`deploy/gcp/README.md`](../deploy/gcp/README.md) for the full runbook.

Summary of ingress policy on GCP:

```
Prompt Opinion runtime ──► https://vigil-mcp-*.a.run.app/mcp         (public)
Prompt Opinion runtime ──► https://vigil-a2a-*.a.run.app/a2a         (public)
Next.js (Vercel)        ──► https://vigil-api-*.a.run.app/api/*      (public)
vigil-mcp / vigil-a2a   ──► https://vigil-hapi-*.a.run.app/fhir      (internal via VPC connector)
vigil-api (approve)     ──► https://vigil-hapi-*.a.run.app/fhir      (internal via VPC connector)
vigil-hapi              ──► Cloud SQL (postgres, private IP)
```

HAPI satisfies SEC-10 via `run.googleapis.com/ingress: internal` — the
`*.a.run.app` URL is unreachable from the public internet; only services
on the shared VPC connector can invoke it.

Options B (GKE Autopilot) and C (single GCE VM) are documented briefly at
the bottom of `deploy/gcp/README.md` as fallbacks if Cloud Run hits a limit.

---

## Option E — Render.com (free, fixture mode) — **recommended for free hosting**

All four services on Render's free plan using a lightweight FHIR fixture
server in place of HAPI. Zero credit card, permanent `*.onrender.com` URLs,
fits in 512 MB per service. Trade-off is read-only FHIR (the fixture does
not persist writes), which is fine for judging.

Configs live under `deploy/render/`:

- [`render.yaml`](../render.yaml) at the repo root — Blueprint for all 4 services.
- [`deploy/render/README.md`](../deploy/render/README.md) — full runbook: Blueprint vs dashboard deploy, UptimeRobot keep-alive, Vercel frontend, free-tier math.

Service map on Render:

| Service | Render URL | Role |
|---|---|---|
| `vigil-fhir` | `https://vigil-fhir-*.onrender.com` | Fixture FHIR store (HAPI replacement) |
| `vigil-mcp`  | `https://vigil-mcp-*.onrender.com`  | MCP tools — PO calls this |
| `vigil-a2a`  | `https://vigil-a2a-*.onrender.com`  | AgentCard + A2A JSON-RPC |
| `vigil-api`  | `https://vigil-api-*.onrender.com`  | FastAPI proxy — dashboard backend |

Key free-tier constraints (see `deploy/render/README.md` for the full
breakdown):

- **750 instance-hours/month per workspace**, shared across all free
  services — cannot keep 4 services warm 24/7 for an entire month on free.
  Recommended posture: deploy now, enable UptimeRobot keep-alive on
  2026-05-07 through submission (2026-05-11), then pause.
- Services sleep after 15 min idle; cold start is ~60 s. UptimeRobot (free)
  keeps them warm during the demo window.
- Frontend deploys to Vercel, not Render (Vercel is a better Next.js host).

---

## Updating the tunnel/public URL without a Vercel redeploy

Vercel Preview and Production environments both support runtime env var
updates that take effect without a redeploy (server components fetch env
vars at request time):

```bash
# Update to new tunnel URL
vercel env rm NEXT_PUBLIC_BACKEND_URL production
vercel env add NEXT_PUBLIC_BACKEND_URL https://<new-ngrok-url>

# For client-side vars (NEXT_PUBLIC_*), a redeploy IS needed unless you
# use a runtime config endpoint. The backend URL is only used server-side
# in route handlers (frontend/app/api/mcp/), so no redeploy is needed.
```

If you need zero-redeploy URL rotation during a live demo, store the URL in
a KV store or environment variable fetched at runtime rather than as a
`NEXT_PUBLIC_*` build-time constant.

---

## Architecture diagram (deployed)

```
Prompt Opinion runtime
        │  SHARP headers
        ▼
https://vigil-mcp.fly.dev/mcp          ← MCP server (public)
        │  FHIR requests
        ▼
http://vigil-hapi.internal:8080/fhir   ← HAPI (private network only)

https://vigil-a2a.fly.dev/a2a          ← A2A agent (public)
        │  MCP calls
        ▼
http://vigil-mcp.internal:7001/mcp     ← MCP (private)

https://vigil-api.fly.dev              ← FastAPI proxy (public)
        │  FHIR write (approve only)
        ▼
http://vigil-hapi.internal:8080/fhir   ← HAPI (private)

Next.js (Vercel) → vigil-api.fly.dev  ← dashboard API
```

---

## Security notes

| Control | Where enforced |
|---|---|
| HAPI never publicly routed | No `[[services]]` in `fly.hapi.toml`; bound to `127.0.0.1` in local docker-compose |
| API key on all requests | `VIGIL_API_KEY` middleware in FastAPI proxy + MCP server middleware |
| Tunnel scope | Only port 8000/7001/9000 tunneled; 8080 never |
| No secrets in repo | `.gitignore` covers `.env*`; secrets injected via `fly secrets set` |
| CORS restricted | `CORS_ORIGINS` env var — not wildcard |

See `docs/SECURITY_REVIEW.md` SEC-05, SEC-10 for full rationale.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `AgentCard` 404 | Ensure `A2A_PUBLIC_URL` env var is set to the public URL before deploy |
| MCP `tool/list` returns 401 | Set `X-API-Key` header matching `VIGIL_API_KEY` |
| HAPI not reachable from Python services | Check private networking: `fly ssh console --app vigil-mcp` then `curl http://vigil-hapi.internal:8080/fhir/metadata` |
| ngrok tunnel drops | re-run `./scripts/tunnel.sh`; update Vercel env with new URL |
| Demo recording shows API key | Ensure terminal with `.env` is not in OBS capture area (SEC-12) |
