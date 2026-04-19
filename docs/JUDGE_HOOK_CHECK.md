# Vigil — Judge Hook Validation (P5)

Owner: integration-lead | Date: 2026-04-19

Validated against: `docs/JUDGE_HOOKS.md` hook matrix, actual implementation, and all public-facing materials (README.md, DEVPOST_SUBMISSION.md, frontend code).

---

## Validation method

Each hook from the JUDGE_HOOKS.md §2 hook map was verified by:
1. Locating the implementation in backend/frontend code
2. Confirming it would be visible on-screen during the demo
3. Checking the clinical claim is defensible (sources cited, thresholds documented)
4. Flagging any gap between the planning doc and reality

---

## 1. Piyush Mathur, MD — Cleveland Clinic

**Theme:** Postop deterioration, signal quality, no false alerts, DECIDE-AI rigor.

| Hook | Claim | Status | Evidence |
|------|-------|--------|----------|
| **H1** — "4.2M postop deaths/year" opener | Stat visible in landing page and Devpost | **CONFIRMED** | `frontend/app/page.tsx:34-38` — stat card "4.2M" with label "postoperative deaths per year", citation "Nepogodiev 2019". Also `README.md:16`, `DEVPOST_SUBMISSION.md:20,31`. |
| **H2** — Demo opens on postop CABG patient | PT-001 is a postop patient, vitals shown first | **CONFIRMED** | Demo script opens on patient roster, clicks PT-001 (stable) then PT-007 (deteriorating CABG). `docs/DEMO_SCRIPT.md:62-66`. |
| **H3** — DECIDE-AI-flavored evaluation | Evaluation table in repo | **PARTIAL** | No standalone `EVALUATION.md` exists. Evaluation table IS embedded in `README.md:353-365` with fields: Intended use, Target population, Data source, Known biases, Failure modes, Validation status. Sufficient but less visible than a standalone doc. |
| **H4** — FHIR R4 resources section | README lists all resources used | **CONFIRMED** | `README.md:140-170` — "FHIR R4 resources" section with LOINC mapping table, explicit "No custom extensions. Every resource is vanilla FHIR R4." |
| **H9** — Continuity-of-care language | OR→PACU→floor framing | **CONFIRMED** | `DEVPOST_SUBMISSION.md:31` — "warning signs appear 30–60 minutes before crisis." `README.md:340-347` — demo beat sheet shows progression. |
| **H11** — Local-validation honesty | Limitations documented | **CONFIRMED** | `README.md:361-365` — "Demo-ground-truth only. Local validation required before any clinical deployment." Also `DEVPOST_SUBMISSION.md:70` — "operational threshold…not externally validated." |

### Mathur verdict: **SERVED (5/6 hooks confirmed, 1 partial)**

**Risk:** H3 is embedded in README rather than a standalone doc. Low risk — Mathur will still see it. The "marginal lift" opening stat is the strongest hook.

**Clinical defensibility:** All thresholds cite published standards (MEWT Shields 2016, qSOFA Singer 2016). Hemodynamic trend rule explicitly documented as "not a published value" requiring prospective validation (`README.md:365`). This honesty IS the Mathur hook.

---

## 2. Josh Mandel, MD — Microsoft / SMART Health IT

**Theme:** FHIR R4 correctness, substitutability, real interop, standards-based.

