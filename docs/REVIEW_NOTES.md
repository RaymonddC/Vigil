# Vigil — Cross-Doc Review Notes

**Generated:** 2026-04-15 after the 11-doc planning pass.
**Purpose:** flag every contradiction, weak claim, and unresolved decision found while reviewing the planning set. Read this before starting the build.

Severity legend: 🔴 blocker (must resolve before any code is written) · 🟠 correction (fix before submission) · 🟡 nit (fix when convenient).

---

## 🔴 BLOCKER-1 — Two incompatible MCP tool sets coexist across the docs

This is the single largest problem in the planning set. Two entirely different 4-tool architectures are both in writing:

### Version A — Clinical-rule tools (per PROJECT_BRIEF, which the brief itself declares canonical)
- `screen_vital_thresholds` — MEWT/qSOFA rule engine + LLM context
- `score_deterioration_risk` — multi-signal trend ranking
- `flag_sepsis_onset` — CDC sepsis recognition score + lactate
- `generate_escalation_note` — SBAR drafter
- **Architecture implication:** clinical logic lives IN the MCP tools. The A2A agent is a thin state machine that calls them in sequence. Tools are meaningful on their own in the Marketplace — any other agent on Prompt Opinion can compose them.
- **Cited in:** `PROJECT_BRIEF.md` (2 refs), `BUILD_PLAN.md` (5 refs), `SYNTHETIC_DATA_SPEC.md` (2 refs)

### Version B — FHIR CRUD tools (per DEMO_SCRIPT, API_CONTRACTS, ARCHITECTURE, PROMPT_OPINION_INTEGRATION)
- `fhir_get_vitals`, `fhir_get_labs`, `fhir_get_meds`, `fhir_write_observation`
- **Architecture implication:** MCP tools are pure FHIR access. ALL clinical logic lives in the A2A agent. The tools are generic, not differentiated.
- **Cited in:** `DEMO_SCRIPT.md` (5 refs), `API_CONTRACTS.md` (17 refs), `ARCHITECTURE.md` (23 refs), `PROMPT_OPINION_INTEGRATION.md` (12 refs)

### Why this matters
- PROJECT_BRIEF §3 says: *"If this conflicts with any other doc, this wins."* So Version A is canonical by fiat.
- But Version B appears in **66 places across 4 docs**, including the shipped demo narration and the full I/O contracts. Rewriting 4 docs is non-trivial.
- The product story is sharper under Version A ("4 reusable clinical tools, any agent can compose them") — that's the Mandel + Mathur hook. Version B is just "we read FHIR", which is undifferentiated.
- The *easier* build is Version B because the tools are trivial passthroughs. Version A requires the rule engines (`criteria/mewt.py`, `criteria/qsofa.py`, etc.) referenced in BUILD_PLAN task F2.
- The reference implementation at `github.com/prompt-opinion/po-community-mcp` is closer to Version B (FHIR utility tools), which is why the later docs drifted.

### Decision required (before build starts)
Pick one:
1. **Keep Version A (canonical).** Rewrite DEMO_SCRIPT, API_CONTRACTS, ARCHITECTURE, PROMPT_OPINION_INTEGRATION tool-name sections. Costs ~4 hours of doc revision. Product story is strongest.
2. **Adopt Version B.** Rewrite PROJECT_BRIEF, BUILD_PLAN tool list, SYNTHETIC_DATA_SPEC expected outputs. Costs ~2 hours of doc revision. Faster build, weaker differentiation.
3. **Hybrid (recommended).** Publish 4 + 4 = 8 tools: the 4 FHIR CRUD tools (raw access, matches po-community-mcp pattern) AND the 4 clinical rule tools (the differentiated product). The A2A agent uses the rule tools; the raw tools ship as bonus infrastructure any other agent can reuse. Doc cost: ~3 hours. Product story strongest and build is incremental (CRUD tools first, rule tools on top).

My recommendation is **3 (Hybrid)** because the rule tools are where the judge hooks live (Mathur: "pattern not threshold"; Hickey: SBAR; CDC sepsis score for clinical defensibility) but the CRUD tools are needed anyway to implement the rule tools internally, so publishing both is near-zero extra cost.

---

## 🔴 BLOCKER-2 — A2A SDK choice contradicts itself

