# Vigil — Final Review (Round 3)

> **Reviewer:** `doc-reviewer` (fresh-eyes, cold read)
> **Date:** 2026-04-19
> **Scope:** All 14 planning docs + README, post-phase-2 rewrite. Third and final review pass.

---

## 1. Post-Rewrite Consistency Audit

### 1.1 Tool names — PASS (with 1 residual)

The four canonical MCP tool names (`screen_vital_thresholds`, `score_deterioration_risk`, `flag_sepsis_onset`, `generate_escalation_note`) are used consistently across PROJECT_BRIEF, ARCHITECTURE, API_CONTRACTS, SYNTHETIC_DATA_SPEC, BUILD_PLAN, DEMO_SCRIPT, JUDGE_HOOKS, PROMPT_OPINION_INTEGRATION, and README. No stale Set B/C/D/E names remain in any active doc.

### 1.2 Autonomy rule — PASS

All active docs now agree: MCP tools and the A2A agent never write to FHIR. The FastAPI proxy's `/approve` endpoint is the single FHIR write entry point, writing `Communication` + `AuditEvent` only on clinician approval. Confirmed in: ARCHITECTURE:278, API_CONTRACTS:349, BUILD_PLAN:128/140/152/367, DEMO_SCRIPT:79, FRONTEND_SPEC:207, JUDGE_HOOKS:97/146/211. No contradictions found.

**Minor note:** JUDGE_HOOKS:211 still says "Agent writes a FHIR Communication resource on screen" — this should read "Backend writes a FHIR Communication resource on screen after clinician approves." The wording is ambiguous enough to be misconstrued as autonomous action.

### 1.3 A2A SDK — PASS

All active docs reference `a2a-sdk` as the chosen path. `google-adk` appears only in: (a) PROMPT_OPINION_INTEGRATION §1b with the correct "historical reference only" callout (line 52), (b) REVIEW_NOTES, REVIEW_SECOND_OPINION, and REWRITE_PROPOSAL (historical artifacts). No active doc recommends google-adk.

### 1.4 Patient roster — PASS

Exactly 10 patients (PT-001 through PT-010). Distribution: 3 stable / 4 deteriorating / 2 sepsis / 1 postpartum hemorrhage. PT-011 is mentioned only in SYNTHETIC_DATA_SPEC:26 as a historical note about the dropped case. No active reference to PT-011 as a live patient.

### 1.5 SHARP headers — PASS

All active docs use exactly `x-fhir-server-url`, `x-fhir-access-token`, `x-patient-id`. The old `x-llm-provider` / `x-llm-api-key` references exist only in REVIEW_SECOND_OPINION:101 (historical finding). BUILD_PLAN F5 (line 78) now correctly states "API keys come from server-side env vars... never from HTTP headers."

### 1.6 State machine naming — FAIL

Two naming schemes persist:

- **7-state (canonical):** `IDLE -> POLLING -> SCREENING -> RISK_SCORING -> SEPSIS_CHECK -> ESCALATING -> AWAITING_REVIEW` — used in PROJECT_BRIEF:26, ARCHITECTURE:42/180, BUILD_PLAN:140/178, PROMPT_OPINION_INTEGRATION:265.
- **5-state (stale):** `OBSERVE -> DOCUMENT` — still in BUILD_PLAN:351 ("A2A Postop Sentinel runs OBSERVE->DOCUMENT state machine end-to-end").

**Fix needed:** `BUILD_PLAN.md:351` — rewrite acceptance criterion to use the 7-state names.

### 1.7 Port numbers — FAIL

Port assignments remain inconsistent across docs:

| Service | ARCHITECTURE | DEMO_SCRIPT | README | PROMPT_OPINION_INTEGRATION | API_CONTRACTS |
|---------|-------------|-------------|--------|---------------------------|---------------|
| MCP server | :7001 | :7001 | **:7000** | :7001 (§3.3), :5001 (§1a ref) | — |
| A2A agent | **:7002** | :9000 | :9000 | :9000 | :9000 |
| HAPI FHIR | :8080 | :8080 | :8080 | — | :8080 |
| Frontend | :3000 | :3000 | :3000 | — | — |
| FastAPI proxy | :8000 | — | — | — | :8000 |