| Hook | Claim | Status | Evidence |
|------|-------|--------|----------|
| **H4** — FHIR R4 resources section | No custom extensions, standard resources | **CONFIRMED** | `README.md:142` — "No custom extensions." LOINC mapping table at lines 155-169. Communication + AuditEvent use vanilla FHIR shapes (`backend/api/routes/patients.py:264-319`). |
| **H5** — "Substitutable clinical tools" phrase | In tagline/README | **PARTIAL** | Devpost tagline uses "0 code changes between wards" instead of literal "substitutable." `README.md:209` uses "substitutability thesis." The concept is clearly communicated but the exact phrase differs. |
| **H6** — CDS-Hooks-shaped A2A trigger | Architecture framing | **CONFIRMED** | `README.md:98-118` data flow shows event-triggered agent cycle. Not explicitly called "CDS-Hooks-shaped" in README but the architecture section describes the pattern. |
| **H10** — Closed-loop FHIR write (shared with Proctor) | Approve writes Communication + AuditEvent | **CONFIRMED** | `backend/api/routes/patients.py:270` — `await client.post_resource("Communication", comm_draft)`. Lines 275-319 — AuditEvent with clinician info. Frontend toast at `frontend/app/alerts/page.tsx:184`. |
| **H12** — Postpartum cameo, same tools | Zero code changes | **CONFIRMED** | `backend/criteria/mewt.py:43-74` — two threshold tables selected by trajectory parameter. `backend/mcp_server/tools/screen_vital_thresholds.py` — no ward-specific branching. No `if ward == "OB"` anywhere in codebase. |
| **H15** — "One build, many wards" framing | Capital-efficient platform | **CONFIRMED** | `DEVPOST_SUBMISSION.md:52` — "Same tools, different ward…zero code changes." `README.md:209` — substitutability section. |

### Mandel verdict: **SERVED (5/6 hooks confirmed, 1 partial)**

**Risk:** H5 wording is "0 code changes" not "substitutable." Low risk — the concept is the same and Mandel will immediately recognize it as the SMART substitutability thesis.

**Clinical defensibility:** FHIR R4 correctness is strong. All LOINC codes standard. Communication + AuditEvent are vanilla FHIR resources. 39 SHARP compliance tests prove header round-trip. MCP server advertises `ai.promptopinion/fhir-context` capability (`backend/mcp_server/server.py:85-97`).

**Potential issue:** JUDGE_HOOKS.md §1.2 mentions emitting a `RiskAssessment` FHIR resource. The actual implementation returns risk scoring as JSON in the tool output, not as a FHIR `RiskAssessment` resource written to HAPI. This is correct behavior (the tool is read-only), but if Mandel asks "where's the RiskAssessment?", point to the tool output format — it contains the same fields.

---

## 3. Joshua Hickey — Mayo Clinic

**Theme:** SBAR rigor, nurse workflow fit, operational thinking.

| Hook | Claim | Status | Evidence |
|------|-------|--------|----------|
| **H2** — Demo opens on postop patient (shared with Mathur) | Patient context shown | **CONFIRMED** | Demo script scene 2 opens on PT-001 stable patient. |
| **H4** — FHIR resources section (shared) | Clinical standards listed | **CONFIRMED** | `README.md:140-170` — includes SBAR (IHI) citation. |
| **H7** — SBAR shown verbatim, structured | S/B/A/R separated on screen | **CONFIRMED** | `backend/schemas.py:436-472` — `SBAR` pydantic model with 4 distinct fields. `frontend/app/alerts/page.tsx:104-122` — renders in 2-column grid with labeled sections. `frontend/app/patients/[id]/page.tsx` — SBAR card with 4 cells. |
| **H8** — "Who gets paged" ops diagram | Operational workflow shown | **PARTIAL** | `README.md:98-118` shows data flow (FHIR → MCP → Agent → Review Queue → Clinician → Communication). But no explicit "who gets paged" diagram with role assignment. The demo flow implicitly answers this: the nurse on the dashboard sees the alert, clicks approve, RRT is dispatched. |
| **H9** — Continuity-of-care framing (shared) | Episode-of-care language | **CONFIRMED** | `DEVPOST_SUBMISSION.md:31,39` — "post-surgical wards", monitoring across the postop window. |

### Hickey verdict: **SERVED (4/5 hooks confirmed, 1 partial)**

**Risk:** H8 — No standalone operational diagram. Medium risk for a PM judge. However, the demo itself IS the operational flow: alert appears → nurse reviews SBAR → clicks approve → Communication written. This is more powerful than a slide.

**Clinical defensibility:** SBAR format is correct — four distinct sections, each clearly labeled. The approve flow writes a real FHIR Communication, which is what a nurse would expect. The "Approve & send RRT" button labels match real clinical workflow (Rapid Response Team dispatch).

