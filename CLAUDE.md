# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

Vigil is the submission for the **Agents Assemble — Healthcare AI Endgame** hackathon (Devpost, deadline 2026-05-11). It registers on the Prompt Opinion Marketplace as **Path B, Option 3 — Independent A2A Agent**: a public, externally hosted A2A agent that any A2A-aware system on the platform can consult. The demo narrative lives in `docs/DEMO_SCRIPT.md`; when in conflict, `docs/PROJECT_BRIEF.md` wins.

Vigil ships two surfaces on the same backend. The **A2A agent** in `backend/a2a_agent/` (plus the MCP tools it calls in `backend/mcp_server/`) is the hackathon submission — it's what Prompt Opinion's launchpad chat invokes per patient. The **clinician dashboard** in `frontend/` is a custom client built on top of the same backend; it demonstrates a production-deployed UX for the same agent and serves as a portfolio surface beyond what the marketplace launchpad offers. Same code, same rule engine, same FHIR client — two front doors. When editing, preserve this invariant: anything the dashboard does must remain expressible as a call into the A2A agent or the MCP tools, not as dashboard-only logic.

## Commands

All backend commands go through `uv` (never plain `python` or `pip`). All frontend commands go through `pnpm`.

```bash
# Infrastructure (HAPI FHIR R4 v7.2.0 + Postgres on :8080)
make up              # start HAPI, wait for /fhir/metadata to return 200
make down            # stop and remove containers
make seed            # seed synthetic patients via data/seed_hapi.py

# Services (each in its own terminal for dev)
make mcp             # MCP server on :7001 (uv run python -m backend.mcp_server.server)
make agent           # A2A agent on :9000
make proxy           # FastAPI proxy on :8000 (uvicorn --reload)
make frontend        # Next.js dev server on :3000

# Orchestrated
make demo            # full stack via scripts/demo.sh, with health checks
make demo-warmup     # reseed + ping LLM + tick agent + warm frontend routes
make demo-stop       # tear everything down

# Quality
make test            # pytest (asyncio_mode=auto)
make lint            # ruff check backend/ tests/
make typecheck       # mypy (opt-in; has known FastMCP Context false positives)
make e2e             # Playwright, requires `make demo` already running

# Single test
uv run pytest tests/test_flag_sepsis_onset.py::test_abx_window_filter -v
uv run pytest -k "sepsis" -v             # by keyword
uv run pytest tests/integration/ -v      # one directory
```

`uv sync` installs with `[dev]` extras by default. LLM-provider extras (`ollama`, `groq`, `anthropic`) are opt-in per `pyproject.toml`.

`LLM_PROVIDER` is swappable at runtime: `ollama` (dev default) | `groq` | `claude` (for demo recording) | `stub` (CI). Set `LLM_PROVIDER=claude` before recording video.

## Architecture

### Three entry surfaces, one Python package

The backend ships as a single `vigil-backend` Docker image that dispatches on the `SERVICE` env var (see the `CMD` in `Dockerfile`):

- `SERVICE=a2a` → `backend.a2a_agent.app:app` on `:9000` — **the public hackathon submission.** A2A JSON-RPC agent with AgentCard at `/.well-known/agent-card.json`. Prompt Opinion's launchpad and any other A2A client call this directly.
- `SERVICE=mcp` → `backend.mcp_server.server:app` on `:7001` — FastMCP streamable-HTTP server exposing the 4 clinical tools. Called *internally* by the A2A agent; not surfaced for direct chat use in the Option 3 deployment.
- `SERVICE=api` → `backend.api.main:app` on `:8000` — FastAPI proxy for the dashboard (FHIR reads + clinician approve). Powers the **portfolio surface** (`frontend/`); not part of the marketplace submission's request path.
- `SERVICE=fixture` → `backend.fhir_fixture.main:app` on `:8080` — synthetic-FHIR fallback, not used in the canonical demo path.

`docker-compose.yml` starts four copies of this image plus HAPI + Postgres + Caddy. The image requires `README.md` in the build context — `uv run` at container start re-validates the workspace via hatchling, which opens the readme listed in `pyproject.toml`.

### The SHARP header bridge (Prompt Opinion compliance)

Prompt Opinion injects three HTTP headers on every call: `x-fhir-server-url`, `x-fhir-access-token`, `x-patient-id`. This is how FHIR context flows without the frontend or the agent having to embed credentials:

- **MCP path:** headers ride on the HTTP request; tools read them via `ctx.request_context.request.headers` (see `backend/mcp_server/middleware.py` + `context.py`).
- **A2A path:** context arrives inside the JSON-RPC body as `message.metadata["…/fhir-context"]`. `backend/a2a_agent/fhir_hook.py::extract_fhir_from_metadata` pulls it out; `fhir_metadata_to_sharp_headers` converts it back to the 3 SHARP headers when the agent calls MCP tools downstream.
- **Frontend proxy:** never handles SHARP headers. Uses the server-side `FHIR_BASE_URL` for all HAPI reads so bearer tokens never reach the browser.

