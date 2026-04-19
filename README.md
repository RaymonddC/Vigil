# Vigil

**A postoperative + maternal deterioration sentinel built on MCP and A2A.**

> Submission for the Agents Assemble — Healthcare AI Endgame hackathon (Devpost, deadline 2026-05-11). Option B: published to the [Prompt Opinion Marketplace](https://www.promptopinion.ai/) as both an MCP Server (Path A) and an A2A Agent (Path B).

Deaths within 30 days of surgery are the third greatest contributor to global deaths — 4.2 million a year, after ischaemic heart disease and stroke (Nepogodiev, *Lancet Global Health* 2019). One woman dies every two minutes from obstetric complications (WHO 2023). In both cases the warning signs appear 30–60 minutes before crisis, but no single vital crosses a hard threshold — the danger lives in the pattern across BP trend, HR trend, nursing-note language, and surgical context. One nurse commonly covers 6–8 post-surgical patients (4–6 in step-down). No human holds that multivariate pattern in their head for all of them.

Vigil is the clinical infrastructure that does.

## What it is

Two published, independent layers that interoperate:

- **Path A — MCP Server.** Four reusable clinical early-warning tools, exposed over Anthropic's Model Context Protocol. Any MCP-compatible agent on Prompt Opinion can call them. Each tool enforces a published clinical standard deterministically, then layers an LLM reasoning pass for patient-specific context.
- **Path B — A2A Agent.** A Postoperative Deterioration Sentinel. Runs a 15-minute monitoring loop, calls the MCP tools in sequence, drafts SBAR escalation notes for clinician review, and never takes an autonomous action — every alert requires one-click approval.

Both layers are discoverable from the Prompt Opinion Marketplace. The same four tools work on post-op patients AND postpartum patients with zero code changes — the demo's climactic moment is at 2:00 when the sepsis tool fires on a postpartum patient using the exact same pipeline.

## The clinical spine

Every rule cites a public standard. Nothing is invented.

| Standard | What we use it for | Source |
|---|---|---|
| MEWT (Modified Early Warning Trigger) | Vital-sign threshold screen | Subbe 2001 *QJM*; Shields 2016 *AJOG* |
| qSOFA | Sepsis risk marker | Singer 2016 *JAMA* (Sepsis-3 consensus) |
| CDC Adult Sepsis Event (ASE) | Sepsis recognition surveillance criteria | CDC 2018+ ASE toolkit |
| KDIGO 2012 | AKI staging by creatinine + urine output | KDIGO guideline 2012 |
| ACOG CO-794 (Quantitative Blood Loss) | Postpartum hemorrhage quantification | ACOG 2019 |
| SBAR | Escalation handoff format | IHI / Joint Commission, Kaiser Permanente origin |
| FHIR R4 + LOINC | Data access + clinical code consistency | HL7 FHIR R4 spec |

Full citations, DOIs, and strength ratings in [`docs/CLINICAL_EVIDENCE.md`](docs/CLINICAL_EVIDENCE.md).

## Architecture

```
┌──────────────────────────┐      ┌──────────────────────┐
│  Next.js 15 Dashboard    │      │  HAPI FHIR R4 Server │
│  (shadcn + Tailwind +    │◄────►│  (Docker, synthetic  │
│   Recharts, Vercel)      │      │   patients)          │
└──────────┬───────────────┘      └──────────┬───────────┘
           │                                 │
           │  SSE / REST                     │  FHIR REST
           ▼                                 ▼
┌──────────────────────────┐      ┌──────────────────────┐
│  Postop Sentinel (A2A)   │─────►│  MCP Server (4 tools)│
│  state machine + SBAR    │      │  FastMCP + streamable│
│  LLM abstraction:        │      │  HTTP, SHARP headers │
│  Ollama / Groq / Claude  │      │  for FHIR context    │
└──────────────────────────┘      └──────────────────────┘
           │                                 │
           └────────────┬────────────────────┘
                        ▼
             Prompt Opinion Marketplace
             (Path A: MCP, Path B: A2A)
```

- **Backend:** Python 3.11+, official `mcp` SDK (FastMCP), A2A layer per reference at `github.com/prompt-opinion/po-adk-python`, `httpx`, `pydantic` v2, FastAPI host for the streamable-HTTP MCP mount.
- **FHIR:** HAPI FHIR R4 (`hapiproject/hapi:v7.2.0`) in Docker. Seeded with 10 synthetic patients × 6 timepoints × 4 trajectories (stable / deteriorating / sepsis-onset / postpartum hemorrhage). Zero real PHI.
- **LLM provider abstraction.** Swap with one env var: `LLM_PROVIDER=ollama` (dev, Qwen2.5 7B-Instruct), `groq` (integration), `claude` (video recording, Claude Sonnet 4.6), `stub` (CI).
- **SHARP context** (FHIR URL, access token, patient id) is passed on every tool call via the three HTTP headers `x-fhir-server-url`, `x-fhir-access-token`, `x-patient-id`. The MCP server advertises `ai.promptopinion/fhir-context` in its capability extensions so Prompt Opinion knows to inject them.
- **Frontend:** Next.js 15 + shadcn/ui + Tailwind + Recharts on Vercel. Four views — patient list, patient detail with vitals trend, agent trace, SBAR approval modal. Read-only; no auth, no mutation UI.

Full architecture, sequence diagrams, and component map: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## The 3-minute demo structure

| Time | Beat |
|---|---|
| 0:00–0:20 | 4.2M contributor stat + dashboard of 10 patients |
| 0:20–0:50 | PT-001 stable → NORMAL → "no false alarms" |
| 0:50–1:20 | PT-007 deteriorating → three readings → TRIGGERED + HIGH risk + contributing signals explained |
| 1:20–1:50 | SBAR drafted live → clinician approve → RRT alert |
| 1:50–2:20 | PT-009 postpartum → same sepsis tool fires EMERGENCY → antibiotic bundle in SBAR |
| 2:20–2:45 | Marketplace shot — both listings live |
| 2:45–3:00 | "4.2M + 260K preventable deaths/year. One platform. Two paths." |

Detailed beat-by-beat script, judge-hook ledger, and risk moments: [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md).

## Repository layout

```
backend/
  mcp_server/        # FastMCP tools + streamable HTTP app
  a2a_agent/         # Postop Sentinel state machine + SBAR drafter
  criteria/          # MEWT / qSOFA / CDC ASE / KDIGO rule modules
  fhir/              # HAPI FHIR client + synthetic bundle loader
  llm/               # Provider abstraction (ollama/groq/claude/stub)
frontend/            # Next.js 15 app (Vercel)
data/                # Synthetic FHIR bundles, 10 patients
docs/                # Planning set (read REVIEW_NOTES.md first)
scripts/             # seed_patients.sh, warm_fhir.sh, record_demo.sh
tests/               # pytest integration tests per trajectory
```

## Quickstart

```bash
# 1. Bring up HAPI FHIR
docker compose up hapi

# 2. Seed synthetic patients
./scripts/seed_patients.sh

# 3. Start MCP server (streamable HTTP on :7001)
cd backend && uv run python -m mcp_server.main

# 4. Start A2A agent (on :9000, uses LLM_PROVIDER from .env)
cd backend && uv run python -m a2a_agent.main

# 5. Start dashboard
cd frontend && pnpm dev  # http://localhost:3000
```

Set `LLM_PROVIDER=claude` in `.env` before recording the demo. Development default is `ollama` + `qwen2.5:7b-instruct`.

## Ground rules

- **Zero real PHI.** All data is synthetic, all ranges are public domain.
- **No autonomous action.** The agent never sends an RRT alert without clinician approval. Every escalation is a one-click human-in-the-loop step.
- **Deterministic clinical rules.** LLM reasoning is only layered on top of rule-engine output for context and prose — never to decide whether to escalate.
- **FHIR R4 correctness.** Every number on the dashboard maps to a real `Observation` with a real LOINC code. If the judges inspect the FHIR bundle, it must be valid.

## Document index

The planning set is in `docs/`. Read in this order:

1. [`REVIEW_NOTES.md`](docs/REVIEW_NOTES.md) — cross-doc audit, open decisions, corrections. **Read first.**
2. [`PROJECT_BRIEF.md`](docs/PROJECT_BRIEF.md) — the one-page north star. If it conflicts with anything else, it wins.
3. [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) — 2-layer system, sequence diagrams.
4. [`API_CONTRACTS.md`](docs/API_CONTRACTS.md) — MCP tool I/O schemas, A2A AgentCard, SHARP headers, FHIR shapes.
5. [`SYNTHETIC_DATA_SPEC.md`](docs/SYNTHETIC_DATA_SPEC.md) — exact vital values per patient × timepoint × trajectory.
6. [`FRONTEND_SPEC.md`](docs/FRONTEND_SPEC.md) — pages, components, design tokens, Vercel deploy notes.
7. [`DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) — 3-minute beat-by-beat video script + judge-hook ledger.
8. [`JUDGE_HOOKS.md`](docs/JUDGE_HOOKS.md) — what each of the 5 target judges cares about and where we land it.
9. [`BUILD_PLAN.md`](docs/BUILD_PLAN.md) — 40 tasks, dependencies, critical path, parallelization map.
10. [`RISK_REGISTER.md`](docs/RISK_REGISTER.md) — 18 risks, top-5 ranked, 6 kill switches, pre-submission checklist.
11. [`CLINICAL_EVIDENCE.md`](docs/CLINICAL_EVIDENCE.md) — citations bibliography. Every clinical claim defers here.
12. [`PROMPT_OPINION_INTEGRATION.md`](docs/PROMPT_OPINION_INTEGRATION.md) — copy-this-code reference for the Prompt Opinion runtime.

## Team

Integration lead + a pool of parallel Claude Code teammates (backend-architect, data-engineer, frontend-developer, demo-producer). Dispatch protocol in `BUILD_PLAN.md` §"Team dispatch strategy".

## License

MIT. All clinical data is synthetic and public-domain in origin.