---

## 4. Stephon Proctor, PhD — CHOP

**Theme:** Agentic action, closed loop, ships real product, not passive dashboards.

| Hook | Claim | Status | Evidence |
|------|-------|--------|----------|
| **H6** — CDS-Hooks-shaped trigger (shared) | Agent as event-driven responder | **CONFIRMED** | A2A agent state machine (`backend/a2a_agent/sentinel.py`) runs 7-state cycle triggered by polling or manual tick. |
| **H10** — Clinician clicks Approve, FHIR write | Closed-loop action on screen | **CONFIRMED** | `backend/api/routes/patients.py:270,319` — writes Communication + AuditEvent to HAPI. `frontend/app/alerts/page.tsx:184` — toast: `"Communication ${res.alert_id} written — audit ${res.audit_id}"`. This is the **#1 highest-leverage hook**. |
| **H11** — Local-validation honesty (shared) | Limitations acknowledged | **CONFIRMED** | `README.md:361-365`, `DEVPOST_SUBMISSION.md:70`. |
| **H3** — DECIDE-AI evaluation (shared) | Evaluation table | **PARTIAL** | Embedded in README (not standalone). See Mathur section. |
| **Vocabulary** — "agentic, not dashboard" | Proctor's trigger word used | **CONFIRMED** | `DEVPOST_SUBMISSION.md:50` — "Closed-loop action, not a dashboard." `DEVPOST_SUBMISSION.md:74` — "This is what Stephon Proctor (CHOP) calls 'agentic, not dashboard.'" `DEVPOST_SUBMISSION.md:115` — explicitly avoids "dashboard" per rejection trigger. |

### Proctor verdict: **SERVED (4/5 hooks confirmed, 1 partial)**

**Risk:** Very low. H10 is the single highest-leverage hook and it's bulletproof — the approve flow writes real FHIR resources and the toast shows the IDs. Proctor's quote about AI that "can actually take action" is exactly what we demo.

**Clinical defensibility:** Agent never writes autonomously. Only the FastAPI approve endpoint writes to FHIR (`backend/api/routes/patients.py:7-8` — "The ONLY FHIR writes are in approve_alert_action"). This preserves the human-in-the-loop guarantee while still showing agentic behavior.

---

## 5. Alice Zheng, MD, MBA, MPH — Foreground Capital

**Theme:** Maternal health, postpartum, market size, racial disparities.

| Hook | Claim | Status | Evidence |
|------|-------|--------|----------|
| **H5** — Substitutable tools (shared) | Same tools, different ward | **CONFIRMED** | Zero code changes verified. See Mandel section. |
| **H12** — Postpartum cameo demo'd live | PT-009 sepsis + PT-010 hemorrhage | **CONFIRMED** | Demo script scenes 5-6 (`DEMO_SCRIPT.md:82-89`). PT-009 has lactate 4.2, WBC 18.4 (verified in data). PT-010 is postpartum hemorrhage trajectory. |
| **H13** — CDC ASE applied to postpartum | Sepsis criteria named | **CONFIRMED** | `backend/mcp_server/tools/flag_sepsis_onset.py` uses CDC ASE logic. Test `test_pt009_sepsis_suspected_cdc_ase` passes. `DEVPOST_SUBMISSION.md:46` names it. |
| **H14** — Maternal mortality disparities stat | Racial disparity mention | **NOT FOUND** | No mention of racial disparities in US maternal mortality in any public-facing material (README, Devpost, frontend). Only appears in JUDGE_HOOKS.md planning doc. **This is a gap.** |
| **H15** — Capital-efficient platform framing | One build, many wards | **CONFIRMED** | `DEVPOST_SUBMISSION.md:52` — "Same tools, different ward." |
| **260K stat** | Maternal mortality stat visible | **CONFIRMED** | `frontend/app/page.tsx:40-44` — "260K" stat card. `DEMO_SCRIPT.md:85` — "260K maternal deaths/year." `README.md:347`. |
| **Fourth trimester language** | Postpartum framing | **NOT FOUND in public materials** | Only in `docs/JUDGE_HOOKS.md` planning doc. Not in README, Devpost, or frontend. |

