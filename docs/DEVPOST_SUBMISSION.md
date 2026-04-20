# Devpost Submission — Vigil

> **Draft for the user to copy into the Devpost form.** Each section maps to a Devpost field.

---

## Title (max 70 characters)

```
Vigil — agentic sentinel for postop + postpartum deterioration
```

(63 characters)

---

## Tagline (max 200 characters)

```
4 MCP tools, 1 A2A agent, 0 code changes between wards. Vigil drafts the SBAR, the clinician sends it — agentic action on FHIR R4 for the 4.2M who die within 30 days of surgery.
```

(179 characters)

---

## Description

### Inspiration

Every year, 4.2 million people die within 30 days of surgery — more than HIV, tuberculosis, and malaria combined ([Nepogodiev, *Lancet* 2019](https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(18)33139-8/fulltext)). A woman dies every two minutes from obstetric complications ([WHO 2023](https://www.who.int/news/item/23-02-2023-a-woman-dies-every-two-minutes-due-to-pregnancy-or-childbirth--un-agencies)). In the US, Black women die from pregnancy-related causes at **roughly 3× the rate of white women**, and over 80% of those deaths are preventable ([CDC Pregnancy Mortality Surveillance System](https://www.cdc.gov/reproductive-health/maternal-infant-health/pregnancy-mortality-surveillance.html); [CDC "Four in 5 pregnancy-related deaths are preventable"](https://www.cdc.gov/media/releases/2022/p0919-pregnancy-related-deaths.html)). The "fourth trimester" — the 12 weeks postpartum — is when most maternal deaths happen, and it's exactly when clinical attention drops off. In both postop and postpartum, the warning signs appear 30–60 minutes before crisis. But no single vital crosses a hard threshold — the danger lives in the *pattern* across HR trend, BP trend, and nursing context. On post-surgical wards one nurse covers 6–8 patients. No human holds that multivariate pattern in their head for all of them.

Current AI solutions for postoperative care show only marginal lift over traditional scoring systems like MEWS and qSOFA ([Moll, Khanna & Mathur, *Crit Care Sci* 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12266812/)). And clinicians override 70–90% of threshold-based alerts ([AHRQ PSNet](https://psnet.ahrq.gov/primer/alert-fatigue)). The problem isn't more alerts — it's better *orchestration* of existing clinical knowledge.

That insight is Vigil.

### What it does

Vigil is a clinical early-warning system that monitors post-surgical and postpartum patients through a live FHIR R4 server and escalates when the *trend pattern* — not a single threshold — indicates deterioration.

**Path A — MCP Server.** Four reusable clinical tools exposed over Anthropic's Model Context Protocol:

1. **`screen_vital_thresholds`** — MEWT + qSOFA threshold check against FHIR Observations
2. **`score_deterioration_risk`** — Trend analysis over ≥3 readings, composite risk banding
3. **`flag_sepsis_onset`** — CDC Adult Sepsis Event criteria with SIRS fallback
4. **`generate_escalation_note`** — LLM-drafted SBAR note (never writes to the chart)

**Path B — A2A Agent.** A Postoperative Deterioration Sentinel that runs a 7-state machine (IDLE → POLLING → SCREENING → RISK_SCORING → SEPSIS_CHECK → ESCALATING → AWAITING_REVIEW), calls the MCP tools in sequence, and drops SBAR drafts into a review queue for clinician one-click approval.

**Closed-loop action, not a dashboard.** When the clinician clicks "Approve & send RRT," the backend writes a FHIR `Communication` resource (the SBAR payload) and an `AuditEvent` (the approval audit trail) to HAPI FHIR. The agent never takes autonomous action — it drafts, it waits.

**Same tools, different ward.** The same four MCP tools fire on a postpartum patient (PT-009, 29F, 3 days post-C-section, lactate 4.2, WBC 18) with zero code changes. Maternal sepsis SBAR, generated the exact same way. This is the substitutability thesis applied to MCP tools: one build, many wards.

### How we built it

- **Backend:** Python 3.11+, official `mcp` SDK (FastMCP) for the MCP server, raw `a2a-sdk` for the A2A agent (no google-adk lock-in), `httpx` + `pydantic` v2. LLM provider abstraction switches between Ollama (dev), Groq (fast), Claude Sonnet (recording), and stub (CI) with one env var.
- **FHIR store:** HAPI FHIR R4 (`v7.2.0`) in Docker + PostgreSQL 15. Seeded with 10 synthetic patients × 6 timepoints × 4 trajectories (stable, deteriorating, sepsis onset, postpartum hemorrhage). Zero real PHI.
- **Frontend:** Next.js 15 (App Router) + shadcn/ui + Tailwind + Recharts. Six views: patient roster, patient detail with vitals trend, review queue with approve button, A2A agent timeline with real-time state trace, system status, and home.
- **SHARP compliance:** Three HTTP headers (`x-fhir-server-url`, `x-fhir-access-token`, `x-patient-id`) flow through every MCP call. The A2A agent bridges metadata to headers for downstream tool calls. 39 compliance tests.
- **Clinical standards:** Every threshold cites a published standard — MEWT (Shields 2016), qSOFA/Sepsis-3 (Singer 2016), CDC Adult Sepsis Event (2018), KDIGO (2012), ACOG QBL (2019), SBAR (IHI). Nothing is invented.

### Challenges we ran into

1. **LLM latency for live SBAR generation.** Claude can take 8–12 seconds for a full SBAR note, but the demo beat allocates only 20 seconds total. We built a demo-mode cache that replays pre-generated SBAR character-by-character while the agent still fires real MCP tool calls underneath.

2. **a2a-sdk vs. google-adk.** The Prompt Opinion reference repo uses Google ADK, which hard-wires Gemini as the LLM provider. We needed Claude for demo quality and Ollama for free local dev. We ported to raw `a2a-sdk` — same AgentCard, same JSON-RPC, but our own LLM provider abstraction. Net result: zero model lock-in.

3. **FHIR R4 correctness under time pressure.** Every LOINC code, UCUM unit, and resource shape had to be correct — Josh Mandel (SMART on FHIR creator) is a judge. We built a citations bibliography (`CLINICAL_EVIDENCE.md`) with strength ratings and forced every clinical claim through it.

4. **Trend-based alerting without published thresholds.** Our hemodynamic trend rule (SBP drop ≥10% AND HR rise ≥15% over 2h) is not a named clinical criterion — it's an operational threshold derived from MEWT and qSOFA literature. We document it explicitly as "not externally validated" and flag it for local validation before deployment.

### Accomplishments that we're proud of

- **Closed-loop FHIR write in a hackathon project.** Not a mock — clinician approves, `Communication` + `AuditEvent` land in HAPI, toast confirms the resource IDs. This is what Stephon Proctor (CHOP) calls "agentic, not dashboard."
- **Zero code changes between postop and postpartum.** The same 4 tools fire on PT-007 (CABG, day 2) and PT-009 (postpartum sepsis, day 3). No `if ward == "OB"` anywhere. The FHIR data is the abstraction.
- **312 tests, including 39 SHARP compliance tests and a 38-test integration harness covering 4 trajectories × 4 tools × 3 SHARP patterns.** For a hackathon. Because interop isn't real if it's not tested.
- **Every clinical claim cites a source with a strength rating.** `CLINICAL_EVIDENCE.md` tracks 12 citation categories, flags weak claims, and recommends rephrasings. We caught our own overclaim ("35% sepsis mortality reduction" → actual figure is 18%, Nature Medicine 2022) during self-review.

### What we learned

- MCP tools are a natural fit for clinical decision support — each tool is a reusable, composable unit of clinical logic that any agent can call. The substitutability thesis (same tools, any ward) is powerful.
- SBAR is more than a format — it's a *workflow*. Generating the text is 10% of the problem; routing it to the right clinician, getting approval, and writing back to the chart is the other 90%.
- Trend-based alerting sits in a gap between rule engines (too many false alerts) and black-box ML (not auditable). Deterministic rules + LLM reasoning is a design pattern worth exploring further.

### What's next

- **Prospective validation.** The hemodynamic trend thresholds need testing against MIMIC-IV and local institutional data before any clinical deployment.
- **Real EHR integration.** HAPI FHIR is a dev sandbox. The SHARP header pattern ports directly to Epic and Cerner FHIR endpoints.
- **Additional clinical pathways.** Pediatric deterioration (PEWS), ICU delirium screening, and surgical site infection monitoring — same tools, new trajectories.
- **Prompt Opinion marketplace listing.** Both MCP Server and A2A Agent registered and discoverable.

---

## Built with

```
python, mcp, a2a-sdk, fastapi, nextjs, react, typescript, shadcn-ui, tailwind-css, recharts, fhir, hapi-fhir, docker, postgresql, pydantic, httpx, ollama, groq, claude, prompt-opinion
```

---

## Try it out

- **GitHub:** https://github.com/RaymonddC/Vigil
- **Demo video:** [link to Devpost video]
- **Live dashboard:** [Vercel URL]
- **Agent card:** `https://<deploy>/.well-known/agent-card.json`

---

## Notes for the user

- **Title:** 63 chars, under the 70-char limit. Hits Proctor ("agentic"), Mathur ("postop"), Zheng ("postpartum").
- **Tagline:** 179 chars, under the 200-char limit. Hits Mandel ("MCP tools", "FHIR R4"), Zheng ("4.2M"), Hickey ("SBAR").
- **Vocabulary:** Uses "agentic" (Proctor), "substitutable" → implied via "0 code changes" (Mandel), "SBAR" (Hickey), "postpartum" (Zheng), "postop" (Mathur). Avoids "dashboard" per Proctor's rejection trigger.
- **Description:** ~1,200 words. Devpost has no hard word limit for the description field, but judges skim — the first 3 sentences and the section headers matter most.
- **Built-with tags:** Devpost auto-generates a tag cloud from this list. Include every framework that a judge might search for.
