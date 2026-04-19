# Development Guide

> Everything a new contributor needs to go from `git clone` to a running Vigil stack. Self-contained — no other docs required to get started.

---

## 1. Prerequisites

| Tool | Version | Install |
|---|---|---|
| **Docker + Docker Compose** | v24+ / v2+ | [docs.docker.com](https://docs.docker.com/get-docker/) |
| **Python** | 3.11+ | [python.org](https://www.python.org/downloads/) |
| **uv** (Python package manager) | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Node.js** | 20+ | [nodejs.org](https://nodejs.org/) |
| **pnpm** | 9+ | `npm install -g pnpm` |

**Tested on:** macOS (ARM/Intel), Ubuntu 22.04, Windows 11 via WSL2.

> **WSL2 users:** Make sure Docker Desktop has the WSL2 integration enabled for your distro. Check with `docker ps` from your WSL shell — if it errors, open Docker Desktop > Settings > Resources > WSL Integration.

---

## 2. Clone and initial setup

```bash
git clone https://github.com/RaymonddC/Vigil.git
cd Vigil
```

### 2.1 Backend dependencies

```bash
uv sync --all-extras
```

This installs all Python dependencies including dev tools (pytest, ruff, mypy) and all LLM provider extras (ollama, groq, anthropic). The lockfile (`uv.lock`) ensures reproducible builds.

### 2.2 Frontend dependencies

```bash
cd frontend && pnpm install && cd ..
```

### 2.3 Environment variables

```bash
cp .env.example .env
```

Edit `.env` — key variables:

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` / `groq` / `claude` / `stub` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Only when `LLM_PROVIDER=ollama` |
| `OLLAMA_MODEL` | `qwen2.5:7b-instruct` | Only when `LLM_PROVIDER=ollama` |
| `GROQ_API_KEY` | (empty) | Get at [console.groq.com](https://console.groq.com) |
| `ANTHROPIC_API_KEY` | (empty) | Get at [console.anthropic.com](https://console.anthropic.com) |
| `FHIR_BASE_URL` | `http://localhost:8080/fhir` | Overridden by SHARP headers in production |
| `POLL_INTERVAL_SEC` | `900` | Agent polling: 900 = 15 min, 30 = fast demo |
| `FHIR_BACKEND` | `hapi` | Use `hapi` for live FHIR |
| `VIGIL_API_KEY` | (empty) | Optional: if set, all services require X-API-Key |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |

The frontend `.env.local` is already configured:

```bash
# frontend/.env.local — already present, no changes needed
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

### 2.4 LLM setup (choose one)

**Option A: Ollama (recommended for dev — free, no API key)**

```bash
# Install Ollama: https://ollama.com/download
ollama pull qwen2.5:7b-instruct
ollama serve  # leave running in a terminal
```

**Option B: Stub mode (no LLM needed at all)**

```bash
# In .env:
LLM_PROVIDER=stub
# Tools return fixed responses. Good for testing the pipeline without LLM latency.
```

**Option C: Groq or Claude (cloud)**

```bash
# In .env, set the provider and API key:
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
# or:
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 3. Start services

### Option A: One-command startup

```bash
make demo
```

This runs `scripts/demo.sh`, which starts all services in order with health checks. Takes ~1–2 minutes on a warm Docker pull. When you see `=== All services running ===`, everything is ready.

To stop everything:

```bash
make demo-stop
```

### Option B: Manual startup (6 terminals)

If you want to see each service's output, start them in separate terminals:

**Terminal 1 — HAPI FHIR (Docker)**

```bash
make up
# Waits for HAPI FHIR to be healthy at http://localhost:8080/fhir
```

HAPI takes 30–60 seconds to start. Wait for the "HAPI FHIR ready" message.

**Terminal 2 — Seed synthetic patients**

```bash
make seed
```

Loads 10 synthetic patients (PT-001 through PT-010) with 6 timepoints each across 4 trajectories: stable, deteriorating, sepsis onset, and postpartum hemorrhage.

**Terminal 3 — MCP server (:7001)**

```bash
make mcp
```

Starts the FastMCP server with 4 clinical tools on `http://localhost:7001`.

**Terminal 4 — A2A agent (:9000)**

```bash
make agent
```

Starts the Postop Sentinel agent. Agent card at `http://localhost:9000/.well-known/agent-card.json`.

**Terminal 5 — FastAPI proxy (:8000)**

```bash
make proxy
```

The proxy bridges the frontend to HAPI FHIR and the agent. Handles the approve endpoint that writes FHIR Communication + AuditEvent resources.

**Terminal 6 — Next.js frontend (:3000)**

```bash
make frontend
```

Opens the clinician dashboard at `http://localhost:3000`.

---

## 4. Verify everything works

Open [http://localhost:3000](http://localhost:3000) in your browser (Chrome recommended, 110% zoom for best demo legibility).

### Checklist

| Step | What to check | Expected |
|---|---|---|
| Landing page | `http://localhost:3000` | Hero stats (4.2M, 260K), 4 feature cards |
| Patient roster | `/patients` | 10 rows sorted by risk, filter pills (All / High+ / Triggered) |
| Stable patient | Click PT-001 | Green "Normal" RiskBadge, flat vitals chart, no alerts |
| Deteriorating patient | Click PT-007 | Red/amber trend in vitals chart, high risk badge, qSOFA score |
| Sepsis patient | Click PT-009 | "Critical" badge, SBAR panel with S/B/A/R sections |
| Agent timeline | `/timeline` | Tool-call events (SCREENING, RISK_SCORING, etc.), "Tick Now" button |
| Review queue | `/alerts` | SBAR alert cards with "Approve & send RRT" button |
| System status | `/settings` | LLM provider, FHIR health (green), SHARP headers |

### Trigger a manual tick

The agent polls on a timer, but you can trigger a screening cycle immediately:

```bash
# From the UI: click "Tick Now" on the Timeline page
# Or via curl:
curl -X POST http://localhost:8000/api/agent/tick
```

### Test the approve flow

1. Go to `/alerts` (Review Queue)
2. Click "Approve & send RRT" on any alert card
3. A Sonner toast should confirm: "Communication {id} written — audit {id}"
4. Check HAPI FHIR for the new resources:
   ```bash
   curl http://localhost:8080/fhir/Communication?_sort=-_lastUpdated&_count=1 | python -m json.tool
   ```

---

## 5. Run tests

### Backend tests (pytest)

```bash
uv run pytest               # 312 tests
uv run pytest -v --tb=short # verbose with short tracebacks
uv run pytest -x            # stop on first failure
uv run pytest -k "sepsis"   # run only sepsis-related tests
```

Key test files: `test_criteria.py` (MEWT/qSOFA/SIRS/KDIGO rules), `test_sharp_compliance.py` (39 SHARP tests), `test_b2_*`/`test_b3_*`/`test_flag_*`/`test_generate_*` (per-tool), `tests/integration/test_mcp_tools.py` (full chain).

### Linting

```bash
make lint
# Runs:
#   uv run ruff check backend/ tests/
#   uv run mypy backend/
```

### E2E tests (Playwright)

```bash
# First time — install browsers:
cd frontend && pnpm exec playwright install --with-deps chromium && cd ..

# Run (requires make demo to be running):
make e2e
```

### All quality checks

```bash
make ci   # runs lint + test
```

---

## 6. Troubleshooting

### HAPI FHIR won't start

```bash
# Check Docker is running:
docker ps

# Check container logs:
docker compose logs hapi

# Common issues:
# - WSL2: Docker Desktop WSL integration not enabled
# - Port 8080 already in use: lsof -i :8080
# - First cold pull of hapiproject/hapi:v7.2.0 takes ~2 min
```

### LLM errors / "provider not configured"

```bash
# Option 1: Use stub mode (no LLM needed):
echo "LLM_PROVIDER=stub" >> .env

# Option 2: Install and run Ollama:
ollama pull qwen2.5:7b-instruct
ollama serve
# Verify: curl http://localhost:11434/api/tags

# Option 3: Use Groq (fast, free tier):
# Get key at https://console.groq.com
echo "LLM_PROVIDER=groq" >> .env
echo "GROQ_API_KEY=gsk_..." >> .env
```

### Port conflicts

```bash
# Check what's using the ports:
lsof -i :7001 -i :8000 -i :8080 -i :9000 -i :3000

# Kill a specific port:
kill $(lsof -ti :8000)
```

### Frontend TypeScript errors

```bash
cd frontend
pnpm install          # reinstall deps
pnpm tsc --noEmit     # check for type errors without building
pnpm dev              # restart dev server
```

### Seed data not showing up

```bash
make seed
# Verify: curl http://localhost:8080/fhir/Patient?_count=0 | python -m json.tool | grep total
# Should show: "total": 10
```

### "Backend unavailable" in the dashboard

The frontend talks to the FastAPI proxy on `:8000`. Make sure it's running: `make proxy` then verify with `curl http://localhost:8000/api/health`.

---

## 7. Architecture overview

```
                    ┌─────────────────────────┐
                    │  Next.js 15 Dashboard   │  :3000
                    │  (shadcn + Recharts)    │
                    └───────────┬─────────────┘
                                │ /api/*
                    ┌───────────▼─────────────┐
                    │  FastAPI Proxy          │  :8000
                    │  (FHIR reads + approve) │
                    └──┬────────────────┬─────┘
                       │                │
          ┌────────────▼──┐    ┌───────▼──────────┐
          │ HAPI FHIR R4  │    │ A2A Sentinel     │  :9000
          │ + PostgreSQL  │    │ (7-state machine)│
          │               │    └───────┬──────────┘
          │  :8080        │            │ MCP tool calls
          │               │    ┌───────▼──────────┐
          └───────────────┘    │ MCP Server       │  :7001
                               │ (4 clinical      │
                               │  tools)          │
                               └──────────────────┘
```

**Service ports:**

| Service | Port | Purpose |
|---|---|---|
| HAPI FHIR | `:8080` | FHIR R4 server (Docker, PostgreSQL backend) |
| MCP Server | `:7001` | 4 clinical tools via streamable HTTP |
| A2A Agent | `:9000` | Postop Sentinel state machine |
| FastAPI Proxy | `:8000` | Bridges frontend to FHIR + agent |
| Next.js | `:3000` | Clinician dashboard |

For the full architecture — component diagram, sequence diagrams, data flow narratives, and tech stack rationale — see [`docs/ARCHITECTURE.md`](ARCHITECTURE.md).

---

## 8. Useful commands

| Command | What it does |
|---|---|
| `make demo` | Start everything with health checks |
| `make demo-stop` | Stop all background services |
| `make demo-warmup` | Pre-flight: reseed, ping LLM, tick agent |
| `make up` / `make down` | Docker (HAPI + postgres) |
| `make seed` | Load synthetic patients |
| `make mcp` | MCP server on :7001 |
| `make agent` | A2A agent on :9000 |
| `make proxy` | FastAPI proxy on :8000 |
| `make frontend` | Next.js on :3000 |
| `make test` | 312 pytest tests |
| `make lint` | ruff + mypy |
| `make ci` | lint + test |
| `make e2e` | Playwright (requires demo running) |

```bash
# Inspect FHIR data
curl http://localhost:8080/fhir/Patient | python -m json.tool
curl http://localhost:8080/fhir/Observation?patient=PT-007&_sort=-date&_count=3 | python -m json.tool

# Inspect agent
curl http://localhost:9000/.well-known/agent-card.json | python -m json.tool
curl -X POST http://localhost:8000/api/agent/tick
```

---

## 9. Commit conventions

```bash
git commit -m "feat(B3): add qSOFA trend scoring"
#                ^type ^scope   ^description
```

**Types:** `feat`, `fix`, `docs`, `test`, `refactor`, `chore`

**Scopes:**
- `B1`–`B8` — backend tasks
- `FE1`–`FE6` — frontend tasks
- `I1`–`I3` — integration tasks
- `P1`–`P4` — documentation / submission tasks

See the full task map in [`docs/BUILD_PLAN.md`](BUILD_PLAN.md).