### Zheng verdict: **AT RISK (3/5 core hooks confirmed, 2 gaps)**

**Gaps requiring action:**

1. **H14 — Racial disparities.** JUDGE_HOOKS.md explicitly lists "No mention of disparities" as a rejection trigger. Adding one sentence to the Devpost description would close this:
   > *"In the US, Black women are 2.6× more likely to die from pregnancy-related causes (CDC MMWR 2023). Vigil's postpartum pathway monitors the fourth trimester — the postpartum window where most of these deaths occur."*

2. **"Fourth trimester" language.** Present only in planning docs. Should appear in Devpost and/or README in the maternal section.

**Clinical defensibility:** CDC ASE applied to postpartum is clinically sound. PT-009 data (lactate 4.2, WBC 18.4) satisfies the ASE organ dysfunction criteria. The same-tools-different-ward claim is verified — no ward-specific branching exists in the codebase.

---

## Summary matrix

| Judge | Hooks planned | Hooks confirmed | Hooks partial | Hooks missing | Verdict |
|-------|--------------|-----------------|---------------|---------------|---------|
| **Mathur** | 6 | 5 | 1 (H3 embedded) | 0 | **SERVED** |
| **Mandel** | 6 | 5 | 1 (H5 wording) | 0 | **SERVED** |
| **Hickey** | 5 | 4 | 1 (H8 no diagram) | 0 | **SERVED** |
| **Proctor** | 5 | 4 | 1 (H3 embedded) | 0 | **SERVED** |
| **Zheng** | 5+ | 3+ | 0 | 2 (H14 disparities, 4th trimester) | **AT RISK** |

---

## Last-mile fixes (recommended)

### Priority 1 — Close Zheng gaps (30 min)

1. **Add one sentence about racial disparities** to `docs/DEVPOST_SUBMISSION.md` in the "Inspiration" paragraph, after the WHO 2023 stat:
   > *"In the United States, Black women are 2.6× more likely to die from pregnancy-related causes than white women (CDC MMWR 2023). The fourth trimester — the 12-week postpartum window — is where most preventable maternal deaths occur."*

2. **Add "fourth trimester" to README.md** in the postpartum section, as a parenthetical:
   > *"…monitoring postpartum patients through the fourth trimester (the 12-week postpartum window)…"*

### Priority 2 — Strengthen Mathur's H3 (15 min)

3. **Create standalone `docs/EVALUATION.md`** by extracting the evaluation table from README.md. This makes it more visible and signals we know what DECIDE-AI is:
   ```
   # Vigil — Evaluation card (DECIDE-AI-lite)
   [copy table from README.md:355-365]
   ```

### Priority 3 — Polish Devpost test count (5 min)

4. **Update DEVPOST_SUBMISSION.md:76** — Claims "69 tests" but actual count is **312 tests**. Update to: "312 tests, including 39 SHARP compliance tests."

### Priority 4 — Optional: operational diagram for Hickey (30 min)

5. If time permits, add a simple ASCII/Mermaid diagram to README showing the escalation flow:
   ```
   Agent tick → 4 MCP tools → SBAR draft → Review queue → Nurse approves → Communication + AuditEvent → RRT dispatched
   ```

---

## Sign-off

| Item | Status |
|------|--------|
| All 5 judges have ≥3 confirmed hooks | **YES** (Zheng at minimum with 260K stat + postpartum cameo + same tools) |
| No judge has a gap rated >= Critical | **YES** (Zheng gaps are fixable in 30 min) |
| Every clinical claim is defensible | **YES** (all thresholds cite published standards, limitations documented) |
| Agent never writes FHIR autonomously | **YES** (only approve endpoint writes) |
| Demo script beats align with hook map | **YES** (verified against DEMO_SCRIPT.md §3) |

**Signed off by integration-lead, 2026-04-19.**
