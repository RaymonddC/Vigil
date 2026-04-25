# Vigil

> A second pair of eyes on every post-op and postpartum bed.

Vigil is a clinician-supervised early-warning agent for post-operative and postpartum wards. It reads vitals and labs from a FHIR R4 server, screens them against published clinical standards (MEWT, qSOFA, CDC ASE, KDIGO), drafts an SBAR escalation note when something looks wrong, and waits for a human to approve before anything leaves the system. Deterministic rules decide whether to escalate; the LLM only writes the prose.

The same backend exposes itself as a public A2A agent on Prompt Opinion's marketplace and powers a production-deployed clinician dashboard. Both surfaces share the rule engine, the FHIR client, and the four MCP tools underneath. Synthetic patient data only — no real PHI is in the repo or the deployment.

## Two surfaces, one platform

Vigil ships as two complementary surfaces built on the same backend.

### 🤝 The agent — `backend/a2a_agent/`

**Submission for the [Agents Assemble — Healthcare AI Endgame](https://agents-assemble.devpost.com/) hackathon (Path B, Option 3 — Independent A2A Agent).**

Registered on [Prompt Opinion's](https://www.promptopinion.ai/) marketplace as an external A2A agent. Any A2A-aware system can consult it for vitals screening, deterioration risk scoring, sepsis recognition, and SBAR drafting. The agent reads FHIR context that Prompt Opinion injects via A2A message metadata, calls the internal MCP tool server for clinical reasoning, and returns chat-ready answers.

- **Agent card:** `https://<deploy-host>/.well-known/agent-card.json`
- **Skills:** `vigil.screen_vitals`, `vigil.score_risk`, `vigil.check_sepsis`, `vigil.draft_sbar`
- **Stack:** Python 3.11 · FastAPI · `a2a-sdk` · MCP (internal) · HAPI FHIR R4 · stub / Ollama / Claude / Groq LLM providers
- **Security:** `X-API-Key` middleware on the JSON-RPC entrypoint; agent card declares the API-key scheme so Prompt Opinion prompts for it on connection. SSRF allowlist on `x-fhir-server-url`. Bearer tokens redacted in logs.

The agent code lives in `backend/a2a_agent/` (state machine, skill router, FHIR-context bridge, MCP client). The four MCP tools it calls live in `backend/mcp_server/tools/`.

### 🩺 The dashboard — `frontend/`

A production-grade clinician UI built on top of the same backend. Roster sorted by deterioration risk, patient detail with a vitals chart, SBAR review-and-approve flow, agent timeline, and a system health page. Designed for nurses on a 12-hour shift watching 6–8 patients at a ward station, with a 10-inch tablet portrait fallback for hand-off rounds.

- **Stack:** Next.js 16 · React 19 · TypeScript · Tailwind v4 · shadcn/ui (Base UI primitives)
- **Design system:** `docs/design/` — full token set, light and dark mode, WCAG 2.2 AA target
- **Approve path:** the FastAPI proxy is the only code that writes to FHIR; the agent never writes autonomously

The dashboard demonstrates a real-world UX for the same agent, beyond what the marketplace launchpad chat offers. It also doubles as a personal portfolio piece for the work.

## Architecture

```
                                Prompt Opinion launchpad
                                          │
                                  A2A JSON-RPC + SHARP
                                          │
                                          ▼
   Clinician ──HTTPS──► Next.js dashboard ──► FastAPI proxy ──► A2A agent
                              (frontend/)        (api/)        (a2a_agent/)
                                                   │                │
                                                   │           MCP Streamable HTTP
                                                   │                │
                                                   ▼                ▼
                                              MCP server (mcp_server/)
                                              4 clinical tools, deterministic
                                                          │
                                                          ▼
                                                  HAPI FHIR R4
                                                  (Observations, Conditions,
                                                   Encounters, Communications,
                                                   AuditEvents)
```

Same Python package, two front doors. The A2A agent is the public submission surface that Prompt Opinion (and any other A2A system) calls. The Next.js dashboard is the local clinician surface that the proxy serves. Both routes converge on the same MCP tool server, which is the single source of clinical truth.

The backend ships as a single Docker image that dispatches on the `SERVICE` env var (`mcp`, `a2a`, `api`, `fixture`). Compose starts one of each, plus HAPI FHIR + PostgreSQL + Caddy. See `CLAUDE.md` for the full architecture map.

## Quickstart (local dev)

Prerequisites: Docker, Python 3.11+ with [`uv`](https://docs.astral.sh/uv/), Node.js 20+ with `pnpm`. Optional: Ollama with `qwen2.5:7b-instruct` for offline LLM.

```bash
make up              # HAPI FHIR R4 v7.2.0 + PostgreSQL on :8080
make seed            # 10 synthetic patients × 6 timepoints × 4 trajectories
make demo            # full stack: MCP :7001, A2A :9000, proxy :8000, FE :3000
```

Then open [http://localhost:3000](http://localhost:3000) for the dashboard, or POST to `http://localhost:9000/` for the A2A JSON-RPC entrypoint.

To run pieces individually in separate terminals:

```bash
make mcp             # MCP server on :7001
make agent           # A2A agent on :9000
make proxy           # FastAPI proxy on :8000
make frontend        # Next.js dev server on :3000
make demo-stop       # tear it all down
```

LLM provider is swapped via the `LLM_PROVIDER` env var: `ollama` (dev default), `groq`, `claude` (for the demo recording), or `stub` (CI). Provider-specific extras are opt-in via `pyproject.toml`.

## Repo map

| Path | What's there |
|---|---|
| `backend/a2a_agent/` | A2A JSON-RPC agent: skill router, sentinel state machine, FHIR-context hook, MCP client |
| `backend/mcp_server/` | FastMCP streamable-HTTP server with the four clinical tools |
| `backend/api/` | FastAPI proxy for the frontend; FHIR reads and the clinician approve endpoint |
| `backend/criteria/` | Deterministic rule engines: MEWT, qSOFA, CDC ASE, KDIGO |
| `backend/fhir/` | HAPI FHIR R4 client and synthetic-bundle loader |
| `backend/llm/` | Provider abstraction (Ollama, Groq, Claude, stub) |
| `backend/schemas.py` | Pydantic v2 models for every tool I/O shape |
| `frontend/` | Next.js 16 dashboard, shadcn/ui, Tailwind v4, Recharts |
| `data/patients/` | Synthetic FHIR bundles for the 10 demo patients |
| `docs/` | Project brief, demo plan, clinical evidence, security review, design system |
| `deploy/` | EC2 + Caddy reference deploy (canonical), plus alternate Render and Fly configs |
| `tests/` | `pytest` suite, including SHARP compliance, sentinel state machine, and Playwright e2e |

## Deployment

The canonical production path is a single AWS EC2 instance running the full `docker-compose` stack behind Caddy with auto-TLS via Let's Encrypt (`deploy/aws/`). Only ports 80 and 443 are public; HAPI binds to `127.0.0.1:8080` for SSH-forwarded debugging.

One host serves both surfaces over the same TLS certificate:

| Path | Service | Surface |
|---|---|---|
| `/` and `/_next/*` | `frontend` (Next.js) | Clinician dashboard |
| `/api/*` | `frontend` → `api` (FastAPI proxy) | Dashboard's server-side fetches |
| `/a2a*` and `/.well-known/agent-card.json` | `a2a` | Public A2A agent (hackathon submission) |
| `/mcp*` | `mcp` | Internal MCP tool server (called by the agent, not directly exposed for chat) |

`.github/workflows/deploy.yml` SSHes to the EC2 on every push to `main` and runs `git pull --ff-only && docker compose up -d --build`. Required repo secrets: `EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY`. `deploy/render/` and `deploy/fly.*.toml` exist as alternate targets but are not the canonical path.

## Documentation

| File | Purpose |
|---|---|
| `CLAUDE.md` | Architecture and conventions overview for Claude Code agents working in the repo |
| `docs/PROJECT_BRIEF.md` | One-page north star for the product; wins on conflicts |
| `docs/AGENTS_ASSEMBLE_TRANSCRIPT.md` | Hackathon platform walkthrough — what Prompt Opinion expects |
| `docs/A2A_REFACTOR_AUDIT.md` | Plan for the Option 3 A2A refactor on this branch |
| `docs/STORYBOARD.md` | 7-beat demo video script |
| `docs/DEMO_SCRIPT.md` | 3-minute demo timing and shot list |
| `docs/CLINICAL_EVIDENCE.md` | Citations for every clinical claim and threshold |
| `docs/SECURITY_REVIEW.md` | 17 findings, 20-item build checklist |
| `docs/PROMPT_OPINION_INTEGRATION.md` | SHARP header patterns and marketplace publishing |
| `docs/design/` | Design system tokens, components, voice and tone guide |

## Clinical posture

Every threshold cites a public standard — MEWT (Shields 2016), qSOFA / Sepsis-3 (Singer 2016), CDC Adult Sepsis Event (2018), KDIGO (2012), SBAR (IHI / Joint Commission), FHIR R4 (HL7). The exception is the hemodynamic trend rule (SBP drop ≥10% AND HR rise ≥15% over 2h), which is operational, not externally validated; this caveat is preserved in the code, the SBAR output, and `docs/CLINICAL_EVIDENCE.md`. Prospective validation is required before any clinical use.

The agent never writes to FHIR autonomously. Every escalation lands in a SQLite review queue; only the FastAPI proxy's clinician-approve endpoint writes the resulting `Communication` and `AuditEvent` resources.

## License

MIT. All clinical data in this repo is synthetic and public-domain in origin.