**Fixes needed:**
1. `README.md:107` — change `:7000` to `:7001`
2. `ARCHITECTURE.md:226` — change `:7002` to `:9000` (or vice versa; pick one and lock)
3. Lock canonical ports in a single table (recommended: docker-compose spec)

### 1.8 "Third biggest killer" wording — FAIL

`DEMO_SCRIPT.md:59` beat table narration still reads: *"Postoperative mortality is the world's third biggest killer"*. The rehearsal text at line 102 correctly reads "third greatest contributor." CLINICAL_EVIDENCE §1.2 and §12 item 4 explicitly flag "biggest killer" / "leading cause" as inaccurate.

**Fix needed:** `DEMO_SCRIPT.md:59` — change "third biggest killer" to "third greatest contributor to global deaths".

---

## 2. Clinical Plausibility

### 2.1 Lab values by trajectory — PASS

- **Stable:** All labs within normal reference ranges at all timepoints. Lactate 1.2-1.3 (ref <2.0), WBC 8.0-8.4 (ref 4.5-11.0), Creatinine 0.9 (ref 0.6-1.2), Bilirubin 0.6-0.7 (ref 0.1-1.2), Platelets 232-240 (ref 150-400). Clinically coherent.
- **Deteriorating:** Progressive worsening follows expected organ-dysfunction sequence. Lactate crosses 2.0 at T+4h (CDC ASE threshold), WBC rises to 14.2, creatinine drifts to 1.5. Physiologically plausible for evolving surgical complication.
- **Sepsis:** Lactate 4.2 at T+4h, WBC 18.4, platelets dropping to 98 at T+8h. Classic septic cascade. Clinically accurate.
- **PPH:** Hgb drop 12.4 -> 7.2 at T+4h tracks with 1800 mL EBL. Lactate rise to 3.2 consistent with hemorrhagic shock. Post-intervention improvement (T+6h/T+8h) is realistic.

### 2.2 PT-007 trend rule — PASS

SBP 130 -> 114 over 2h = 12.3% drop (threshold: >=10%). HR 76 -> 92 over 2h = 21.1% rise (threshold: >=15%). Both conditions met at T+2h. The rule in CLINICAL_EVIDENCE §2.3 fires correctly. SYNTHETIC_DATA_SPEC §2.2 documents this calculation explicitly.

### 2.3 PT-009 sepsis resources for CDC ASE — PASS (with caveat)

At T+4h: Temp 38.8 (>38), HR 118 (>90), RR 24 (>20), suspected infection source (postpartum). Lactate 4.2 (organ dysfunction: >=2.0). WBC 18.4. MedicationAdministration (ampicillin-sulbactam) at T+4:20 provides the antibiotic signal. CDC ASE criteria met: presumed infection + organ dysfunction (lactate). This fires `cdc_ase` mode, not `sirs_fallback`.

**Caveat:** CDC ASE formally requires a blood culture order AND >=4 qualifying antibiotic days. The synthetic data has only 1 antibiotic dose. For a demo this is acceptable, but CLINICAL_EVIDENCE §4.1 should note we use a simplified ASE adaptation (antibiotic start as infection proxy) rather than the full retrospective surveillance definition. This is already partially acknowledged at CLINICAL_EVIDENCE:121 ("caveat for our copy").

### 2.4 SNOMED codes — PARTIAL PASS

Verified codes:
- **59621000** (Essential hypertension) — Confirmed valid SNOMED CT code via FindACode and BioPortal.
- **44054006** (Type 2 diabetes mellitus) — Standard, widely used SNOMED code.

Flagged codes:
- **199223000** — Listed as "Gestational diabetes" in SYNTHETIC_DATA_SPEC but the actual SNOMED CT concept is "Diabetes mellitus during pregnancy, childbirth and the puerperium" — a broader category. The correct code for gestational diabetes mellitus specifically is **11687002**. **Fix recommended:** change PT-009's comorbidity from 199223000 to 11687002.
- **58532003** — Listed as "Placenta accreta." BioPortal shows placenta accreta as **70129008**, not 58532003. Could not confirm 58532003 is a valid SNOMED code for this concept. **Needs verification** before build; if invalid, replace with 70129008.
- **11612004** — Listed as "Chorioamnionitis." Could not confirm via web search. The ICD-10 code O41.12 is correct but the SNOMED mapping needs verification at build time. The canonical SNOMED for chorioamnionitis appears to be 59031006 or related. **Needs verification.**

### 2.5 RxNorm codes — PARTIAL PASS