- `PROJECT_BRIEF`, `ARCHITECTURE`, `API_CONTRACTS`, `BUILD_PLAN`, `RISK_REGISTER` all say **`a2a-sdk`** (Google's official, pypi `a2a-sdk`).
- `PROMPT_OPINION_INTEGRATION` explicitly recommends **`google-adk` + `po-adk-python` patterns** and says raw `a2a-sdk` would force us to "re-invent the agent card JSON, the FHIR metadata bridge middleware, and the ADK-style session state."
- Both can't be right. `google-adk` is higher-level and the reference repo is ADK-flavored; `a2a-sdk` is lower-level but is what the rest of our docs assume.

### Decision required
Pick one SDK and amend the other 5 docs to match.
- **If `google-adk`:** amend BUILD_PLAN F7/B7 tasks, update PROJECT_BRIEF §"Ground rules", update ARCHITECTURE stack table, update `pyproject.toml` dep list in BUILD_PLAN F1.
- **If `a2a-sdk`:** amend PROMPT_OPINION_INTEGRATION §3 and §5.2, understand we lose the `before_model_callback` + `AgentExtension` + `to_a2a()` chain and must hand-roll those.

My recommendation: **`google-adk`** because the reference repo at `po-adk-python` is the only known-good integration with Prompt Opinion's runtime. Re-implementing the FHIR metadata bridge middleware is a plausible 4–8h rabbit hole; using the reference path is a 1–2h copy job.

---

## 🟠 CORRECTION-1 — Demo narration wording is clinically indefensible

`DEMO_SCRIPT.md` lines 59, 102:
> "Postoperative mortality is the world's third biggest killer"

CLINICAL_EVIDENCE §1.2 makes it explicit:
> The phrase is "third greatest *contributor* to deaths" not "third leading cause of death" — the latter is inaccurate because the Lancet figure is a modeled contributor share, not a GBD cause ranking.

**Fix:** change both mentions in DEMO_SCRIPT to match Nepogodiev 2019's exact wording:
> "Deaths within 30 days of surgery are the third greatest contributor to global deaths — after ischaemic heart disease and stroke."

This also needs to be fixed if the phrase appears in README, Devpost copy, or the video thumbnail text.

---

## 🟠 CORRECTION-2 — "Cleveland Clinic reduced sepsis mortality 35%" is uncitable

Per CLINICAL_EVIDENCE §1.5, the 35% figure traces only to Cleveland Clinic press releases, not peer-reviewed work. If this claim appears anywhere in the Devpost submission, Devpost description, README, or video, it gets flagged by Mathur (Cleveland Clinic) immediately.

**Substitute:** use the **TREWS study (Nature Medicine, 2022)** — 18% relative mortality reduction and 5.7-hour earlier detection. Peer-reviewed, prospective, defensible.

**Fix:** audit the final README and Devpost copy before submission. The claim does not currently appear in PROJECT_BRIEF or DEMO_SCRIPT but it may creep into README or marketing copy during the polish phase.

---

## 🟠 CORRECTION-3 — "Rubenstein EBL formula" is not a real named formula

CLINICAL_EVIDENCE §6.4 confirms: "Rubenstein EBL" doesn't exist in PubMed as a named formula. It was in the original tech concept but doesn't survive fact-checking.

**Current status:** the name does NOT appear in any of the 11 planning docs. The grep was clean.

**Guard rail:** if any build-phase task or video overlay adds a "Rubenstein formula" reference later, swap it for:
- **ACOG Committee Opinion 794** (Quantitative Blood Loss / QBL) for postpartum hemorrhage quantification, OR
- **Brecher's formula** (Gerdessen 2021) for pre-op blood-volume estimation.

---

## 🟠 CORRECTION-4 — Nurse staffing ratio is slightly overstated

PROJECT_BRIEF §"The problem" line 19: *"One nurse watches 8+ post-surgical patients."*

Per CLINICAL_EVIDENCE §10 the sourced number is:
- General post-surgical ward: 6–8 patients per nurse (Prin & Wunsch)
- Step-down: 4–6 patients per nurse

**Fix:** change PROJECT_BRIEF line 19 to:
> "On the post-surgical ward one nurse commonly watches 6–8 patients; in step-down 4–6. No human can hold that multivariate pattern in their head for all of them."

---

## 🟡 NIT-1 — LOINC code for hourly urine output

CLINICAL_EVIDENCE flags LOINC **9192-6** as a possible mis-pick: it's the 24-hour urine-output code, not hourly. KDIGO AKI is scored against **mL/kg/hr** which should point to **9187-6** (urine-output rate) instead.

**Impact:** if a clinical judge inspects the FHIR bundles in the synthetic data, this is a visible error.

**Fix:** confirm with a LOINC lookup, then patch `SYNTHETIC_DATA_SPEC.md` and any tool code that hard-codes the LOINC value. Low-urgency but worth catching before video recording.

---

## 🟡 NIT-2 — Patient count drift

- `PROJECT_BRIEF.md` §"Ground rules": *"10 synthetic patients × 6 timepoints × 4 trajectories"*
- `SYNTHETIC_DATA_SPEC.md`: not yet verified — check if it matches.
- `DEMO_SCRIPT.md` pre-flight: only references PT-001, PT-007, PT-009, PT-010 (4 patients). §0:20 says "watching four post-op patients" — that's demo framing and is fine, but the underlying roster must be 10 per the brief.

**Fix:** confirm SYNTHETIC_DATA_SPEC has exactly 10 patients spanning all 4 trajectories, and update any drift back to 10.

---

## 🟡 NIT-3 — Agent state-machine name drift

- PROJECT_BRIEF state machine: `IDLE → POLLING → SCREENING → RISK_SCORING → SEPSIS_CHECK → ESCALATING → AWAITING_REVIEW` (7 states)
- BUILD_PLAN task B7: `OBSERVE → SCREEN → RANK → ALERT → DOCUMENT` (5 states)
- DEMO_SCRIPT agent panel shows "DETECTING" (not in either list)

**Fix:** pick one naming scheme, propagate to all docs and frontend labels. The 7-state version is more descriptive for the demo; the 5-state is easier to code. Pick before B7 starts.

---

## 🟡 NIT-4 — Well-known agent-card endpoint path

API_CONTRACTS line 518 correctly notes that the a2a-sdk middleware whitelists `/.well-known/agent-card.json` (not `/.well-known/agent.json`). If the build diverges from that, the runtime will 404.

**Guard rail:** make sure the A2A server entry point registers this exact path.

---

## 🟡 NIT-5 — "AIDS + TB + malaria combined" comparison is uncited

DEMO_SCRIPT line 102 says postop mortality is "bigger than AIDS, tuberculosis, and malaria combined." CLINICAL_EVIDENCE doesn't surface a direct source for this combined framing.

- WHO 2019: AIDS ~690k, TB ~1.4M, malaria ~409k = ~2.5M combined
- Nepogodiev 2019 postop 30-day figure: ~4.2M

So the arithmetic backs it up but the phrase should either be supported by a specific source in Devpost copy, or downgraded to "more than AIDS, tuberculosis, and malaria each." Either is defensible; inconsistency is not.

---

## Decision log (for restart)

Resolve these in order:

| # | Decision | Owner | Blocks |
|---|---|---|---|
| 1 | MCP tool architecture: A / B / Hybrid (see BLOCKER-1) | User | Everything |
| 2 | A2A SDK: `a2a-sdk` vs `google-adk` (see BLOCKER-2) | User | Backend task B7 |
| 3 | State-machine naming: 7-state vs 5-state (see NIT-3) | User | Frontend labels, BUILD_PLAN B7 |
| 4 | Rewrite DEMO_SCRIPT wording to "third greatest contributor" | Lead agent | Video recording |
| 5 | Confirm LOINC 9192-6 vs 9187-6 for hourly UO | Backend agent | Synthetic data + tool code |

Everything else can wait for the polish phase.

---

## What's strong across the planning set

- **Clinical evidence base is solid.** CLINICAL_EVIDENCE.md cited every non-trivial claim and flagged its own weaknesses. Use it as the canonical bibliography.
- **Risk register is thorough.** 18 risks, top-5 ranked, 6 kill switches, and a dependency graph of external unknowns. Minimal editorial overhead needed.
- **Build plan is executable.** 40 tasks, dependencies mapped, critical path 28h, total 116h, named parallelization map. Ready to dispatch to a teammate pool once BLOCKER-1 is decided.
- **Judge hooks map is explicit.** Every judge is served by 3+ beats, with timestamps tied to the demo script. Update only after the BLOCKER-1 tool-name decision lands.
- **Prompt Opinion integration is copy-ready.** The 3 critical patterns (`get_capabilities` monkey-patch, SHARP header read, `extract_fhir_context` callback) have working code blocks annotated with GitHub permalinks.

## What's still missing

- A `prompt_opinion_config.json` / manifest file format — nobody found one in the reference repos. Must be confirmed in the Prompt Opinion Discord on day 1 of the build (R01 in RISK_REGISTER).
- Confirmation that a marketplace listing is *required* for Option B (vs merely encouraged). Same Discord ask.
- An account on `app.promptopinion.ai`. Also day 1.

---

*End of review notes. Re-read this before dispatching the build team.*
