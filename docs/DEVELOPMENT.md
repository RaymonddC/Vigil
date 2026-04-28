# Development Guide

> Long-form companion to the `README.md` Quickstart. Read the README first to get a stack running; come back here when you need manual control, deeper troubleshooting, or the full test / lint / e2e flow.

---

## 1. Prerequisites (full matrix)

The README lists the bare minimum. If you plan to do real development (backend changes, frontend work, e2e tests), you'll want:

| Tool | Version | Notes / install |
|---|---|---|
| **Docker + Docker Compose** | v24+ / v2+ | [docs.docker.com](https://docs.docker.com/get-docker/) |
| **Python** | 3.11+ | Managed by `uv`; you don't need a separate `python` install |
| **uv** | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Node.js** | 20+ | For the dashboard and Playwright |
| **pnpm** | 9+ | `npm install -g pnpm` |
| **make** | any | Standard target runner |
| **jq** | any | Pretty-printing JSON in smoke tests; optional |
| **Ollama** | latest | Optional — only when `LLM_PROVIDER=ollama` |
| **cloudflared** or **ngrok** | latest | Optional — only when exposing the agent to Prompt Opinion's launchpad |

**Tested on:** macOS (ARM/Intel), Ubuntu 22.04, Windows 11 via WSL2.

> **WSL2 users:** open Docker Desktop > Settings > Resources > WSL Integration and enable your distro. Verify with `docker ps` from your WSL shell.

---

## 2. Clone, sync, configure

```bash
git clone https://github.com/RaymonddC/Vigil.git
cd Vigil
```

### 2.1 Backend dependencies

```bash
uv sync
```

This installs runtime + `[dev]` extras (pytest, ruff, mypy). LLM-provider extras (`ollama`, `groq`, `anthropic`) are opt-in via `--extra`:

```bash
uv sync --extra ollama          # only if you'll run a local Ollama
uv sync --extra groq            # only if LLM_PROVIDER=groq
uv sync --extra anthropic       # only if LLM_PROVIDER=claude
```

Gemini and the stub provider need no extras — Gemini uses raw `httpx` to keep the dep tree light.

### 2.2 Frontend dependencies

```bash
cd frontend && pnpm install && cd ..
```

Skip if you only care about the agent submission path.

### 2.3 Environment variables

```bash
cp .env.example .env
```

Key knobs:

| Variable | Default | Notes |
|---|---|---|
| `VIGIL_API_KEY` | — | **Required** for compose; any non-empty string in dev. The middleware enforces it on the `mcp`, `a2a`, and `api` services. If unset, enforcement is disabled and a warning is logged. |
| `LLM_PROVIDER` | `ollama` | One of `ollama` / `groq` / `claude` / `gemini` / `stub`. `stub` returns canned text — perfect for CI and pipeline-only debugging. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Only when `LLM_PROVIDER=ollama` |
| `OLLAMA_MODEL` | `qwen2.5:7b-instruct` | Only when `LLM_PROVIDER=ollama` |
| `GEMINI_API_KEY` | — | Get a free key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey). Same model PO uses by default. |
| `GEMINI_MODEL` | `gemini-2.5-flash-lite` | |
| `GROQ_API_KEY` | — | [console.groq.com](https://console.groq.com) |
| `ANTHROPIC_API_KEY` | — | [console.anthropic.com](https://console.anthropic.com) |
| `FHIR_BASE_URL` | `http://localhost:8080/fhir` | Overridden by SHARP headers when called via Prompt Opinion |
| `VIGIL_SYNTHETIC_FALLBACK` | `false` | When `true`, MCP tools fall back to bundled PT-007 data if the upstream FHIR server 401/403s. Useful for demo recordings; keep `false` in any production-shaped deploy. |
| `POLL_INTERVAL_SEC` | `900` | Sentinel polling: 900 = 15 min. Set `30` for fast demo, `0` to disable autonomous polling (the Option 3 deploy default). |
| `FHIR_BACKEND` | `hapi` | Use `hapi` for live FHIR, `fixture` for the in-memory synthetic fallback. |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated. Only relevant when running compose with a `SITE_DOMAIN`. |
| `A2A_PUBLIC_URL` | (derived) | Override the URL the AgentCard advertises (e.g. when you've fronted the agent with a tunnel). |

The frontend also reads `frontend/.env.local`:

```bash
# frontend/.env.local — already present
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

### 2.4 LLM setup (choose one)

**A. Stub mode — no LLM at all.** Fastest path; tools return canned templates. Good enough to verify dispatch and the rule engines.

```bash
# .env
LLM_PROVIDER=stub
```

**B. Gemini — easiest free cloud option.** Same provider Prompt Opinion uses by default.

```bash
# .env
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
```

**C. Ollama — fully offline.**

```bash
ollama pull qwen2.5:7b-instruct
ollama serve                       # leave running

# .env
LLM_PROVIDER=ollama
```

**D. Groq / Claude.** Set `LLM_PROVIDER=groq` (or `claude`) and the matching API key in `.env`.

---

## 3. Start services

### Option A: One command (`make demo`)

The default path. Starts HAPI, seeds patients, then launches MCP / A2A / proxy / frontend in the background with health checks:

```bash
make demo                          # ~1–2 minutes on a warm Docker pull
make demo-stop && make down        # full teardown (Docker + background processes)
```

Logs live in `.demo-logs/`; PIDs in `.demo-pids/`.

### Option B: Manual six-terminal startup

When you want each service's stdout in its own pane:

| Terminal | Command | What it runs |
|---|---|---|
| 1 | `make up` | HAPI FHIR + Postgres on `:8080`, waits for the metadata endpoint |
| 2 | `make seed` | 10 synthetic patients (PT-001..PT-010) into HAPI; one-shot |
| 3 | `make mcp` | FastMCP server on `:7001` |
| 4 | `make agent` | A2A agent on `:9000`, AgentCard at `/.well-known/agent-card.json` |
| 5 | `make proxy` | FastAPI proxy on `:8000` (dashboard backend + approve endpoint) |
| 6 | `make frontend` | Next.js dev server on `:3000` |

> **Important:** `make mcp` / `make agent` / `make proxy` do **not** auto-source `.env`. Export the env vars you need in each shell, or set them inline:
>
> ```bash
> LLM_PROVIDER=gemini GEMINI_API_KEY=... VIGIL_API_KEY=local-dev-key-anything make agent
> ```
>
> The full `make demo` script does the same — its child processes inherit whatever's in the launching shell's environment.

### Option C: Docker compose

Closest to the production EC2 deploy. All four services + HAPI + Caddy in containers:

```bash
# Optional: set SITE_DOMAIN in .env if you want Caddy to issue a real cert
docker compose up -d --build
docker compose logs -f a2a         # follow the agent
docker compose down
```

Compose binds HAPI to `127.0.0.1:8080` only (SEC-10) — it's not reachable from outside the host. Public traffic goes through Caddy on `:80` / `:443`.

---

## 4. Verify everything works

### Smoke tests

```bash
# Agent card
curl -s http://localhost:9000/.well-known/agent-card.json | jq .name
#  → "Vigil — Postop & Postpartum Sentinel"

# JSON-RPC SendMessage round-trip (the same shape Prompt Opinion uses)
make smoke
make smoke SKILL=draft_sbar PATIENT=PT-007
make smoke SKILL=check_sepsis

# Health endpoints
curl http://localhost:7001/health       # MCP
curl http://localhost:8000/api/health   # FastAPI proxy
```

The live skill list (IDs, parameter shapes, FHIR-context extension) is advertised on the AgentCard — don't hardcode it in test scripts; fetch it.

### Dashboard checklist

Open <http://localhost:3000> (Chrome at 110% zoom for demo legibility):

| Step | What to check | Expected |
|---|---|---|
| Landing | `/` | Hero stats and feature cards render |
| Roster | `/patients` | 10 rows sorted by deterioration risk; All / High+ / Triggered filters work |
| Stable patient | Click PT-001 | Green badge, flat vitals chart, no alerts |
| Deteriorating | Click PT-007 | Amber/red trend, qSOFA score visible |
| Sepsis | Click PT-009 | Critical badge, SBAR S/B/A/R sections render |
| Timeline | `/timeline` | Tool-call events, "Tick Now" button |
| Review queue | `/alerts` | SBAR alert cards with "Approve & send RRT" |
| System status | `/settings` | LLM provider, FHIR health, SHARP headers |

### Trigger a manual sentinel tick

```bash
curl -X POST http://localhost:8000/api/agent/tick
# Or click "Tick Now" on /timeline
```

### Test the approve flow

1. `/alerts` → "Approve & send RRT" on any card.
2. Sonner toast confirms `Communication {id} written — audit {id}`.
3. Verify against HAPI:
   ```bash
   curl -s "http://localhost:8080/fhir/Communication?_sort=-_lastUpdated&_count=1" | jq .
   ```

The proxy's approve endpoint is the **only** code path that writes back to FHIR — the agent never writes autonomously.

---

## 5. Tests, lint, e2e

```bash
make test                          # full pytest (asyncio_mode=auto)
make lint                          # ruff check backend/ tests/
make typecheck                     # mypy — opt-in; known FastMCP Context false positives
make ci                            # lint + test
```

Useful filters:

```bash
uv run pytest -k "sepsis" -v
uv run pytest tests/integration/ -v
uv run pytest tests/test_sharp_compliance.py::test_extract_metadata -v
uv run pytest -x                   # stop on first failure
uv run pytest --tb=short
```

### Playwright e2e

```bash
# First time — install browsers
cd frontend && pnpm exec playwright install --with-deps chromium && cd ..

# Requires `make demo` to be running first
make e2e
```

---

## 6. Exposing the agent to Prompt Opinion

Optional. Only needed when you want PO's hosted launchpad to chat with your local agent.

### Cloudflared (no signup)

```bash
# No-sudo install
curl -L --output ~/.local/bin/cloudflared \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x ~/.local/bin/cloudflared

export VIGIL_API_KEY=local-dev-key-anything
bash scripts/tunnel-cf.sh
```

The script tunnels `:8000` (proxy), `:7001` (MCP), and `:9000` (agent) and prints public `https://*.trycloudflare.com` URLs. HAPI (`:8080`) is never tunneled (SEC-10).

### ngrok

```bash
ngrok config add-authtoken <token>
export VIGIL_API_KEY=local-dev-key-anything
bash scripts/tunnel.sh
```

### After the tunnel is up

1. Restart the agent with `A2A_PUBLIC_URL=https://<a2a-tunnel-host>/a2a` so the AgentCard advertises the public URL.
2. Register that URL on [app.promptopinion.ai](https://app.promptopinion.ai). See `docs/PO_PUBLISHING_RESEARCH.md` and `docs/PROMPT_OPINION_INTEGRATION.md` for the current PO menu paths.

---

## 7. Troubleshooting

### HAPI FHIR won't start

```bash
docker ps                          # is Docker running?
docker compose logs hapi           # what's HAPI saying?
lsof -i :8080                      # port already in use?
```

WSL2 cold-pulls of `hapiproject/hapi:v7.2.0` take ~2 minutes the first time.

### LLM errors / "provider not configured"

Switch to stub mode for a no-LLM smoke:

```bash
echo "LLM_PROVIDER=stub" >> .env
```

Or check the matching key is set: `LLM_PROVIDER=gemini` needs `GEMINI_API_KEY`, `groq` needs `GROQ_API_KEY`, `claude` needs `ANTHROPIC_API_KEY`, `ollama` needs `ollama serve` running.

### Port conflicts

```bash
lsof -i :3000 -i :7001 -i :8000 -i :8080 -i :9000
kill $(lsof -ti :8000)             # nuke whatever's on :8000
```

### Frontend TypeScript errors

```bash
cd frontend
pnpm install
pnpm tsc --noEmit
pnpm dev
```

Pages that fetch from the backend during RSC render export `const dynamic = "force-dynamic"`. Don't strip those exports — `pnpm build` will hang on static prerendering otherwise.

### Seed data missing

```bash
make seed
curl -s "http://localhost:8080/fhir/Patient?_count=0" | jq '.total'   # expect 10
```

Patient JSON files use absolute timestamps. If HAPI was seeded long ago, MEWT's recent-window filter may report 0 observations — re-run `make seed` to refresh.

### "Backend unavailable" in the dashboard

The frontend talks to the FastAPI proxy on `:8000`. Make sure it's running: `make proxy`, then verify with `curl http://localhost:8000/api/health`.

### Agent returns "MCP tool was unreachable: HTTP 401"

The agent forwards `VIGIL_API_KEY` to MCP only if it's set in the agent's environment. If you've set `VIGIL_API_KEY` for MCP but not for the agent process, MCP will 401 every call. Either set it on both, or unset it on both for local dev.

---

## 8. Architecture (quick map)

```
                    Prompt Opinion launchpad
                              │
                       A2A JSON-RPC + SHARP
                              │
                              ▼
   Clinician ─HTTPS─► Next.js dashboard ─► FastAPI proxy ─► A2A agent (:9000)
                          (:3000)            (:8000)               │
                                                            MCP Streamable HTTP
                                                                   ▼
                                                           MCP server (:7001)
                                                                   │
                                                                   ▼
                                                            HAPI FHIR R4 (:8080)
```

| Service | Port | Purpose |
|---|---|---|
| HAPI FHIR | `:8080` | FHIR R4, Postgres-backed |
| MCP server | `:7001` | Clinical tools via streamable HTTP |
| A2A agent | `:9000` | Public submission surface; AgentCard at `/.well-known/agent-card.json` |
| FastAPI proxy | `:8000` | Dashboard backend + clinician approve write path |
| Next.js | `:3000` | Clinician dashboard |

Full architecture, sequence diagrams, and tech stack rationale: [`docs/ARCHITECTURE.md`](ARCHITECTURE.md).

---

## 9. Useful commands

| Command | What it does |
|---|---|
| `make demo` | Orchestrated startup with health checks |
| `make demo-stop` | Stop all background services |
| `make demo-warmup` | Reseed, ping LLM, tick agent, warm frontend routes |
| `make up` / `make down` | HAPI + Postgres only |
| `make seed` | Load synthetic patients |
| `make mcp` | MCP server on `:7001` |
| `make agent` | A2A agent on `:9000` |
| `make proxy` | FastAPI proxy on `:8000` |
| `make frontend` | Next.js dev server on `:3000` |
| `make smoke` | JSON-RPC SendMessage to the agent (knobs: `SKILL`, `PATIENT`, `AGENT`, `FHIR_URL`) |
| `make test` | pytest |
| `make lint` | ruff |
| `make typecheck` | mypy (opt-in) |
| `make ci` | lint + test |
| `make e2e` | Playwright (requires `make demo` running) |

```bash
# Inspect FHIR data
curl -s http://localhost:8080/fhir/Patient | jq .
curl -s "http://localhost:8080/fhir/Observation?patient=PT-007&_sort=-date&_count=3" | jq .

# Inspect agent
curl -s http://localhost:9000/.well-known/agent-card.json | jq .
curl -X POST http://localhost:8000/api/agent/tick
```

---

## 10. Commit conventions

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

Full task map: [`docs/BUILD_PLAN.md`](BUILD_PLAN.md).