- **309264** (Cefazolin) — Plausible but could not confirm exact RxCUI via web search. RxNorm has multiple cefazolin entries (e.g., 1665050 for "cefazolin 1000 MG Injection"). Verify at build time via RxNav.
- **1659149** (Ampicillin-sulbactam) — Not found in search results. The closest confirmed RxCUI is **1659598** for "ampicillin 2000 MG / sulbactam 1000 MG Injection." **Fix recommended:** verify and potentially replace with 1659598 or the correct SCD-level RxCUI.
- **203134** (Piperacillin-tazobactam) — Not verified. Verify at build time.

### 2.6 LOINC urine output code — NEEDS DECISION

CLINICAL_EVIDENCE §11.2 note (line 269) correctly flags this as unresolved. The docs use **9192-6** ("Urine output 24 hour") but KDIGO AKI staging needs hourly rate (mL/kg/h). The correct code for hourly urine output is **9188-4** ("Urine output 1 hour"). The synthetic data UCUM unit is `mL/h` which semantically is an hourly rate, not a 24h volume. **Fix:** Either change the LOINC to 9188-4 (matches the `mL/h` unit and KDIGO use case) or keep 9192-6 and change the unit to `mL` (24h total). Recommend 9188-4 since the tools need hourly rate for KDIGO.

### 2.7 Comorbidities vs. surgical context — PASS

- PT-004 (open colectomy) + T2DM + COPD: clinically coherent (common surgical population).
- PT-007 (exploratory laparotomy) + T2DM + CKD stage 3: excellent — CKD is a major postop risk factor and drives the creatinine monitoring story.
- PT-009 (C-section) + gestational diabetes + obesity + chorioamnionitis: perfect setup for postpartum sepsis.
- PT-010 (vaginal delivery) + placenta accreta + previous cesarean + mild preeclampsia: textbook PPH risk profile.

---

## 3. Research Findings

### 3a. Prompt Opinion updates

The Prompt Opinion GitHub organization has **4 repos**: `po-community-mcp` (updated Apr 17, 2026), `po-adk-python` (updated Apr 16, 2026), `po-overview` (updated Mar 24, 2026), `po-adk-typescript` (updated Feb 24, 2026). No new repos since our last fetch. The community MCP repo had 89 commits as of fetch date; changes since Apr 15 could not be determined from the listing page — a `git log` on the repo would be needed. No new blog posts or documentation found at promptopinion.ai beyond what we already captured.

### 3b. Devpost rules — CRITICAL FINDING

**Marketplace listing is REQUIRED, not optional.** The rules state: "Submissions must be successfully published to the Prompt Opinion Marketplace with a functional configuration" to pass Stage One technical qualification. Submissions not published in the marketplace **will not advance to scoring.**

**Judging criteria are 3, equally weighted** (not 4 as our PROJECT_BRIEF assumed):
1. **The AI Factor** — Does the solution leverage Generative AI beyond what rule-based software can do?
2. **Potential Impact** — Does it address a significant pain point with clear hypothesis for improvement?
3. **Feasibility** — Could this exist in a real healthcare system today? Does it respect privacy, safety, and regulatory constraints?

**Our scorecard uses 4 criteria** (AI Factor, Impact, Feasibility, Buildability) totaling /40. Devpost uses 3 equally weighted criteria with no "Buildability" category. **Fix needed:** Update PROJECT_BRIEF:33 scorecard and recalibrate target from ">=37/40" to a 3-criterion scale.

**Prize structure:** 1st $7,500, 2nd $5,000, 3rd $2,500, 10 Honorable Mentions at $1,000 each. Total $25,000. Our PROJECT_BRIEF:34 says "$7.5K grand prize, or top-3 ($15K+)" — the $15K+ figure is correct ($7.5K + $5K + $2.5K = $15K for top 3).

**Option B** is "an agent that supports the A2A standard" — submissions must be "explicitly built as either an MCP Server or an A2A-enabled Agent." Our dual-path (both MCP + A2A) approach is valid and potentially stronger than single-path entries.

### 3c. a2a-sdk current version

Latest stable: **0.3.26** (released Apr 9, 2026). Pre-release 1.0.0a3 also available. Python >=3.10 required.