SSRF protection (`SEC-01`) validates `x-fhir-server-url` against `ALLOWED_FHIR_HOSTS`. Bearer tokens are redacted in logs via `_redact_token()` (first 4 chars + `****`). Tests in `tests/test_sharp_compliance.py` + `test_sharp_middleware.py`.

### Deterministic rules first, LLM second

The 4 MCP tools (`backend/mcp_server/tools/`) all follow the same shape: a deterministic rule engine from `backend/criteria/` (MEWT, qSOFA, CDC ASE, KDIGO) produces the escalation decision; an LLM pass only layers patient-specific prose on top. **The LLM never decides whether to escalate.** `generate_escalation_note` is the only tool that invokes the LLM for anything beyond enrichment. Every tool I/O shape lives in `backend/schemas.py` (pydantic v2); `ToolStatus` is the common error envelope discriminator.

### Human-in-the-loop write path

The A2A Postop Sentinel (`backend/a2a_agent/sentinel.py`) runs a 7-state machine: `IDLE → POLLING → SCREENING → RISK_SCORING → SEPSIS_CHECK → ESCALATING → AWAITING_REVIEW`. It **never writes to FHIR**. Triggered alerts land in a SQLite review queue (`backend/api/review_queue.py`) that:

- atomically supersedes prior alerts for the same patient on enqueue
- uses `UPDATE ... WHERE status='in-progress' RETURNING *` in `claim_alert_for_writing` to race-safely claim an alert exactly once

The clinician clicks Approve → the FastAPI proxy (`backend/api/main.py` + `routes/patients.py`) is the **only** code path that writes `Communication` + `AuditEvent` to HAPI. Before the Communication POST, `_ensure_vigil_referenced_resources` idempotently PUTs the Vigil `Device` and any referenced `PractitionerRole`, because HAPI-1094 rejects unresolved references. Kebab-case is forced on logical IDs (`charge_nurse → charge-nurse`) to avoid HAPI-0521. Compose sets `hapi.fhir.enforce_referential_integrity_on_write: false` as belt-and-braces.

### Same 4 tools, two wards

The postpartum cameo (PT-009) reuses the exact same 4 tools as the postop pipeline. No ward branching, no conditional logic — the only difference is the synthetic trajectory in `data/patients/`. Preserve this invariant when editing criteria or tool code; the demo's 2:00 moment depends on it.

## Frontend quirks (Next.js 16)

- Pages that fetch from the backend during render must export `const dynamic = "force-dynamic"` (see `app/patients/page.tsx`, `app/patients/[id]/page.tsx`, `app/settings/page.tsx`). Without it, `pnpm build` attempts static pre-rendering and hangs waiting for the backend.
- RSC fetches go direct to `BACKEND_URL` (internal docker network, e.g. `http://api:8000`). Client-side fetches go same-origin `/api/*` and are routed by Caddy to the `api` service.
- `frontend/lib/api.ts::buildServerHeaders` injects `X-API-Key` from `process.env.VIGIL_API_KEY` for server-side calls only.
- Next.js 16 reads `HOSTNAME` and `PORT` from env natively; don't pass them as `pnpm start -- --hostname ...` (next start treats the first positional as a project dir and fails).

## Deployment

The canonical production path is AWS EC2 `c7i-flex.large` running the full docker-compose stack behind Caddy with auto-TLS via Let's Encrypt (`deploy/aws/`). Only ports 80/443 are public; HAPI binds to `127.0.0.1:8080` on the host for SSH-forwarded debugging only. `.github/workflows/deploy.yml` SSHes to the EC2 on every push to `main` and runs `git pull --ff-only && docker compose up -d --build`. Required repo secrets: `EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY`. `deploy/render/` and `deploy/fly.*.toml` exist as alternate targets but aren't the canonical path.

## Conventions

- Commit scopes follow the `B1-B8 / FE1-FE6 / I1-I3 / P1-P4` taxonomy from the BUILD_PLAN (e.g. `feat(B3): ...`, `fix(FE2): ...`).
- Clinical claims cite `docs/CLINICAL_EVIDENCE.md`; never invent thresholds. The hemodynamic trend rule (SBP drop ≥10% AND HR rise ≥15% over 2h) is flagged as operational-not-validated — keep that caveat intact.
- `docs/DEFERRED_FINDINGS.md` tracks known issues that are deliberately not fixed before the deadline; check there before adding a new "todo".
