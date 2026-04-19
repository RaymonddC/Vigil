# Vigil — Project Brief

**One-page north star. Every other doc defers to this. If this conflicts with any other doc, this wins.**

## What it is

Vigil is a postoperative + maternal deterioration sentinel built for the **Agents Assemble — Healthcare AI Endgame** hackathon (Devpost, submission deadline **2026-05-11**). We submit under **Option B**, which covers both competition paths in a single unified product:

- **Path A — MCP Server**: 4 reusable clinical early-warning tools exposed over Anthropic's Model Context Protocol.
- **Path B — A2A Agent**: A Postoperative Deterioration Sentinel that calls the MCP tools in a 15-minute monitoring loop and drafts SBAR escalation notes for clinician one-click approval.

Both layers are published to the **Prompt Opinion Marketplace** (https://www.promptopinion.ai/), the hackathon's host platform. The MCP server and A2A agent are independent, discoverable, and any agent on the platform can call our 4 tools.

## The problem

- **4.2 million** people die within 30 days of surgery every year — more than tuberculosis, HIV/AIDS, and malaria each (Nepogodiev 2019, *Lancet Global Health*).
- **One woman dies every 2 minutes** from obstetric complications; most from hemorrhage or sepsis.
- In both cases the warning signs appear **30–60 minutes before crisis**. No single vital crosses a hard threshold — the danger lives in the pattern across BP trend + HR trend + nursing note language + surgical context.
- One nurse watches 8+ post-surgical patients. No human can hold that multivariate pattern in their head for all of them.

## The solution

Reusable clinical infrastructure, not a one-off agent.

- **4 MCP tools** enforce published clinical standards (MEWT, qSOFA, CDC SRS) deterministically, then layer an LLM reasoning pass for patient-specific context and SBAR prose generation.
- **1 A2A agent** runs a state machine (IDLE → POLLING → SCREENING → RISK_SCORING → SEPSIS_CHECK → ESCALATING → AWAITING_REVIEW) and never acts autonomously — every escalation requires clinician approval.
- **Unified design**: the same 4 tools work on postop patients AND postpartum patients. The demo's climactic moment is exactly that — at 2:00 of the video, we show `flag_sepsis_onset` firing on a postpartum patient with zero code changes. Maternal is a cameo trajectory in synthetic data, not a separate module.

## Success metrics

| Metric | Target |
|---|---|
| Scorecard | ≥37/40 (AI Factor 10, Impact 10, Feasibility 9, Buildability 8) |
| Prize | $7.5K grand prize, or top-3 ($15K+) |
| Demo video | ≤3:00, hits all 5 target judges by end |
| Marketplace | Published as both MCP Server (Path A) AND A2A Agent (Path B) |
| Clinical integrity | Zero hallucinated thresholds — every rule cites a public standard |
| Deadline | 2026-05-11 |

## Target judges

Five named judges; each demo moment and every piece of Devpost copy must land at least 3 of their hooks. Details in `JUDGE_HOOKS.md`.

1. **Piyush Mathur** (Cleveland Clinic) — postop complication AI, his exact research area
2. **Josh Mandel** (Microsoft Research) — SMART on FHIR creator, values FHIR correctness + reusable MCP infrastructure
3. **Joshua Hickey** (Mayo Clinic) — SBAR is Mayo's internal rapid-response format
4. **Stephon Proctor** (CHOP) — wants agentic AI that takes action, not dashboards
5. **Alice Zheng** (VC) — women's health × AI investor thesis, maternal mortality is her pain point

## Ground rules (non-negotiable)

- **Unified architecture per the tech concept doc** — not the earlier split maternal+postop chat-summary design.
- **Python 3.11+** backend: official `mcp` SDK (FastMCP merged in), `a2a-sdk` (Google's official), `httpx`, `pydantic`.
- **Next.js 15 + shadcn/ui + Tailwind + Recharts** frontend, deployed to Vercel.
- **HAPI FHIR R4** in Docker (`hapiproject/hapi:v7.2.0`) for clinical realism in the demo video.
- **LLM provider abstraction**: `LLM_PROVIDER` env var switches between `ollama` (dev), `groq` (integration), `claude` (video recording), `stub` (CI). Qwen2.5 7B-Instruct default dev model.
- **SHARP context = 3 HTTP headers**: `x-fhir-server-url`, `x-fhir-access-token`, `x-patient-id`. Reference: github.com/prompt-opinion/po-community-mcp.
- **10 synthetic patients × 6 timepoints × 4 trajectories** (stable, deteriorating, sepsis onset, postpartum hemorrhage). All public-domain clinical ranges.
- **Zero real PHI. Ever.**
- **No autonomous action** — agent never sends an RRT alert without clinician approval.

## What we're deliberately NOT building

- Custom SMART on FHIR auth — Prompt Opinion handles it, we just read headers.
- Maternal-specific MCP tools — same tools, different trajectory.
- EHR integration — synthetic FHIR bundles only.
- Model training — clinical criteria are deterministic; LLM only explains + drafts prose.
- User accounts, login, editing — frontend is read-only clinician dashboard.
- Mobile app — desktop browser is the clinical use context.
- Historical outcome tracking beyond demo — logged to FHIR AuditEvent but not analyzed.

## The 3-minute demo structure (hero = postop, cameo = maternal)

| Time | Beat |
|---|---|
| 0:00–0:20 | 4.2M stat + platform dashboard of 10 patients |
| 0:20–0:50 | PT-001 stable → NORMAL result → "no false alarms" |
| 0:50–1:20 | PT-007 deteriorating → 3 readings → TRIGGERED + HIGH risk + 3 contributing signals explained |
| 1:20–1:50 | SBAR note drafted live → clinician approve → RRT alert sent |
| 1:50–2:20 | PT-009 postpartum → same `flag_sepsis_onset` fires EMERGENCY → antibiotic bundle in SBAR |
| 2:20–2:45 | Marketplace shot — both listings visible |
| 2:45–3:00 | "4.2M + 260K preventable deaths/year. One platform. Two paths. Published today." |

Detailed script in `DEMO_SCRIPT.md`.

## Document tree

- `PROJECT_BRIEF.md` (this) — north star
- `ARCHITECTURE.md` — 2-layer system, component diagrams, sequence diagrams
- `API_CONTRACTS.md` — MCP tool I/O schemas, A2A AgentCard, SHARP headers, FHIR shapes
- `SYNTHETIC_DATA_SPEC.md` — exact vital values for 10 patients × 6 timepoints × 4 trajectories
- `FRONTEND_SPEC.md` — pages, components, design tokens, Vercel deploy
- `DEMO_SCRIPT.md` — 3-minute beat-by-beat video script
- `JUDGE_HOOKS.md` — what each of the 5 judges cares about and where we land it
- `BUILD_PLAN.md` — phased task breakdown with dependencies + acceptance criteria
- `RISK_REGISTER.md` — known risks + mitigations
- `CLINICAL_EVIDENCE.md` — citations and research backing for all clinical claims
- `PROMPT_OPINION_INTEGRATION.md` — exact patterns to copy from github.com/prompt-opinion reference repos
- `README.md` — public-facing (synthesized last, sources all above)