**API surface mismatch:** Our schematic code in PROMPT_OPINION_INTEGRATION §3.1 references `AgentExecutor`, `RequestContext`, `EventQueue`, `Task`, `TaskState`, `TextPart` from `a2a.server` and `a2a.types`. The PyPI page does NOT confirm `AgentExecutor` exists as a class name. The GitHub README does not enumerate class names either. The actual API docs are at `a2a-protocol.org/latest/sdk/python/api/` (not fetched).

**Risk:** The schematic code is explicitly labeled as "to be verified against a2a-sdk 0.3.x during backend task B7" (PROMPT_OPINION_INTEGRATION:308). This is correctly flagged. BUILD_PLAN B7 must start with an API surface audit.

### 3d. HAPI FHIR on WSL2

Known issues found:
- **Volume mount reliability:** Docker for Windows issue #10060 documents that bind mount volumes under WSL2 are "not reliable" — volumes can resolve to different paths. Mitigation already in RISK_REGISTER R02: "Use bind mount under `/mnt/wsl` not `/mnt/d` for perf."
- **Startup race:** Docker can start before WSL2 mounts are ready, causing mount failures on system boot. Mitigation: manual `docker compose up` after login, not auto-start.
- **Path mixing:** Windows-style paths vs Linux-style paths cause silent failures. Always use `/mnt/c/...` format.
- **JVM memory:** HAPI FHIR's JPA server needs >=2GB heap. `.wslconfig` must allocate >=4GB to WSL2.

No HAPI-specific blockers found. RISK_REGISTER R02 mitigations are adequate.

### 3e. Piyush Mathur publications

The paper already cited in CLINICAL_EVIDENCE §8.1 — "Artificial intelligence for the prediction of postoperative complications in the critically ill" (Crit Care Sci, 2025) — remains his most recent relevant publication. He is also Guest Editor for an MDPI Healthcare special issue on "AI and ML in Perioperative Oncology" (2025-2026). No additional publications found that we should add. Our citation is current.

### 3f. Competitor scan

No visible competitor submissions found. The hackathon Devpost page shows a submissions management URL but individual entries are not publicly visible before the deadline. No blog posts, tweets, or forum discussions about specific competing projects were found. CompeteHub lists the hackathon but shows no participant projects. This means we cannot differentiate proactively, but it also means no competitor has a public head start.

---

## 4. README Assessment

### 4.1 Tool names — PASS
All four canonical names used correctly. No stale names.

### 4.2 Architecture description — PASS
Correctly describes MCP + A2A layers, `a2a-sdk` (not `google-adk`), SHARP headers.

### 4.3 "Third greatest contributor" — PASS
Line 7: "third greatest contributor to global deaths" — correct wording.

### 4.4 Patient roster — PASS
"10 synthetic patients x 6 timepoints x 4 trajectories" (line 61). Correct.

### 4.5 Internal links — PASS
All `docs/*.md` links are relative and point to existing files. No broken links detected.

### 4.6 Specific fixes needed

1. **Port mismatch (line 107):** MCP server listed as `:7000`, should be `:7001` per ARCHITECTURE and DEMO_SCRIPT.
2. **Backend description (line 60):** Says "A2A layer per reference at `github.com/prompt-opinion/po-adk-python`" — this should clarify "pattern adapted from" rather than implying we clone it, given the a2a-sdk decision.
3. **Document index (line 130):** Lists REVIEW_NOTES.md as "read first" but does not list CLINICAL_EVIDENCE.md, DEFERRED_FINDINGS.md, or REVIEW_FINAL.md. Consider adding these.
4. **Missing CLINICAL_EVIDENCE link in document index** — currently referenced as item 11 (line 140) but listed out of read order (should appear earlier, as it is a dependency for understanding the tools).

### 4.7 60-second judge scan — MOSTLY PASS

A judge scanning this in 60 seconds would understand: what Vigil does (postop + maternal sentinel), the clinical standards it uses (table), the architecture (diagram), the demo flow (table), and how to run it (quickstart). The opening paragraph effectively conveys urgency. Two improvements: (a) add a one-line "Built with" badge row (Python, MCP, A2A, FHIR, Next.js) for fast visual scanning, (b) the quickstart should mention `docker compose up` for ALL services, not just `hapi`.

---

## 5. Gap Analysis

Ranked by build-time urgency:

| # | Missing Artifact | Urgency | Effort | Notes |
|---|-----------------|---------|--------|-------|
| 1 | **Docker Compose spec** | HIGH — blocks demo | 2h | Services: hapi (:8080), mcp-server (:7001), a2a-agent (:9000), fastapi-proxy (:8000). Health checks, volume mounts, port locks. Currently hand-waved in ARCHITECTURE §6 and BUILD_PLAN F6. |
| 2 | **Environment variable reference** | HIGH — blocks build | 1h | Complete list: `LLM_PROVIDER`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, `VIGIL_MCP_URL`, `NEXT_PUBLIC_API_BASE_URL`, `VALID_API_KEYS`, `HAPI_FHIR_URL`, `POLL_INTERVAL_SEC`. Scattered across 4 docs. |
| 3 | **Port number lock table** | HIGH — blocks integration | 0.5h | Single canonical table referenced by all docs. Currently 3 conflicting sets. |
| 4 | **Risk vocabulary unification** | MEDIUM — blocks frontend | 1h | Frontend uses 5 levels (normal/low/medium/high/critical), API uses 3 risk bands + 3 severity levels. DEFERRED_FINDINGS #8 flags this as "will fire on first integration test." |
| 5 | **MRN/name scheme alignment** | MEDIUM — blocks frontend | 1h | Three incompatible conventions (DEFERRED_FINDINGS #9). Align to SYNTHETIC_DATA naming. |
| 6 | **Devpost submission copy** | LOW — needed at P3 | 2h | Title, tagline, description, built-with tags, story, challenges, what's next. JUDGE_HOOKS §3 has 5 tagline options but no full draft. |
| 7 | **CI/CD pipeline spec** | LOW — nice to have | 1h | GitHub Actions: lint (ruff), test (pytest), FHIR validate. BUILD_PLAN F1 mentions "CI stub" but no spec. |
| 8 | **EVALUATION.md (DECIDE-AI-lite)** | LOW — judge polish | 1h | JUDGE_HOOKS §1.1 hook H3 and §4 item 4 promise this. Not yet written. Low effort, high Mathur/Proctor signal. |

---

## 6. Overall Readiness

### What is strong
- **Clinical evidence base** is thorough, self-auditing, and correctly sourced.
- **Autonomy rule** is now consistent across all 12+ docs — the single most dangerous contradiction from Round 2 is resolved.
- **Tool names** are frozen and consistent.
- **Synthetic vital/lab tables** are clinically plausible and well-documented.
- **Judge hooks** are mapped 3+ per judge with concrete demo timestamps.
- **a2a-sdk decision** is made and documented with clear rationale.

### What needs work before build
- **Port numbers** must be locked (30 min fix, blocks everything).
- **DEMO_SCRIPT:59** wording ("biggest killer") must be fixed (5 min).
- **BUILD_PLAN:351** state machine naming must be updated (5 min).
- **SNOMED codes** 199223000 and 58532003 need correction or verification (1h).
- **LOINC urine output** code decision (9192-6 vs 9188-4) must be made (30 min).
- **RxNorm codes** 1659149 and 203134 need verification (30 min).
- **Scorecard** in PROJECT_BRIEF needs recalibration to 3 Devpost criteria (30 min).
- **Deferred findings #8 and #9** (risk vocab, MRN naming) will fire on first integration test.

### What needs work before submission
- **Marketplace listing** is REQUIRED (not optional). R01 is correctly the #1 risk. Discord outreach must happen immediately.
- **a2a-sdk API surface** (AgentExecutor class existence) must be verified at B7 start.
- **EVALUATION.md** should be written for Mathur/Proctor credibility.

### Probability of strong placement

With the planning set as-is after phase 2, and assuming the build executes cleanly:
- **3-criterion equal-weight scoring** (not /40): strong on AI Factor and Impact, competitive on Feasibility.
- **Marketplace listing gate** is the binary pass/fail risk. If R01 fires and KS-1 executes ("listing pending"), we may not advance to scoring at all.
- **Conditional on marketplace listing:** ~55-65% probability of top-3 placement. The dual-path (MCP + A2A) submission is a differentiator, and the clinical depth is above hackathon median.
- **Risk-adjusted (including R01 uncertainty):** ~40-50% probability of top-3.

The planning set is ready for build with the fixes enumerated above. Total fix effort: ~6-8 hours. The highest-leverage single action is resolving R01 (Prompt Opinion publishing flow) — it gates the entire submission.

---

*End of final review.*
