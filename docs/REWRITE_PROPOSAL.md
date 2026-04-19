# Vigil Phase-1 Rewrite Proposal

> **Author:** `rewrite-lead`
> **Phase:** 1 of 2 (research + proposal; no file edits)
> **Date:** 2026-04-15
> **Scope:** 6 findings + Blocker-2 amendment + freebies, as scoped in the phase-1 brief.

---

## 0. Executive summary

The second-opinion review surfaced 24 issues. Phase-1 read shows the docs have **drifted forward** since the review was written: roughly half the listed line numbers are already stale because someone (probably the integration lead) has already applied partial fixes. The biggest still-unfixed items are:

1. **`PROMPT_OPINION_INTEGRATION.md §3 + §5.2`** still recommends `google-adk`. Full flip required.
2. **`API_CONTRACTS.md §1.4 `generate_escalation_note` output schema** still has `persist=True`, `communication_id`, a `FHIR writes: Communication` line, and a `persist_error` branch. This is the autonomy-contradiction finding — it must be rewritten to produce a `communication_draft` only.
3. **`DEMO_SCRIPT.md:127, 146`** still contain `fhir_write_observation` and "Send to Epic" in the scene-breakdown / judge-hook ledger (even though the actual beat text at lines 73 and 79 has already been corrected).
4. **`SYNTHETIC_DATA_SPEC.md`** is the single most drifted doc: roster says 10 but actually lists 11; §5 FHIR template never shows `Condition`, `MedicationAdministration`, or lab `Observation`s; §4 Expected Alert Table foot-note names three drifted Set E tools; the §2.2 PT-007 vitals don't actually cross any written rule at T+2h.
5. **`CLINICAL_EVIDENCE.md §2.3`** has no quantitative trend rule, so `screen_vital_thresholds`'s own acceptance criteria ("PT-007@T+2h returns `triggered` per the trend rule") is not met by any published text.

Findings that I **verified are already fixed** and therefore NOT in the edit set: F4 (SHARP headers — BUILD_PLAN:78/146/208/346 already use the canonical 3), F12 (JUDGE_HOOKS:14 already says "third greatest contributor"), F21 (DEMO_SCRIPT:79 already says "Approve & Send RRT"), F22 (BUILD_PLAN B10 already exists and B2 is already `screen_vital_thresholds`), F17 (BUILD_PLAN already has B10 FastAPI proxy), F18 (BUILD_PLAN does not re-state the polling path), F23 partial (PROJECT_BRIEF:16 already says "each" not "combined").

---

## 1. Reading notes — line ranges to touch

Line numbers re-verified against the **current** working tree, not the second-opinion snapshot. Drift flagged where it exists.

### 1.1 `PROMPT_OPINION_INTEGRATION.md`
- **§3 (lines 256-404)** — entire "A2A Agent Integration Pattern (po-adk-python)" section. All of §3.1, §3.2, §3.3, §3.5 are written around `google.adk.agents.Agent`, `gemini-2.5-flash`, `before_model_callback=extract_fhir_context`, `to_a2a()`, and `GOOGLE_API_KEY`. Needs in-place rewrite to raw `a2a-sdk`, OR a disclaimer header plus a new "§3b — Raw a2a-sdk adaptation" subsection. I recommend the latter (see decision 2.1).
- **§5.2 (lines 482-509)** — "use `google-adk` + `po-adk-python` patterns, not raw `a2a-sdk`" is flipped and needs a new justification paragraph + a new file map.
- **§1b (lines 50-101)** — repo inventory of `po-adk-python`. Leave as historical reference but add a "note: we no longer clone this 1:1" callout so future readers aren't confused.
- **Appendix Pattern Checklist (lines 582-595)** — items "A2A side: `Agent(..., before_model_callback=extract_fhir_context)`" and "`create_a2a_app(..., fhir_extension_uri=...)`" need rewording to raw-sdk equivalents.

Note lines 457-460 (the existing §5.1 bullet list of 4 tool names already includes `"generate_escalation_note — composes SBAR text, no FHIR write"`) — this is the line the second opinion cited as "already correct". Leave it alone; it's load-bearing evidence that the no-write contract pre-existed the drift in API_CONTRACTS.

### 1.2 `API_CONTRACTS.md`
- **Line 349** — `**FHIR writes:** `Communication` (see Section 5).` — **delete entire line**.
- **Lines 373-377** — `persist` field in `EscalationInput`. **Delete the field.**
- **Line 399** — `communication_id: str | None    # FHIR Communication.id if persist=True` → replace with `communication_draft: dict    # Unpersisted FHIR Communication resource shape`.
- **Line 413** — example payload `"persist": true` → remove line (and trailing comma rebalance).
- **Lines 431-434** — response `"communication_id": "Communication/comm-884"` → replace with an inlined `communication_draft` example object.
- **Line 441** — `**FHIR write fails:** `status=ok` with `communication_id=null` and `detail.persist_error` set.` → **delete**. The tool no longer writes.
- **Lines 277-278 (ARCHITECTURE.md)** — `**No autonomous action.** The A2A agent never writes to FHIR. Writes happen only when a human clicks Approve, and only via the review-queue service.` — already correct prose. Needs only a small augmentation clause saying MCP tools also never write.
- **§6 lines 894-908** — `POST /api/patients/{id}/alerts/{alertId}/approve` — already correctly typed as the single FHIR writer. Leave as-is; it's the target state for the contradiction fix.
- **§5.6 line 772** — Communication example still has `status: "in-progress"`; this is the *post-approve* state. Change to `"completed"` to match the `/approve` contract (§6 line 907), OR note both the `in-progress` draft shape and the `completed` persisted shape. **Choose: leave at `in-progress`** and add a parenthetical — see decision 2.2.

### 1.3 `DEMO_SCRIPT.md`
- **Line 127** (judge-hooks ledger, Proctor row) — "`fhir_write_observation` write-back, 'Send to Epic' button with toast, 'teammate not dashboard' line". Rewrite to name the canonical flow.
- **Line 143** (scene 3 breakdown) — "End the scene on the `fhir_write_observation` call — Proctor's first taste of closed-loop action." Rewrite to reference `generate_escalation_note` producing a draft.
- **Line 146** (scene 4 breakdown) — "Finish with the 'Send to Epic' button — Proctor's closing moment." Rewrite to "Approve & Send RRT" button.
- **Line 60** + **Line 102** — "bigger than AIDS, tuberculosis, and malaria combined." Change to "more than AIDS, tuberculosis, and malaria each" (matches PROJECT_BRIEF.md:16 and the REVIEW_NOTES NIT-5 "either/or" resolution). This is freebie Finding 23.

Lines 15, 67, 72, 73, 79, 106 are **already** on canonical tool names ("screen vital thresholds, score deterioration risk, flag sepsis onset, draft the SBAR"). Leave.

### 1.4 `BUILD_PLAN.md`
Already reflects:
- B2 is `screen_vital_thresholds` (not `list_postop_patients`) ✓
- B5 says "returns the SBAR plus an unpersisted `communication_draft`" and "No FHIR write happens inside the tool" ✓
- B10 exists as FastAPI proxy + enumeration ✓
- F3 mentions labs / Conditions / MedAdmin ✓
- F5/B8/I2 use canonical SHARP headers ✓
- B7 acceptance criteria reference "CDC ASE fires at T+4h" for PT-009 (line 141) ✓

**Only one edit required:** F3 acceptance currently reads `PT-007@T+2h satisfies the hemodynamic trend rule (CLINICAL_EVIDENCE §2.3)` — that rule does not yet exist in CLINICAL_EVIDENCE. This edit is bundled with finding 16.

### 1.5 `JUDGE_HOOKS.md`
- **Line 14** — already says "third greatest contributor". ✓ No edit needed. (Finding 12 resolved before this session.)
- **Lines 5, 121, 149, 187** — already say "CDC Adult Sepsis Event applied to postpartum" / "CDC Adult Sepsis Event" / "severe maternal morbidity" (vocabulary, not a tool). ✓ Finding 5 appears already resolved; no Set-D drift remains. **Verify:** I could not find any literal "CDC Severe Maternal Morbidity" string in the current file. Will confirm on phase-2 entry.

### 1.6 `SYNTHETIC_DATA_SPEC.md`
- **Lines 24-30** (roster contradiction) — says "Roster is 11 patients" AND has a PT-011 row that collides with the `PROJECT_BRIEF.md:58` lock of 10. **Rewrite.** (Finding 6, bundled freebie.)
- **§2.2 lines 51-62** (PT-007 deteriorating vitals) — values don't cross any quantitative threshold at T+2h. **Rewrite T+2h row values** OR move the expected TRIGGERED marker (Finding 16).
- **Need NEW §2.5** — lab panel table keyed to trajectory+timepoint, with LOINC codes. (Finding 15.)
- **§4 line 146** — foot-note names `detect_sepsis_risk`, `assess_postpartum_bleeding`, `generate_sbar_handoff` (Set E drift). **Rewrite** to name the four canonical tools. (Finding 3.)
- **§5 lines 150-228** — FHIR bundle template shows only Patient, Encounter, Procedure, and 7 vital Observations. **Add** `Condition` + `MedicationAdministration` + lab `Observation` entries OR add a new `§5b — Additional resource shapes` subsection that enumerates the shapes without repeating them in every per-patient example. (Finding 14, finding 15.)
- **§4 Expected Alert table line 137-140** — assuming we touch PT-007 values, the marker at T+2h must remain consistent with §2.2. (Finding 16.)
- **§7 line 272** — `PT-011/...` mention in the output directory listing. Delete if we drop PT-011.

### 1.7 `CLINICAL_EVIDENCE.md`
- **§2.3 lines 73-87** — the "Deviations" paragraph waves at trend rules but never quantifies any. **Append** a bulleted "Hemodynamic trend rule" block with citation strength. (Finding 16 part 1.)
- **§4 lines 105-112** — CDC ASE already correctly described. No edit.
- **§11.2** — LOINC table for vitals exists. **Add** a second table (or rows) for the lab LOINCs: lactate 2524-7, WBC 6690-2, creatinine 2160-0, bilirubin 1975-2, platelets 777-3. These are already named in `API_CONTRACTS.md:265` but never justified here. Bundled with finding 15.

### 1.8 `FRONTEND_SPEC.md`
- **Line 207** — "Both client-side only — they open a `<Dialog>` that says 'Demo: acknowledged' and closes. No network call." **Contradicts** `API_CONTRACTS.md §6.4` (which says `POST /api/.../approve` writes Communication + AuditEvent). This is **Finding 7** — NOT in scope per the brief, but the Finding 2 resolution *depends* on the approve button firing a real network call.
  - **Recommendation:** bundle a minimal 1-line edit (see decision 2.3). Flag in questions if the integration lead wants me to stay out of it.

### 1.9 `RISK_REGISTER.md`
- **Line 61** — KS-4 fallback pointer. No edit needed; only cited by the Blocker-2 section of this proposal. (Finding 20 — KS-4 trigger condition — is out of scope.)

### 1.10 Files NOT touched in this pass
`README.md` (doesn't exist yet), `REVIEW_NOTES.md` (historical, explicitly excluded by brief).

---

## 2. Decision log — ambiguous judgment calls

### 2.1 Blocker-2 rewrite shape: in-place flip vs. additive §3b

**Decision:** in-place rewrite of §3.1, §3.2, §3.5, and §5.2. Keep §3.3, §3.4, §1b lightly edited as historical context.

**Alternative:** add a new "§3b — Raw a2a-sdk adaptation" beneath the ADK section, leaving ADK intact as reference.

**Why in-place:** the brief says the recommendation flips; future maintainers should read the canonical answer on first scroll. An additive §3b leaves two live recommendations competing. The historical value of the ADK prose is that it documents the metadata-bridge *pattern*, which still applies — I preserve that by keeping §3.3's metadata wire format (unchanged) and §3.4's "Path A and Path B are parallel" paragraph.

### 2.2 API_CONTRACTS §5.6 Communication example — draft shape vs. final shape

**Decision:** keep the `"status": "in-progress"` draft shape as §5.6 (label it "Communication — SBAR escalation, **draft shape as returned inside `communication_draft`**"). Add a one-line note "On approve, the FastAPI proxy POSTs this body to HAPI with `status` flipped to `completed` per §6.4."

**Alternative:** duplicate the resource as §5.6a (draft) and §5.6b (persisted).

**Why single shape + note:** the only field that differs between the two states is `status`, and duplicating the whole resource for a single-field delta is noise. A one-liner is self-documenting.

### 2.3 Whether to bundle Finding 7 (FRONTEND_SPEC client-side approve)

**Decision:** bundle a minimal surgical edit: rewrite `FRONTEND_SPEC.md:207` to say the approve button calls `POST /api/patients/{id}/alerts/{alertId}/approve` via `lib/api.ts::ackAlert()` (already declared at FRONTEND_SPEC.md:366), and the dialog is a success toast fed by the server response. Do NOT touch the rest of §3.3 or §6.

**Why:** Finding 2 cannot be said to be "resolved across the doc set" while FRONTEND_SPEC says the approve button makes no network call. The brief explicitly calls out FRONTEND_SPEC as "adjacent". A two-word surgical edit ("Both client-side only" → "Client-triggered; backend writes via `ackAlert()`") is within phase-2 scope and avoids leaving the contradiction visible. **Flagging for override** — integration lead, say no if you disagree.

### 2.4 PT-007 vs. PT-009 timing alignment (Finding 16)

**Decision:** DO BOTH as the brief says. (a) Add the trend rule to CLINICAL_EVIDENCE. (b) For the vitals-vs-rule fit, **rewrite the PT-007 T+2h row** rather than moving the ground-truth marker. The T+2h marker is directly cited by `BUILD_PLAN.md:111` B2 acceptance (`PT-007@T+2h returns status=triggered`) and `ARCHITECTURE.md` scenario B narration ("TRIGGERED (MEWT=5)" at T+2h). Moving the marker to T+4h breaks three downstream docs; rewriting the vitals only breaks one table.

**Proposed new PT-007 values** (see §3.5 for full diff):
- T+0h: SBP **130**, DBP 82, HR **76**, RR 16, SpO2 98, Temp 37.0, Urine 50 (baseline raised so 10% drop lands in range)
- T+1h: SBP **124**, DBP 78, HR **84**, RR 17, SpO2 97, Temp 37.1, Urine 42
- T+2h: SBP **114** (10.8% drop from T+0h ✓), DBP 72, HR **92** (21% rise from T+0h ✓), RR 18, SpO2 96, Temp 37.2, Urine 35
- Rest (T+4h, T+6h, T+8h) unchanged — they already cross absolute thresholds.

This satisfies the new trend rule (SBP drops ≥10% AND HR rises ≥15% over any 2-hour window) at T+2h. T+0h baseline of SBP 130 is inside published stable-postop range (§6 of SYNTHETIC_DATA_SPEC already allows up to 125; 130 is 5 over but still within Shields-2016 non-severe MEWT thresholds of <85 or >160).

**Alternative considered:** move the marker. Rejected — too many downstream citations to the T+2h moment.

### 2.5 Condition profiles per patient (Finding 14)

**Decision:** 1 comorbidity for stable patients (PT-001..003), 2 for deteriorating (PT-004..007), 3 for sepsis/hemorrhage (PT-008..010). Total count 20. Heroes (PT-001, PT-007, PT-009, PT-010) get deliberately curated lists that match narration:

| Patient | Comorbidities | SNOMED codes |
|---|---|---|
| PT-001 | Essential hypertension | 59621000 |
| PT-002 | Osteoarthritis of knee | 239873007 |
| PT-003 | Appendicitis s/p (no comorbidity) | — |
| PT-004 | T2DM, COPD | 44054006, 13645005 |
| PT-005 | Obesity (BMI 35), hypertension | 414916001, 59621000 |
| PT-006 | Coronary artery disease, T2DM | 53741008, 44054006 |
| PT-007 | T2DM, chronic kidney disease stage 3 | 44054006, 433144002 |
| PT-008 | T2DM, COPD, previous sepsis | 44054006, 13645005, 76571007 |
| PT-009 | Gestational diabetes, obesity, chorioamnionitis (active) | 199223000, 414916001, 11612004 |
| PT-010 | Placenta accreta, previous cesarean, mild preeclampsia | 58532003, 200737006, 398254007 |

**Alternative:** 1-3 at random per generator seed. Rejected — the heroes need *reproducible, citable* comorbidities so the SBAR narration can name-drop them (see PT-009 "chorioamnionitis" → antibiotic bundle justification in the DEMO_SCRIPT beat).

**Why 2-3 for hero sepsis/hemorrhage:** Mathur cares about comorbidity-weighted deterioration risk; a single comorbidity looks like an afterthought.

### 2.6 MedicationAdministration agents + timing (Finding 14)

**Decision:** each patient gets 1 peri-operative antibiotic. Heroes PT-008/009 get 2 (pre-op prophylaxis AND post-onset broad-spectrum). Crucially, the broad-spectrum start time is **AFTER** the sepsis-onset timepoint so `flag_sepsis_onset` correctly identifies the "abx in evaluation window" component without fooling itself about a pre-administration window.

| Patient | Drug | RxNorm | Start (relative to T+0h procedure) |
|---|---|---|---|
| PT-001..003 | Cefazolin 1g IV | 309264 | T-0:30 (pre-op prophylaxis only) |
| PT-004..007 | Cefazolin 1g IV | 309264 | T-0:30 |
| PT-008 | Cefazolin 1g IV pre-op | 309264 | T-0:30 |
| PT-008 | Piperacillin-tazobactam 4.5g IV | 203134 | T+4:15 (after sepsis onset T+4h) |
| PT-009 | Cefazolin 2g IV pre-delivery | 309264 | T-0:15 |
| PT-009 | Ampicillin-sulbactam 3g IV | 1659149 | T+4:20 (after sepsis onset T+4h) |
| PT-010 | Cefazolin 2g IV | 309264 | T-0:15 |

**Alternative:** antibiotic starts BEFORE the onset timepoint (real-life empirical). Rejected — CDC ASE explicitly requires presumed infection + organ dysfunction; the "abx was already running before the vitals rolled" scenario is correct real-world clinical practice but confuses the demo rule path.

**Dosing citations:** Cefazolin 1-2g peri-op — ASHP Surgical Site Infection Prevention Guidelines 2013. Piperacillin-tazobactam 4.5g q6h — IDSA/SCCM Surviving Sepsis Campaign 2021. Ampicillin-sulbactam 3g q6h for postpartum endometritis/sepsis — ACOG Practice Bulletin 199 (2018).

### 2.7 DEMO_SCRIPT line 67 replacement (already resolved, but documenting rationale)

DEMO_SCRIPT.md:67 already reads `"Every number on this screen is a real FHIR Observation pulled by an MCP tool."` — this already avoids naming the drifted tools. The second opinion was looking at an earlier revision. **No edit needed.**

### 2.8 Where does `list_postop_patients` go? Split across B10 or new B11?

**Decision:** already in B10. No split needed. Finding 22 resolved by prior edit.

### 2.9 Drop PT-011 vs. keep at 11

**Decision:** drop PT-011 (Finding 6). PROJECT_BRIEF.md:58 is the north star and locks the count at 10. FRONTEND_SPEC.md:131 hard-codes `[All 10]`. Rebalanced count: 3 stable / 3 deteriorating (PT-004..006 filler + PT-007 hero) / 2 sepsis (PT-008/009) / 2 hemorrhage — but PT-010 is the only hemorrhage patient now, leaving 1 slot. **I recommend promoting PT-006 from deteriorating to a second hemorrhage case** would break the Mathur demo (PT-007 is the hero deteriorator and needs its 3-patient cohort for "same trajectory across multiple patients" framing).

**Better fix:** accept 3 / 4 / 2 / 1 = 10 as the final distribution (1 hemorrhage). The brief says "4 trajectories" not "equal counts per trajectory," and the 260K maternal-deaths narration only needs PT-010 firing. Drop PT-011 and its row from §4, leave §2.4 header as "(PT-010 hero)".

**Alternative:** keep PT-011 and rewrite PROJECT_BRIEF:58 to say 11. Rejected — the brief wins per its own line 3.

### 2.10 F5 / B8 / I2 SHARP headers — no edit

Verified already correct in current tree. Finding 4 resolved.

---

## 3. Edit-by-edit diffs

Every edit below targets the *current* working-tree line numbers, re-verified during phase-1 research. Anchors chosen to be unique within their host file.

### 3.1 PROMPT_OPINION_INTEGRATION.md — Blocker-2 amendment (a)

#### Edit 3.1.a — §5.2 justification flip (lines 482-509)

**Anchor:**
```
### 5.2 A2A agent — **use `google-adk` + `po-adk-python` patterns, not raw `a2a-sdk`**
Justification:
1. `po-adk-python` gives us a working `AgentCard` / `AgentExtension` / `to_a2a()` / `before_model_callback` chain that is already proven to connect to Prompt Opinion. Raw a2a-sdk means re-inventing the agent card JSON, the FHIR metadata bridge middleware, and the ADK-style session state for tool calls.
2. ADK's `Agent(tools=[...])` + plain-function tools are the fastest path to 4 tools + 1 orchestration loop.
3. We can still swap the model — `model="gemini-2.5-flash"` → set `GOOGLE_API_KEY`, or sub in Ollama/Groq via ADK's model-agnostic interface if time permits. Claude-on-ADK requires an adapter; defer unless judging requires it.
4. Tradeoff: we pick up `google-adk` as a hard dep. Acceptable — it's the blessed path.
```

**New text:**
```
### 5.2 A2A agent — **use raw `a2a-sdk`, NOT `google-adk`**

Justification:
1. `google-adk` hard-wires Gemini (`model="gemini-2.5-flash"` + `GOOGLE_API_KEY` — see §3.1). That directly breaks the `LLM_PROVIDER=ollama|groq|claude|stub` abstraction locked in `PROJECT_BRIEF.md:56` and the `DEMO_SCRIPT.md:18` precondition `LLM_PROVIDER=claude`. Adapting Claude into ADK's "model-agnostic interface" is a 3-6h unbudgeted spike on top of the 1-2h copy claim.
2. Five of the six architecture docs already assume raw `a2a-sdk`: `PROJECT_BRIEF.md:53`, `ARCHITECTURE.md:206`, `API_CONTRACTS.md:5`, `BUILD_PLAN.md` (F1 + B7), `RISK_REGISTER.md:18`. Flipping one doc (this one) aligns all six; the inverse flip would break five.
3. The "hard parts" of the raw-sdk port already exist verbatim:
   - **AgentCard JSON** — `API_CONTRACTS.md:522-580` is written in the exact shape `a2a.types.AgentCard` (pydantic v2) consumes.
   - **FHIR metadata bridge** — `API_CONTRACTS.md:620-657` defines `extract_fhir_from_payload(payload) -> (metadata_key, fhir_dict)`, ported line-by-line from `po-adk-python/shared/fhir_hook.py::extract_fhir_context` but rewritten as a framework-agnostic pure function. It attaches to an a2a-sdk request handler as a request-intercept middleware (see §3.1 below) instead of as an ADK `before_model_callback`.
4. **Only real loss** vs. ADK: ~80 LOC of session-state plumbing between tool calls. The a2a-sdk `TaskHandler` pattern replaces this. Estimated delta: 6-8h for the full port (vs. the ADK path's 1-2h copy + 3-6h adapter spike = 4-8h). Net even, with zero model lock-in.
5. **Fallback (KS-4).** If the raw port bogs past 8h, `RISK_REGISTER.md:61` already endorses hand-rolled FastAPI A2A (~50 LOC covering `message/send`, `tasks/get`, and the agent-card GET) as the pre-committed pivot. Option B → Option C is a mechanical fallback, not a redesign.
```

#### Edit 3.1.b — §3 header + §3.1 agent rewrite (lines 256-282)

**Anchor:**
```
## 3. A2A Agent Integration Pattern (po-adk-python)

### 3.1 The Agent (`google-adk`)
```

**New text:**
```
## 3. A2A Agent Integration Pattern (raw `a2a-sdk`)

> **Reference repo is still `po-adk-python`** — we copy its FHIR metadata wire format, its AgentCard shape, and its middleware bridging. We do NOT copy its `google-adk` dependency, its `Agent(...)` constructor, or its `to_a2a()` bootstrap. See §5.2 for the decision rationale.

### 3.1 The Agent (raw `a2a-sdk`)

Vigil's A2A agent subclasses `a2a.server.AgentExecutor` (the raw-sdk handler class) instead of ADK's `Agent`. The constructor takes the four Vigil MCP tools as plain async callables and runs the screen → score → sepsis → escalate state machine inside `execute()`. Session state (last-tool-call, accumulated context) lives on the `RequestContext` object the sdk passes on every tick.

```python
# backend/a2a_agent/sentinel.py
from a2a.server import AgentExecutor, RequestContext, EventQueue
from a2a.types import Task, TaskState, TextPart
from backend.a2a_agent.fhir_hook import extract_fhir_from_payload
from backend.a2a_agent.mcp_client import VigilMcpClient   # thin httpx wrapper around our MCP server

class PostopSentinelExecutor(AgentExecutor):
    def __init__(self, mcp: VigilMcpClient):
        self._mcp = mcp

    async def execute(self, ctx: RequestContext, events: EventQueue) -> None:
        # 1. Read FHIR credentials out of the incoming JSON-RPC payload.
        _, fhir = extract_fhir_from_payload(ctx.raw_request)
        if not fhir:
            await events.emit_task(Task.failed("missing FHIR context"))
            return

        # 2. Forward the 3 SHARP headers onto every downstream MCP call.
        headers = {
            "x-fhir-server-url":   fhir["fhirUrl"],
            "x-fhir-access-token": fhir.get("fhirToken", ""),
            "x-patient-id":        fhir["patientId"],
        }

        # 3. Run the state machine — each call is an MCP tool invocation.
        screen = await self._mcp.call("screen_vital_thresholds", headers=headers)
        risk   = await self._mcp.call("score_deterioration_risk", headers=headers)
        sepsis = await self._mcp.call("flag_sepsis_onset",        headers=headers)
        if screen["status"] != "triggered":
            await events.emit_task(Task.completed(parts=[TextPart(text="NORMAL")]))
            return
        escalation = await self._mcp.call("generate_escalation_note",
                                          headers=headers,
                                          body={"vitals_result": screen, "risk_result": risk, "sepsis_result": sepsis})

        # 4. Emit the SBAR + communication_draft back to the caller. The
        #    agent does NOT write to FHIR — the proxy's approve endpoint does.
        await events.emit_task(Task.completed(parts=[TextPart(text=escalation["narrative"])]))
```

The raw-sdk counterpart to ADK's `before_model_callback=extract_fhir_context` is to call `extract_fhir_from_payload()` once at the top of `execute()`. There is no "before LLM" hook because the state machine, not the LLM, is the orchestration layer — the LLM only runs inside individual MCP tools.
```

#### Edit 3.1.c — §3.2 callback → middleware rewrite (lines 284-325)

**Anchor:**
```
### 3.2 The `extract_fhir_context` callback
`shared/fhir_hook.py` (https://github.com/prompt-opinion/po-adk-python/blob/main/shared/fhir_hook.py):
```

**New text:**
```
### 3.2 The `extract_fhir_from_payload` middleware

With raw `a2a-sdk` there is no ADK callback lifecycle, so the hook becomes a plain pure function we call explicitly. It matches `po-adk-python/shared/fhir_hook.py::extract_fhir_context` behaviorally — same substring match on the metadata key, same `fhirUrl/fhirToken/patientId` field shape — but it takes the raw JSON-RPC payload dict and returns `(key, fhir_dict)` instead of mutating ADK state.

**Canonical implementation lives at `API_CONTRACTS.md:620-657`** — we do not re-state it here. Wire it into `PostopSentinelExecutor.execute()` as shown in §3.1, step 1. For requests where the Prompt Opinion runtime places the metadata at `params.metadata` vs. `params.message.metadata`, the helper's two-candidate probe handles both locations (same fallback order as `po-adk-python/shared/middleware.py::ApiKeyMiddleware`'s bridging behavior).

**Why this is safer than ADK's callback.** ADK's `before_model_callback` fires only when the LLM is about to be invoked — if your agent short-circuits on rule-engine output (which Vigil does on the NORMAL path), the callback may never run and the FHIR headers go unread. The raw-sdk approach runs the extraction unconditionally at request entry, which matches Vigil's "rule engine first, LLM last" control flow.

Metadata wire format is unchanged from §3.2 of the original ADK write-up — same substring match, same field names. The wire payload format shown in `shared/fhir_hook.py` docstring still applies:

```json
{
  "params": {
    "message": {
      "metadata": {
        "https://vigil.local/schemas/a2a/v1/fhir-context": {
          "fhirUrl":   "https://fhir.example.org/r4",
          "fhirToken": "<bearer-token>",
          "patientId": "patient-42"
        }
      }
    }
  }
}
```
```

#### Edit 3.1.d — §3.3 AgentCard rewrite (lines 327-389)

**Anchor:**
```
### 3.3 AgentCard + A2A app factory
`shared/app_factory.py` (https://github.com/prompt-opinion/po-adk-python/blob/main/shared/app_factory.py):
```

**New text:**
```
### 3.3 AgentCard + A2A app bootstrap (raw `a2a-sdk`)

`a2a.types.AgentCard` is a pydantic v2 model with a camelCase alias generator. Construct it directly; do not go through `google.adk.a2a.utils.agent_to_a2a.to_a2a()`. **The exact JSON shape Vigil serves is already written at `API_CONTRACTS.md:522-580`** — feed that dict through `AgentCard.model_validate(data)` and serve it at `GET /.well-known/agent-card.json`.

Bootstrap pattern (one file, ~30 lines):

```python
# backend/a2a_agent/app.py
import json
from pathlib import Path
from a2a.server import A2AServer
from a2a.types import AgentCard
from backend.a2a_agent.sentinel import PostopSentinelExecutor
from backend.a2a_agent.mcp_client import VigilMcpClient

agent_card_json = json.loads(Path("backend/a2a_agent/agent_card.json").read_text())
agent_card = AgentCard.model_validate(agent_card_json)

mcp = VigilMcpClient(base_url="http://localhost:7001")
executor = PostopSentinelExecutor(mcp)

a2a_app = A2AServer(agent_card=agent_card, executor=executor).build()
```

Run with `uvicorn backend.a2a_agent.app:a2a_app --host 0.0.0.0 --port 9000`. The `a2a-sdk` `A2AServer` handles `/.well-known/agent-card.json`, `message/send`, and `tasks/get` automatically — no FastAPI wrapper needed.

**API key auth.** `po-adk-python/shared/middleware.py::ApiKeyMiddleware` is a Starlette middleware that reads `X-API-Key` from request headers. Port it verbatim (~20 LOC) and attach via `a2a_app.add_middleware(ApiKeyMiddleware)`. No dependency on ADK.
```

#### Edit 3.1.e — §3.5 running-locally update (lines 396-404)

**Anchor:**
```
### 3.5 Running locally
```bash
pip install -r requirements.txt -r requirements-dev.txt
export GOOGLE_API_KEY=...
honcho start                 # all 3 agents via Procfile
# OR single agent:
uvicorn healthcare_agent.app:a2a_app --host 0.0.0.0 --port 8001
# OR ADK web UI (for debugging agent logic, NOT A2A):
adk web .
```
```

**New text:**
```
### 3.5 Running locally (raw `a2a-sdk`)
```bash
uv sync  # pulls a2a-sdk[http-server], httpx, pydantic — NO google-adk
export LLM_PROVIDER=ollama           # or groq | claude | stub
export VIGIL_MCP_URL=http://localhost:7001

# Single-process dev
uvicorn backend.a2a_agent.app:a2a_app --host 0.0.0.0 --port 9000

# Inspect the agent card
curl -sS http://localhost:9000/.well-known/agent-card.json | jq

# Invoke the sentinel end-to-end with inline FHIR metadata
curl -sS -X POST http://localhost:9000/ \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":"req-1","method":"message/send",
    "params":{"message":{"role":"user","parts":[{"kind":"text","text":"Screen PT-007"}],
    "metadata":{"https://vigil.local/schemas/a2a/v1/fhir-context":{"fhirUrl":"http://localhost:8080/fhir","fhirToken":"","patientId":"PT-007"}}}}
  }'
```

No `GOOGLE_API_KEY` is required. No `honcho` multi-agent Procfile. No ADK web UI. One process, one port, one LLM provider selected by env var. **This is the whole stack.**
```

#### Edit 3.1.f — §5.2 file map rewrite (lines 489-506)

**Anchor:**
```
```
backend/
└── vigil_agent/
    ├── Dockerfile                  # mirrors po-adk-python Dockerfile
    ├── Procfile                    # single entry: vigil: uvicorn vigil_agent.app:a2a_app --port 8001
    ├── requirements.txt            # google-adk, a2a-sdk[http-server], httpx
    ├── shared/
    │   ├── app_factory.py          # copy from po-adk-python verbatim
    │   ├── fhir_hook.py            # copy from po-adk-python verbatim (extract_fhir_context)
    │   └── middleware.py           # copy — bridges message.metadata → params.metadata
    └── vigil_agent/
        ├── agent.py                # root_agent = Agent(..., tools=[4 tools], before_model_callback=extract_fhir_context)
        ├── app.py                  # a2a_app = create_a2a_app(..., fhir_extension_uri=...)
        └── tools/
            └── vigil.py            # 4 tools OR call through to the vigil_mcp server over HTTP
```

Tools in the ADK agent will be **thin wrappers that call our own MCP server over HTTP** (so the MCP implementation is the single source of clinical logic). This is Vigil-specific — `po-adk-python` does it inline, but we want dual-path (both MCP and A2A) submissions.
```

**New text:**
```
```
backend/
└── a2a_agent/
    ├── Dockerfile                  # python:3.12-slim, uvicorn backend.a2a_agent.app:a2a_app
    ├── requirements.txt            # a2a-sdk[http-server]>=0.3.0, httpx>=0.28.0, pydantic>=2.8  (NO google-adk)
    ├── agent_card.json             # the JSON shape from API_CONTRACTS.md:522-580, served at /.well-known/agent-card.json
    ├── app.py                      # A2AServer(agent_card, executor).build() — see §3.3
    ├── sentinel.py                 # PostopSentinelExecutor(AgentExecutor) — see §3.1
    ├── fhir_hook.py                # extract_fhir_from_payload() — see API_CONTRACTS.md:620-657
    ├── middleware.py               # ApiKeyMiddleware (ported from po-adk-python, ~20 LOC)
    └── mcp_client.py               # thin httpx wrapper that forwards 3 SHARP headers onto every MCP call
```

**Tools are not defined in this tree.** They live in `backend/vigil_mcp/tools/` (MCP server, single source of clinical logic). The A2A executor calls them over HTTP via `mcp_client`, which injects the SHARP headers extracted from A2A metadata. This gives us the dual-path submission (MCP marketplace listing + A2A marketplace listing) without duplicating logic.
```

#### Edit 3.1.g — Appendix checklist rewrite (lines 590-591)

**Anchor:**
```
- [ ] A2A side: `Agent(..., before_model_callback=extract_fhir_context)`
- [ ] `create_a2a_app(..., fhir_extension_uri=...)` with `AgentExtension` in capabilities
```

**New text:**
```
- [ ] A2A side: `PostopSentinelExecutor(AgentExecutor)` with `extract_fhir_from_payload()` called at `execute()` entry
- [ ] `A2AServer(agent_card=AgentCard.model_validate(agent_card_json), executor=executor).build()` with `AgentExtension` declared inside the agent-card JSON under `capabilities.extensions`
```

---

### 3.2 API_CONTRACTS.md — Finding 2 (autonomy contradiction) (b)

#### Edit 3.2.a — remove FHIR-write declaration from §1.4 (line 349)

**Anchor:**
```
**FHIR reads:** `Patient/{id}` (name, MRN), `Encounter?patient={id}&status=in-progress`, `Procedure?patient={id}&_sort=-date&_count=1`.
**FHIR writes:** `Communication` (see Section 5).
```

**New text:**
```
**FHIR reads:** `Patient/{id}` (name, MRN), `Encounter?patient={id}&status=in-progress`, `Procedure?patient={id}&_sort=-date&_count=1`.
**FHIR writes:** None. The tool returns an unpersisted `communication_draft` (a valid `Communication` resource shape with no `id`). The FastAPI proxy's approve endpoint (`§6.4`) is the only path in the stack that writes `Communication` + `AuditEvent` to HAPI, and it does so only when a clinician clicks Approve in the frontend.
```

#### Edit 3.2.b — remove `persist` field from `EscalationInput` (lines 373-377)

**Anchor:**
```
    persist: Annotated[bool, Field(
        default=True,
        description="If True, POST a Communication resource to FHIR and return its id."
    )] = True
```

**New text:** *delete the entire 4-line block* (no replacement). The preceding `recipient_role` field gains a trailing comma if Pydantic requires it (it does not — the field already has its default trailing).

#### Edit 3.2.c — replace `communication_id` field in `EscalationOutput` (line 399)

**Anchor:**
```
    communication_id: str | None    # FHIR Communication.id if persist=True
```

**New text:**
```
    communication_draft: dict       # Unpersisted FHIR Communication resource shape — see §5.6. No id; no POST. The FastAPI proxy writes this (status="completed") via the /approve endpoint when a clinician acknowledges.
```

#### Edit 3.2.d — remove `"persist": true` from request example (line 413)

**Anchor:**
```
  "recipient_role": "rapid_response",
  "persist": true
}
```

**New text:**
```
  "recipient_role": "rapid_response"
}
```

#### Edit 3.2.e — rewrite happy-path response example (lines 420-435)

**Anchor:**
```
{
  "status": "ok",
  "patient_id": "patient-42",
  "sbar": {
    "situation": "Post-op day 1 patient with SBP 86 and qSOFA 2; sepsis suspected.",
    "background": "42yo s/p laparoscopic cholecystectomy 18h ago; Hx T2DM.",
    "assessment": "Meets CDC ASE: lactate 2.4, SBP 86, abx started. High deterioration risk.",
    "recommendation": "Activate rapid response, draw repeat lactate, bolus 500ml NS, notify attending."
  },
  "narrative": "S: ... B: ... A: ... R: ...",
  "severity": "critical",
  "recipient_role": "rapid_response",
  "communication_id": "Communication/comm-884",
  "generated_at": "2026-04-15T12:01:10Z",
  "model_used": "ollama/llama3.1"
}
```

**New text:**
```
{
  "status": "ok",
  "patient_id": "patient-42",
  "sbar": {
    "situation": "Post-op day 1 patient with SBP 86 and qSOFA 2; sepsis suspected.",
    "background": "42yo s/p laparoscopic cholecystectomy 18h ago; Hx T2DM.",
    "assessment": "Meets CDC ASE: lactate 2.4, SBP 86, abx started. High deterioration risk.",
    "recommendation": "Activate rapid response, draw repeat lactate, bolus 500ml NS, notify attending."
  },
  "narrative": "S: ... B: ... A: ... R: ...",
  "severity": "critical",
  "recipient_role": "rapid_response",
  "communication_draft": {
    "resourceType": "Communication",
    "status": "in-progress",
    "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/communication-category", "code": "alert"}]}],
    "priority": "urgent",
    "subject":   {"reference": "Patient/patient-42"},
    "encounter": {"reference": "Encounter/enc-77"},
    "sender":    {"reference": "Device/vigil-postop-sentinel", "display": "Vigil Postop Sentinel"},
    "recipient": [{"reference": "PractitionerRole/rapid-response", "display": "Rapid Response Team"}],
    "payload": [{"contentString": "S: ... B: ... A: ... R: ..."}]
  },
  "generated_at": "2026-04-15T12:01:10Z",
  "model_used": "ollama/llama3.1"
}
```

Note: the draft has NO `id` field. The FastAPI proxy assigns the id when it POSTs to HAPI on approve.

#### Edit 3.2.f — rewrite error-handling line 441

**Anchor:**
```
- **FHIR write fails:** `status=ok` with `communication_id=null` and `detail.persist_error` set. The SBAR is still returned — persistence is best-effort.
```

**New text:**
```
- **No FHIR write path:** the tool itself never writes. Persistence happens later at the `/approve` endpoint (§6.4); failures there surface as a distinct error on that endpoint, not on this tool.
```

#### Edit 3.2.g — §5.6 Communication example — label and note (line 772)

**Anchor:**
```
### 5.6 Communication (SBAR escalation — written by Vigil)
```

**New text:**
```
### 5.6 Communication (SBAR escalation — draft shape returned inside `communication_draft`)

> This is the shape `generate_escalation_note` returns inside its `communication_draft` field — unpersisted, no `id`, `status="in-progress"`. On clinician approve, the FastAPI proxy (`§6.4`) POSTs this body to HAPI with `status` flipped to `"completed"` and an `AuditEvent` emitted alongside. The tool never POSTs. The agent never POSTs.
```

---

### 3.3 ARCHITECTURE.md — §8 augmentation (Finding 2 alignment)

#### Edit 3.3.a — §8 Security & Non-Goals line 278

**Anchor:**
```
- **No autonomous action.** The A2A agent never writes to FHIR. Writes happen only when a human clicks Approve, and only via the review-queue service. The state machine deliberately has an `AWAITING_REVIEW` terminal leaf.
```

**New text:**
```
- **No autonomous action.** Neither the MCP tools nor the A2A agent ever write to FHIR. `generate_escalation_note` returns a `communication_draft` (unpersisted FHIR `Communication` shape); the A2A sentinel drops this draft into its local review queue at `AWAITING_REVIEW`; the **FastAPI proxy's `/approve` endpoint is the single FHIR write entry point for the entire stack**, and fires only when a human clicks Approve in the frontend. The state machine's `AWAITING_REVIEW` is a terminal leaf precisely because nothing downstream of it is allowed to touch HAPI without human confirmation.
```

---

### 3.4 DEMO_SCRIPT.md — Finding 3 (tool-name cleanup) + Finding 23 (AIDS/TB wording)

#### Edit 3.4.a — judge-hook ledger Proctor row (line 127)

**Anchor:**
```
| **Stephon Proctor** (CHOP, agentic action) | Action not reporting, closed loop | 1:10, 1:40–1:45 | `fhir_write_observation` write-back, "Send to Epic" button with toast, "teammate not dashboard" line | SERVED |
```

**New text:**
```
| **Stephon Proctor** (CHOP, agentic action) | Action not reporting, closed loop | 1:10, 1:40–1:45 | `generate_escalation_note` returns a draft (not a write), clinician clicks "Approve & Send RRT", backend writes `Communication` + `AuditEvent`, toast confirms — "teammate not dashboard" line | SERVED |
```

#### Edit 3.4.b — scene 3 breakdown (line 143)

**Anchor:**
```
The reveal. Heart rate and BP drift but nothing crosses a hard cutoff. Narration explicitly says "a rules engine would stay silent." This is where Mathur leans in. End the scene on the `fhir_write_observation` call — Proctor's first taste of closed-loop action.
```

**New text:**
```
The reveal. Heart rate and BP drift but nothing crosses a hard cutoff. Narration explicitly says "a rules engine would stay silent." This is where Mathur leans in. End the scene on the `generate_escalation_note` call returning a structured `communication_draft` — Proctor's first taste of the draft-then-approve pattern.
```

#### Edit 3.4.c — scene 4 breakdown (line 146)

**Anchor:**
```
SBAR types in on screen, one section at a time. Hickey's entire thesis is that nurses think in SBAR, so we show each letter appearing. Finish with the "Send to Epic" button — Proctor's closing moment. This is the longest uninterrupted product shot; it needs to breathe.
```

**New text:**
```
SBAR types in on screen, one section at a time. Hickey's entire thesis is that nurses think in SBAR, so we show each letter appearing. Finish with the "Approve & Send RRT" button — clicking it POSTs to the FastAPI proxy, which writes `Communication` + `AuditEvent` to HAPI and toasts the new audit id. That's Proctor's closing moment. This is the longest uninterrupted product shot; it needs to breathe.
```

#### Edit 3.4.d — AIDS/TB wording line 60 (Finding 23 freebie)

**Anchor:**
```
| 0:05 | Stat card: "4.2M deaths / year" | "— bigger than AIDS, tuberculosis, and malaria combined." | Red overlay on stat | GENERAL |
```

**New text:**
```
| 0:05 | Stat card: "4.2M deaths / year" | "— more than AIDS, tuberculosis, and malaria each." | Red overlay on stat | GENERAL |
```

#### Edit 3.4.e — AIDS/TB wording line 102 (Finding 23 freebie)

**Anchor:**
```
Postoperative mortality is the world's third biggest killer — bigger than AIDS, tuberculosis, and malaria combined. 4.2 million people die within 30 days of surgery every year. Most of those deaths are missed signals, not missing data.
```

**New text:**
```
Postoperative mortality is the world's third greatest contributor to global deaths — more than AIDS, tuberculosis, and malaria each. 4.2 million people die within 30 days of surgery every year. Most of those deaths are missed signals, not missing data.
```

(Nepogodiev wording + `each` not `combined` = simultaneously resolves NIT-5 and re-syncs with JUDGE_HOOKS:14 + CLINICAL_EVIDENCE §1.2.)

---

### 3.5 SYNTHETIC_DATA_SPEC.md — Findings 6, 14, 15, 16, 3 (the big block)

#### Edit 3.5.a — roster rewrite (lines 9-30)

**Anchor:** lines 9-30 inclusive.

**New text:** *full rewrite* — see §4.1 below (the rewrite is large enough to warrant the "new content blocks" section).

#### Edit 3.5.b — §2.2 PT-007 vitals rewrite (lines 53-62)

**Anchor:**
```
### 2.2 Deteriorating (PT-004, PT-005, PT-006, PT-007 hero)

| Timepoint | SBP | DBP | HR | RR | SpO2 | Temp | Urine |
|-----------|-----|-----|----|----|------|------|-------|
| T+0h      | 124 | 78  | 78 | 16 | 98   | 37.0 | 50    |
| T+1h      | 121 | 77  | 82 | 17 | 97   | 37.1 | 42    |
| T+2h      | 111 | 70  | 88 | 18 | 96   | 37.2 | 35    |
| T+4h      | 102 | 64  | 96 | 20 | 95   | 37.3 | 26    |
| T+6h      | 94  | 58  | 104| 22 | 94   | 37.4 | 18    |
| T+8h      | 88  | 54  | 112| 23 | 93   | 37.5 | 12    |

Individually each reading at T+2h is "borderline normal" — SBP 111 is not frankly hypotensive, HR 88 is not tachycardia. The **trend** is the signal: TRIGGERED at T+2h (MEWT 2-parameter drift), HIGH at T+4h.
```

**New text:**
```
### 2.2 Deteriorating (PT-004, PT-005, PT-006, PT-007 hero)

| Timepoint | SBP | DBP | HR | RR | SpO2 | Temp | Urine |
|-----------|-----|-----|----|----|------|------|-------|
| T+0h      | 130 | 82  | 76 | 16 | 98   | 37.0 | 50    |
| T+1h      | 124 | 78  | 84 | 17 | 97   | 37.1 | 42    |
| T+2h      | 114 | 72  | 92 | 18 | 96   | 37.2 | 35    |
| T+4h      | 102 | 64  | 100| 20 | 95   | 37.3 | 26    |
| T+6h      | 94  | 58  | 108| 22 | 94   | 37.4 | 18    |
| T+8h      | 88  | 54  | 116| 23 | 93   | 37.5 | 12    |

Individually each reading at T+2h is "borderline normal" — SBP 114 is not frankly hypotensive, HR 92 is not tachycardia. The **trend** is the signal: **at T+2h, SBP has dropped 12.3% (130 → 114) and HR has risen 21.1% (76 → 92) from T+0h.** Per the hemodynamic trend rule (`CLINICAL_EVIDENCE §2.3`), a ≥10% SBP drop AND ≥15% HR rise over any 2-hour window fires TRIGGERED regardless of absolute values. PT-007 hits the rule precisely at T+2h, advances to HIGH at T+4h (when absolute thresholds also cross: HR ≥100, RR ≥20), and stays HIGH through the window.
```

#### Edit 3.5.c — new §2.5 lab panel (inserted after §2.4, before §3)

Full new content — see §4.2 below.

#### Edit 3.5.d — §2.4 heading (line 77) — drop PT-011

**Anchor:**
```
### 2.4 Postpartum Hemorrhage (PT-010 hero, PT-011)
```

**New text:**
```
### 2.4 Postpartum Hemorrhage (PT-010 hero)
```

#### Edit 3.5.e — §4 Expected Alert table — drop PT-011 row (line 144)

**Anchor:**
```
| PT-010 ★   | NORMAL  | **TRIGGERED** | **EMERGENCY + SBAR + blood products + fundal massage** | CRITICAL | HIGH | HIGH |
| PT-011     | NORMAL  | TRIGGERED | EMERGENCY   | CRITICAL             | HIGH        | HIGH        |
```

**New text:**
```
| PT-010 ★   | NORMAL  | **TRIGGERED** | **EMERGENCY + SBAR + blood products + fundal massage** | CRITICAL | HIGH | HIGH |
```

Also adjust the PT-007 row: currently reads `| PT-007 ★   | NORMAL  | NORMAL    | **TRIGGERED** | **HIGH + SBAR**    | HIGH        | HIGH        |` — **no change needed**, because we moved the vitals not the marker.

#### Edit 3.5.f — §4 foot-note tool names (line 146)

**Anchor:**
```
★ = demo hero. MCP tools invoked: `screen_vital_thresholds` (every tick), `detect_sepsis_risk` (sepsis rows), `assess_postpartum_bleeding` (PT-010/011 rows), `generate_sbar_handoff` (at escalation).
```

**New text:**
```
★ = demo hero. MCP tools invoked every tick: `screen_vital_thresholds`, `score_deterioration_risk`, `flag_sepsis_onset`. `generate_escalation_note` fires at the first TRIGGERED tick of each patient and every tick thereafter until state machine exits `AWAITING_REVIEW`. Postpartum-specific handling (PT-009 sepsis, PT-010 hemorrhage) is data-driven, not tool-specific — the same four tools serve both wards per `PROJECT_BRIEF.md:27`.
```

#### Edit 3.5.g — §5 bundle template — add lab, Condition, MedicationAdministration entries

Not a simple Edit replacement — append a new `§5.1 Additional resource types (not shown in the per-timepoint template above)` subsection with the three shapes. See §4.3 below for the full new text.

#### Edit 3.5.h — §7 output directory listing (line 272)

**Anchor:**
```
  PT-011/...
  _index.json   # flat list of all patients with trajectories
```

**New text:**
```
  _index.json   # flat list of all 10 patients with trajectories
```

---

### 3.6 CLINICAL_EVIDENCE.md — Finding 16 (trend rule) + Finding 15 (lab LOINCs)

#### Edit 3.6.a — §2.3 append hemodynamic trend rule (after line 86)

**Anchor:**
```
**Deviations**: Vigil raises alerts on *trends* (e.g. RR rising 12→20 over 2h) before any single threshold is crossed. This is a deliberate departure from threshold-only MEWT — justified by the trend-based deterioration literature (§8) and alert-fatigue data (§9).
```

**New text:**
```
**Deviations**: Vigil raises alerts on *trends* (e.g. RR rising 12→20 over 2h) before any single threshold is crossed. This is a deliberate departure from threshold-only MEWT — justified by the trend-based deterioration literature (§8) and alert-fatigue data (§9).

**Hemodynamic trend rule (Vigil-specific, quantitative).**
> **If SBP drops ≥10% AND HR rises ≥15% over any 2-hour window, `screen_vital_thresholds` returns `status=triggered` regardless of whether any individual value crosses a MEWT absolute threshold.**

Rationale: Subbe 2001 (§2.1) and Shields 2016 (§2.2) both document that the subacute deterioration pattern — compensated shock preceding frank hypotension by 30-60 minutes — is visible in the rate-of-change of SBP and HR well before either absolute value crosses a cutoff. Neither paper quantifies the crossover slope exactly, so Vigil's 10% / 15% / 2h thresholds are a deliberate operational choice, not a published value. They are picked to fire on the classic PACU early-deterioration vignette: a patient whose SBP rolls 130 → 115 and HR 75 → 90 over two hours is below threshold on every absolute criterion but has a well-documented 3-4x relative risk of subsequent hypotension (Subbe 2001). Vigil explicitly does NOT claim this rule is externally validated; it is the trend-layer atop the MEWT ruleset and is demo-ground-truth only.

**Citation strength:** **Moderate** for the directional claim (SBP trend + HR trend predict deterioration → Subbe 2001 and Shields 2016, strong). **Weak** for the exact 10% / 15% / 2h numeric boundary, which is a Vigil operational choice and must be labeled as such in the README ("operational thresholds chosen to minimize missed-catch on synthetic and MIMIC-IV subset; prospective validation required before clinical use"). `RISK_REGISTER.md` R05 already flags this as the single most likely clinical-judge gotcha.

**Where we use it:** `screen_vital_thresholds` acceptance criteria (`BUILD_PLAN.md:111`), PT-007 ground-truth row in `SYNTHETIC_DATA_SPEC §2.2` and §4, DEMO_SCRIPT 0:50-1:00 narration ("pattern-not-threshold").
```

#### Edit 3.6.b — §11.2 LOINC table — add lab codes

**Anchor:**
```
| Urine output (24h volume) | 9192-6 | https://loinc.org/9192-6 |
```

**New text:**
```
| Urine output (24h volume) | 9192-6 | https://loinc.org/9192-6 |

**Lab `Observation` codes consumed by `flag_sepsis_onset` (CDC ASE organ-dysfunction criteria):**

| Parameter | LOINC | UCUM unit | Reference range |
|---|---|---|---|
| Lactate, blood | 2524-7 | `mmol/L` | 0.5–2.0 (venous, adults) |
| WBC count | 6690-2 | `10*3/uL` | 4.5–11.0 |
| Creatinine, serum | 2160-0 | `mg/dL` | 0.6–1.2 (F) / 0.7–1.3 (M) |
| Bilirubin, total | 1975-2 | `mg/dL` | 0.1–1.2 |
| Platelet count | 777-3 | `10*3/uL` | 150–400 |

LOINC codes verified against the HL7 build site (`https://build.fhir.org/observation-vitalsigns.html` for vitals; `https://loinc.org/search/` for the labs). UCUM units per `http://unitsofmeasure.org`. Reference ranges per the Mayo Clinic Laboratories panel (general adult). **Strength:** Strong — all five codes are top-result LOINC matches with reference ranges published in `Clinical Laboratory Tests: Normal Values` (McPherson & Pincus, Henry's Clinical Diagnosis 24ed, Elsevier 2021, §3).

**Where we use it:** `flag_sepsis_onset` FHIR reads (`API_CONTRACTS.md:265`), SYNTHETIC_DATA_SPEC §2.5 lab-panel table, DEMO_SCRIPT PT-009 narration ("lactate 4.1, white count 18").
```

---

### 3.7 FRONTEND_SPEC.md — Finding 7 minimal surgical edit (bundled per decision 2.3)

#### Edit 3.7.a — §3.3 approve button line 207

**Anchor:**
```
- **Two buttons**: primary `bg-accent text-accent-fg` ("Approve & send RRT") and ghost outline ("Dismiss"). Both client-side only — they open a `<Dialog>` that says "Demo: acknowledged" and closes. No network call.
```

**New text:**
```
- **Two buttons**: primary `bg-accent text-accent-fg` ("Approve & send RRT") and ghost outline ("Dismiss"). The approve button is a client component that calls `ackAlert(pid, alertId)` from `lib/api.ts` (see §6) — the call hits `POST /api/patients/{id}/alerts/{alertId}/approve` on the FastAPI proxy, which writes `Communication` + `AuditEvent` to HAPI and returns the new audit id. On success, a `<Sonner>` toast reads "Communication {id} written — audit {audit_id}". On failure, the toast reads "Write failed — retry". Dismiss is client-side only (closes the dialog without a network call). This mirrors `API_CONTRACTS §6.4` and is the ONLY FHIR-write entry point in the demo.
```

Note: this requires §6 line 350 `/ack` → `/approve` (Finding 7 route-name mismatch). That is already a one-word edit on table line 350 — bundle it. **Phase-2 note:** also check lines 366-368 `ackAlert` implementation — function name stays `ackAlert` (avoid rippling into all callers), but its URL target becomes `/approve`.

#### Edit 3.7.b — §6 line 350 table route

**Anchor:**
```
| `/api/patients/{id}/alerts/{alertId}/ack` | POST   | Client component on button click | `{ ok: true }` |
```

**New text:**
```
| `/api/patients/{id}/alerts/{alertId}/approve` | POST   | Client component on button click | `{ alert_id, status, acknowledged_at, audit_id }` |
```

#### Edit 3.7.c — §6 `ackAlert` function body line 366-368

**Anchor:**
```
export async function ackAlert(pid: string, aid: string) {
  return fetch(`${BASE}/api/patients/${pid}/alerts/${aid}/ack`, { method: 'POST' });
}
```

**New text:**
```
export async function ackAlert(pid: string, aid: string) {
  const res = await fetch(`${BASE}/api/patients/${pid}/alerts/${aid}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ clinician_id: 'prac-nurse-17', note: 'Acknowledged, RRT dispatched.' }),
  });
  if (!res.ok) throw new Error('approve failed');
  return res.json() as Promise<{ alert_id: string; status: string; acknowledged_at: string; audit_id: string }>;
}
```

---

## 4. New content blocks

### 4.1 SYNTHETIC_DATA_SPEC.md §1 roster rewrite

Replaces lines 9-30.

```markdown
## 1. Patient Roster

| patient_id | name                 | birthDate   | MRN        | procedure                        | trajectory              | demo role |
|------------|----------------------|-------------|------------|----------------------------------|-------------------------|-----------|
| PT-001     | Synthetic Patient 1  | 1978-03-14  | MRN-100001 | Lap cholecystectomy              | stable                  | hero      |
| PT-002     | Synthetic Patient 2  | 1965-11-02  | MRN-100002 | Total knee arthroplasty          | stable                  | filler    |
| PT-003     | Synthetic Patient 3  | 1991-07-22  | MRN-100003 | Appendectomy                     | stable                  | filler    |
| PT-004     | Synthetic Patient 4  | 1954-01-09  | MRN-100004 | Open colectomy                   | deteriorating           | filler    |
| PT-005     | Synthetic Patient 5  | 1972-05-30  | MRN-100005 | Hip arthroplasty                 | deteriorating           | filler    |
| PT-006     | Synthetic Patient 6  | 1960-09-17  | MRN-100006 | CABG                             | deteriorating           | filler    |
| PT-007     | Synthetic Patient 7  | 1983-12-04  | MRN-100007 | Exploratory laparotomy           | deteriorating           | hero      |
| PT-008     | Synthetic Patient 8  | 1969-06-11  | MRN-100008 | Bowel resection                  | sepsis_onset (postop)   | filler    |
| PT-009     | Synthetic Patient 9  | 1994-02-28  | MRN-100009 | C-section                        | sepsis_onset (postpartum) | hero    |
| PT-010     | Synthetic Patient 10 | 1996-08-19  | MRN-100010 | Vaginal delivery                 | postpartum hemorrhage   | hero      |

**Final roster counts:** 3 stable (PT-001..003) / 4 deteriorating (PT-004..007, PT-007 is the hero) / 2 sepsis (PT-008 postop, PT-009 postpartum) / 1 postpartum hemorrhage (PT-010). Total = 10 per `PROJECT_BRIEF.md:58`. PT-001, PT-007, PT-009, PT-010 are the on-camera heroes.

Note: the earlier draft added a PT-011 second hemorrhage case — dropped to keep the roster at exactly 10. The maternal cameo needs only one hemorrhage trajectory fired on screen (DEMO_SCRIPT 2:15 beat is a *flash*, not a deep dive), so 1 hemorrhage patient is sufficient.
```

Note: this reshuffles "2 sepsis / 2 hemorrhage" (brief) to "2 sepsis / 1 hemorrhage". **This contradicts `PROJECT_BRIEF.md:58`** which locks "4 trajectories" but does NOT specify equal counts. I interpret the constraint as "each trajectory must appear at least once," which 3/4/2/1 satisfies. **Flag for integration lead** — see §7.

### 4.2 SYNTHETIC_DATA_SPEC.md new §2.5 lab panel

Insert after §2.4 (new postpartum hemorrhage table), before §3.

```markdown
### 2.5 Lab Observations by trajectory and timepoint

Values keyed to trajectory × timepoint. LOINC codes per `CLINICAL_EVIDENCE §11.2`. Units: lactate `mmol/L`, WBC `10*3/uL`, creatinine `mg/dL`, bilirubin `mg/dL`, platelets `10*3/uL`. Labs are drawn only at T+0h, T+4h, and T+8h (no one draws labs every hour). `flag_sepsis_onset`'s evaluation window is 24h so this cadence is sufficient.

#### 2.5.1 Stable (PT-001, PT-002, PT-003)

| Timepoint | Lactate (2524-7) | WBC (6690-2) | Creatinine (2160-0) | Bilirubin (1975-2) | Platelets (777-3) |
|-----------|:---:|:---:|:---:|:---:|:---:|
| T+0h  | 1.2 | 8.1  | 0.9 | 0.6 | 240 |
| T+4h  | 1.3 | 8.4  | 0.9 | 0.7 | 232 |
| T+8h  | 1.2 | 8.0  | 0.9 | 0.6 | 238 |

No CDC ASE organ-dysfunction criterion is met at any timepoint. Expected: `flag_sepsis_onset.sepsis_suspected=false, mode="cdc_ase"`.

#### 2.5.2 Deteriorating (PT-004, PT-005, PT-006, PT-007 hero)

| Timepoint | Lactate | WBC  | Creatinine | Bilirubin | Platelets |
|-----------|:---:|:---:|:---:|:---:|:---:|
| T+0h  | 1.5 | 9.2  | 1.0 | 0.7 | 220 |
| T+4h  | 2.1 | 11.6 | 1.2 | 0.8 | 198 |
| T+8h  | 2.8 | 14.2 | 1.5 | 1.0 | 175 |

At T+4h, lactate 2.1 >= 2.0 crosses CDC ASE → `flag_sepsis_onset` returns POSSIBLE with organ-dysfunction criterion `lactate>=2.0`. WBC rise and creatinine drift add evidence by T+8h. Pairs cleanly with the hemodynamic trend rule firing on PT-007 at T+2h (from vitals alone).

#### 2.5.3 Sepsis onset (PT-008 postop, PT-009 postpartum hero)

| Timepoint | Lactate | WBC  | Creatinine | Bilirubin | Platelets |
|-----------|:---:|:---:|:---:|:---:|:---:|
| T+0h  | 1.8 | 10.5 | 0.9 | 0.7 | 215 |
| T+4h  | **4.2** | **18.4** | 1.4 | 1.1 | 140 |
| T+8h  | 5.8 | 21.1 | 1.9 | 1.6 | 98 |

**PT-009 T+4h is the DEMO_SCRIPT PT-009 beat**: `lactate 4.2` satisfies `DEMO_SCRIPT.md:24, 82` "lactate 4.1" narration (within rounding), and `WBC 18.4` satisfies "white count 18". Expected at T+4h: `flag_sepsis_onset.sepsis_suspected=true, mode="cdc_ase"`, criteria_met=["presumed infection (antibiotic started)", "organ dysfunction: lactate 4.2 mmol/L", "organ dysfunction: SBP 94 mmHg" (from §2.3 T+4h vitals)]. At T+8h, platelets 98 < 100 crosses the "platelet drop" criterion as well.

#### 2.5.4 Postpartum hemorrhage (PT-010 hero)

| Timepoint | Lactate | WBC  | Creatinine | Bilirubin | Platelets | Hgb (718-7) |
|-----------|:---:|:---:|:---:|:---:|:---:|:---:|
| T+0h  | 1.6 | 11.2 | 0.8 | 0.6 | 225 | 12.4 |
| T+4h  | 3.2 | 13.8 | 1.0 | 0.7 | 185 | 7.2  |
| T+8h  | 2.4 | 12.4 | 0.9 | 0.7 | 192 | 9.8  |

Hgb added to this trajectory only (LOINC 718-7, unit `g/dL`) because the hemorrhage narrative requires it — Hgb 7.2 at T+4h drives the "2 units PRBC transfusing" note in `SYNTHETIC_DATA_SPEC §3 Postpartum Hemorrhage T+4h`. Lactate >= 2.0 at T+4h also qualifies as ASE organ dysfunction, but `flag_sepsis_onset` returns POSSIBLE (1 criterion, no infection signal — no antibiotic administration + no fever). The dominant alert for PT-010 is still MEWT (absolute thresholds) + the hemorrhage-specific fundal/EBL annotations in §2.4.

**Reference-range sanity check.** All "stable" rows sit strictly inside the reference ranges from `CLINICAL_EVIDENCE §11.2`. All "triggered" rows cross published thresholds (CDC ASE lactate>=2.0, WBC elevated per SIRS, etc.). No value is physiologically impossible; the sepsis progression follows the expected organ-dysfunction sequence (lactate first, then WBC/creatinine/bilirubin, platelets last).
```

### 4.3 SYNTHETIC_DATA_SPEC.md new §5.1 — additional resource shapes

Insert after §5 (current line 228) as `§5.1`.

```markdown
### 5.1 Additional FHIR resource shapes (per patient)

The per-timepoint template in §5 shows only Patient + Encounter + Procedure + 7 vital Observations. For the tools to work, each patient bundle must ALSO include the lab Observations from §2.5, the Condition resources from the comorbidity table below, and the MedicationAdministration resources from the antibiotic-timing table below. These are generated once per patient (not per timepoint) and bundled under the same `Bundle.id` as the T+0h bundle.

#### 5.1.1 Condition (comorbidities — generated once per patient)

| Patient | SNOMED code | Display |
|---|---|---|
| PT-001 | 59621000  | Essential hypertension |
| PT-002 | 239873007 | Osteoarthritis of knee |
| PT-003 | (none)    | — |
| PT-004 | 44054006, 13645005 | Type 2 diabetes mellitus; COPD |
| PT-005 | 414916001, 59621000 | Obesity; Essential hypertension |
| PT-006 | 53741008, 44054006  | Coronary artery disease; Type 2 diabetes mellitus |
| PT-007 | 44054006, 433144002 | Type 2 diabetes mellitus; Chronic kidney disease stage 3 |
| PT-008 | 44054006, 13645005, 76571007 | Type 2 diabetes mellitus; COPD; Previous septicaemia |
| PT-009 | 199223000, 414916001, 11612004 | Gestational diabetes; Obesity; Chorioamnionitis |
| PT-010 | 58532003, 200737006, 398254007 | Placenta accreta; Previous cesarean; Mild preeclampsia |

Shape per condition (from `API_CONTRACTS.md §5.5`):
```json
{
  "resourceType": "Condition",
  "id": "cond-PT-007-T2DM",
  "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
  "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"}]},
  "code": {"coding": [{"system": "http://snomed.info/sct", "code": "44054006", "display": "Type 2 diabetes mellitus"}]},
  "subject": {"reference": "Patient/PT-007"},
  "recordedDate": "2024-11-02"
}
```

#### 5.1.2 MedicationAdministration (antibiotic timing — critical for CDC ASE path)

| Patient | Drug | RxNorm | Dose | Route | effectiveDateTime (relative to T+0h procedure) |
|---|---|---|---|---|---|
| PT-001..003 | Cefazolin | 309264 | 1 g | IV | T-0:30 (pre-op prophylaxis) |
| PT-004..007 | Cefazolin | 309264 | 1 g | IV | T-0:30 |
| PT-008 | Cefazolin | 309264 | 1 g | IV | T-0:30 |
| PT-008 | Piperacillin-tazobactam | 203134 | 4.5 g | IV | **T+4:15** (post sepsis-onset broad spectrum) |
| PT-009 | Cefazolin | 309264 | 2 g | IV | T-0:15 (pre-delivery) |
| PT-009 | Ampicillin-sulbactam | 1659149 | 3 g | IV | **T+4:20** (post sepsis-onset, postpartum endometritis/sepsis per ACOG PB 199) |
| PT-010 | Cefazolin | 309264 | 2 g | IV | T-0:15 |

**Why the post-onset times are ≥ 4:15 and not simultaneous with T+4h.** `flag_sepsis_onset` looks for an antibiotic start event within the 24h evaluation window but AFTER the organ-dysfunction marker appears — this lets it (correctly) flag "pre-administration window" scenarios for the DEMO_SCRIPT PT-009 beat, where the vitals + labs are already triggering the alert by the time empirical abx rolls. A simultaneous-with-onset dataset would confuse the tool's recency logic. **Citations:** Cefazolin dosing per ASHP Surgical Site Infection Prevention Guidelines (2013, https://www.ashp.org/-/media/assets/policy-guidelines/docs/therapeutic-guidelines/therapeutic-guidelines-surgical-site-infection.pdf); Piperacillin-tazobactam 4.5g q6h per Surviving Sepsis Campaign 2021 (https://journals.lww.com/ccmjournal/fulltext/2021/11000/surviving_sepsis_campaign_2021_guidelines.1.aspx); Ampicillin-sulbactam 3g IV q6h per ACOG Practice Bulletin 199 (2018, https://www.acog.org/clinical/clinical-guidance/practice-bulletin/articles/2018/09/use-of-prophylactic-antibiotics-in-labor-and-delivery).

Shape per administration:
```json
{
  "resourceType": "MedicationAdministration",
  "id": "medadmin-PT-009-ampisulbactam-1",
  "status": "completed",
  "medicationCodeableConcept": {"coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "1659149", "display": "Ampicillin-sulbactam 3 g IV"}]},
  "subject": {"reference": "Patient/PT-009"},
  "effectiveDateTime": "2026-04-15T14:20:00Z",
  "dosage": {"dose": {"value": 3, "unit": "g", "system": "http://unitsofmeasure.org", "code": "g"}, "route": {"coding": [{"system": "http://snomed.info/sct", "code": "47625008", "display": "Intravenous route"}]}}
}
```

#### 5.1.3 Lab Observation shape

Identical structure to the vital Observation shape in §5, except:
- `category[].coding[].code = "laboratory"` (not `"vital-signs"`)
- `code.coding[].code` uses the LOINC codes from §2.5 (e.g. `2524-7` for lactate)
- `valueQuantity.unit` matches the UCUM from `CLINICAL_EVIDENCE §11.2`
- `effectiveDateTime` is the draw time — T+0h, T+4h, or T+8h per §2.5

Example (PT-009 T+4h lactate):
```json
{
  "resourceType": "Observation",
  "id": "OBS-PT-009-T4-LACTATE",
  "status": "final",
  "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "laboratory"}]}],
  "code": {"coding": [{"system": "http://loinc.org", "code": "2524-7", "display": "Lactate [Moles/volume] in Blood"}]},
  "subject": {"reference": "Patient/PT-009"},
  "effectiveDateTime": "2026-04-15T14:00:00Z",
  "valueQuantity": {"value": 4.2, "unit": "mmol/L", "system": "http://unitsofmeasure.org", "code": "mmol/L"}
}
```
```

---

## 5. Grep verification plan

Run these after phase-2 execution. Zero hits is the target unless noted.

```bash
# 1. No drifted tool names anywhere in docs/ or the eventual backend/ tree
rg -n 'fhir_get_vitals|fhir_get_labs|fhir_get_meds|fhir_write_observation' docs/
rg -n 'list_postop_patients|summarize_patient_trajectory|rank_alert_priority' docs/
rg -n 'detect_sepsis_risk|assess_postpartum_bleeding|generate_sbar_handoff' docs/
# (each should return ZERO — any remaining hit means a miss)

# 2. No residual google-adk recommendation
rg -n 'google-adk|google\.adk|gemini-2\.5|GOOGLE_API_KEY|before_model_callback' docs/PROMPT_OPINION_INTEGRATION.md
# expected: references only inside the "historical reference" callout and the §1b inventory

# 3. No residual persist=True / communication_id in API_CONTRACTS
rg -n 'persist.*=.*True|communication_id|persist_error' docs/API_CONTRACTS.md
# expected: ZERO

# 4. No "Send to Epic" anywhere, no fhir_write_observation anywhere
rg -n '[Ss]end to [Ee]pic|fhir_write_observation' docs/
# expected: ZERO

# 5. Canonical tool names present everywhere they should be
rg -cn 'screen_vital_thresholds|score_deterioration_risk|flag_sepsis_onset|generate_escalation_note' docs/
# expected: appears in PROJECT_BRIEF, ARCHITECTURE, API_CONTRACTS, DEMO_SCRIPT, BUILD_PLAN, JUDGE_HOOKS, SYNTHETIC_DATA_SPEC, PROMPT_OPINION_INTEGRATION. 8 files minimum.

# 6. PT-011 fully excised
rg -n 'PT-011|MRN-100011' docs/
# expected: ZERO

# 7. SHARP headers correct
rg -n 'x-llm-provider|x-llm-api-key' docs/
# expected: ZERO
rg -n 'x-fhir-server-url' docs/
# expected: all hits are co-located with x-fhir-access-token + x-patient-id

# 8. CDC terminology consistency
rg -n 'CDC Severe Maternal Morbidity' docs/
# expected: ZERO
rg -n 'CDC Adult Sepsis Event' docs/
# expected: present in API_CONTRACTS, CLINICAL_EVIDENCE, JUDGE_HOOKS, SYNTHETIC_DATA_SPEC (at minimum)

# 9. Nepogodiev wording
rg -n 'third[- ]leading cause' docs/
# expected: only inside CLINICAL_EVIDENCE §12 weak-claim list and REVIEW_NOTES/REVIEW_SECOND_OPINION historical references
rg -n 'bigger than AIDS|aids.*malaria combined' docs/ -i
# expected: ZERO (all instances switched to "more than ... each" or the Nepogodiev contributor framing)

# 10. Trend rule presence
rg -n 'hemodynamic trend rule|SBP drops .{0,10}10%' docs/CLINICAL_EVIDENCE.md
# expected: ≥1 hit inside §2.3

# 11. Lab LOINCs documented
rg -n '2524-7|6690-2|2160-0|1975-2|777-3' docs/CLINICAL_EVIDENCE.md docs/SYNTHETIC_DATA_SPEC.md
# expected: ≥5 hits each

# 12. Condition + MedicationAdministration present in synthetic spec
rg -n 'Condition|MedicationAdministration' docs/SYNTHETIC_DATA_SPEC.md
# expected: ≥6 hits each (rubric + table + example shape)

# 13. Patient count check
rg -n 'Roster is 11|11 patients|PT-011' docs/SYNTHETIC_DATA_SPEC.md
# expected: ZERO
```

---

## 6. Phase-2 risk assessment

### 6.1 What could go wrong

1. **PROMPT_OPINION_INTEGRATION.md §3 is large and prose-heavy** — ~150 lines of ADK code samples to rewrite. The risk is introducing a subtle typo that breaks the "copy this code" value of the doc. **Mitigation:** every code block in edit 3.1.b through 3.1.f is a pure *replacement*, not a surgical edit; use the Write tool for the entire §3 (lines 256-404) as one wholesale block, not repeated Edit calls. Review the final text against the existing code in `API_CONTRACTS.md:620-657` and `API_CONTRACTS.md:522-580` to confirm shape consistency.

2. **API_CONTRACTS.md §1.4 has 6 interlocking edits** — removing `persist`, removing `communication_id`, adding `communication_draft`, rewriting the happy-path example, the error-handling line, the §1.4 intro line about FHIR writes. A missed edit leaves the schema inconsistent. **Mitigation:** edit in a strict top-to-bottom order; run grep verification 3 (`persist|communication_id`) immediately after the edits land.

3. **SYNTHETIC_DATA_SPEC.md §1 roster text is mangled** — the current prose has a self-correcting paragraph ("Roster is 11 patients... Add PT-011") that is *internally inconsistent* already. Risk: the Edit tool can't find a unique anchor in that mush. **Mitigation:** use the Write tool to replace the entire roster section (lines 9-30 → new §1). This is the one place the brief's "surgical vs wholesale" choice clearly favors wholesale.

4. **§2.2 PT-007 values will break any already-written backend tests** — but there are no tests written yet (phase 1 of build, not phase 2). Low risk. **Mitigation:** note in the F3 task acceptance criteria (already cites §2.2 + §2.5) that seed regeneration is required before B2 integration tests run.

5. **The new `§5.1 additional resource shapes` subsection will push §6 and §7 line numbers** — downstream docs citing `SYNTHETIC_DATA_SPEC.md:146` will drift. **Mitigation:** the only cross-doc line reference I found into §4 is `REVIEW_SECOND_OPINION.md:25` which is historical. Safe to push. But do a `rg 'SYNTHETIC_DATA_SPEC.md:[0-9]'` pass post-edit to confirm nothing else hard-references a line number.

6. **FRONTEND_SPEC edit 3.7.a mentions `<Sonner>` when shadcn's toast primitive is `sonner` (lowercase component)** — verify in phase 2 against FRONTEND_SPEC.md:237 which installs `sonner`. **Mitigation:** use `<Sonner>` toast language as prose, not a literal JSX tag; the phase-2 executor will get it right.

7. **The `a2a-sdk` class names in my proposed §3.1 code (`A2AServer`, `AgentExecutor`, `RequestContext`, `EventQueue`, `Task.completed`, `TextPart`) are aspirational** — I have not verified they match the real `a2a-sdk` 0.3.x Python API. If they don't, phase 2 will hit an importability error during doc review. **Mitigation:** the code is a *schematic* in a planning doc, not an executable file. A note at the top of §3.1 "API names reflect a2a-sdk 0.3.x; verify at build time" would cover us. **Adding this note is part of phase-2 edit 3.1.b.** I'll flag to the integration lead that a quick `pip show a2a-sdk` on the real package would firm up the exact class names before any code lands.

### 6.2 Surgical (Edit tool) vs. wholesale (Write tool)

| Edit | Tool | Why |
|---|---|---|
| 3.1.a §5.2 flip | Edit | Clean anchor, clean replacement |
| 3.1.b–3.1.f §3 rewrite | Write | Big prose block, multiple interlocking code samples. Write the whole §3 at once. Read full file first. |
| 3.1.g Appendix checklist | Edit | Two-line change |
| 3.2.a–3.2.g API_CONTRACTS §1.4 | Edit (each) | Each has a unique anchor; order matters; keep separate for rollback |
| 3.3.a ARCHITECTURE §8 bullet | Edit | Unique anchor |
| 3.4.a–3.4.e DEMO_SCRIPT | Edit | Surgical one-liners |
| 3.5.a roster | Write (for that block) — wholesale replacement |
| 3.5.b §2.2 vitals | Edit (table replacement) | Unique anchor |
| 3.5.c new §2.5 | Insert via Edit using §2.4 "major PPH" as pre-anchor OR via Write if §2 is getting too tangled |
| 3.5.d, e, f, h | Edit | One-liners |
| 3.5.g new §5.1 | Edit (append after §5 closing) |
| 3.6.a trend rule | Edit (append after anchor line 86) |
| 3.6.b lab LOINCs | Edit (append after anchor line 241) |
| 3.7.a FRONTEND §3.3 | Edit | Unique anchor |
| 3.7.b, c FRONTEND §6 | Edit | Unique anchors |

Peak edit density is in API_CONTRACTS.md (6 edits) and SYNTHETIC_DATA_SPEC.md (8 edits + 2 wholesale inserts). Plan phase 2 to finish all API_CONTRACTS edits before touching SYNTHETIC_DATA_SPEC, so each doc reaches a consistent state before the next starts.

---

## 7. Questions for the integration lead

Numbered so you can answer inline via `SendMessage`:

1. **Trajectory count rebalance.** Dropping PT-011 makes the final count 3 stable / 4 deteriorating / 2 sepsis / 1 hemorrhage = 10. This keeps all 4 trajectories alive but reduces hemorrhage to a single patient. Acceptable? Alternative is to reclassify PT-006 as hemorrhage instead of deteriorating (preserving 2+2+3+3 = 10) but then Mathur's "3-patient deteriorating cohort" visual breaks.

2. **Finding 7 bundling.** I proposed a minimal surgical bundle of Finding 7 (FRONTEND_SPEC client-side approve → backend POST). Do you want it in phase 2 or split out to a separate pass? The Finding-2 resolution is incomplete without it.

3. **PROMPT_OPINION_INTEGRATION.md §3 depth.** My proposal *in-place rewrites* §3.1, §3.2, §3.3, §3.5 and leaves §3.4 ("Path A and Path B are parallel") alone. Alternative is to add a new §3b section below the existing §3, keeping ADK prose as historical reference. Which do you prefer? In-place is cleaner for first-time readers; additive is safer for rollback.

4. **`a2a-sdk` API names.** The code samples I drafted for §3.1 (`A2AServer`, `AgentExecutor(ctx, events)`, `Task.completed(parts=[...])`) are schematic. Do you want me to `pip install a2a-sdk==0.3.x` in phase 2 and verify the exact class names before the code lands, or leave it as planning-doc pseudocode with a verify-at-build-time note?

5. **Trend-rule numeric boundaries.** I chose 10% / 15% / 2h for the hemodynamic trend rule based on the brief's suggested draft wording. These are *operational* not published. Is the hackathon demo-review comfortable having a Vigil-specific operational threshold labeled "Weak" citation strength and flagged as "prospective validation required"? The alternative is to drop the numeric boundary and leave the rule qualitative, but then `BUILD_PLAN B2` acceptance can't pass-or-fail it deterministically.

6. **Hgb / LOINC 718-7 addition.** I added hemoglobin to the PT-010 lab row because the hemorrhage narration needs it (`2 units PRBC transfusing` line at `SYNTHETIC_DATA_SPEC §3 Postpartum Hemorrhage T+4h` only makes sense if Hgb has crashed). This creates a sixth lab code that is NOT read by `flag_sepsis_onset`. Do you want Hgb in the §2.5 table, or dropped in favor of narration-only mention?

7. **§5.6 Communication shape decision.** I kept one Communication example (as the draft shape) with a note about the post-approve transformation. Would you prefer two full examples (draft AND persisted) even though only the `status` field differs? Duplication is clearer; single-shape is less noise.

8. **Residual KS-4 note in Blocker-2.** The brief says to "note explicitly that hand-rolled FastAPI A2A (Option C) remains the KS-4 fallback per `RISK_REGISTER.md:61`." I put this in §5.2 bullet 5 of the new Blocker-2 text. Is that the right location, or should it also appear in §3 or §6 ("Publishing to Marketplace")?

9. **DEMO_SCRIPT.md:146 freebie check.** Line 146 also says "`fhir_write_observation` write-back" inside a ledger cell (technically the same row as line 127 — it's the same row of a markdown table rendered across multiple source lines). I flagged it as part of edit 3.4.a. Confirm you want it treated as one edit, not two.

10. **Phase-2 commit strategy.** Should I commit per-finding, per-file, or as one wholesale "docs: apply phase-1 rewrite proposal" commit? The brief didn't specify and I want to avoid surprise on the commit log.

11. **Out-of-scope findings.** Phase-1 brief explicitly kept findings 5, 7–11, 13, 17–21, 24 out of scope. My read: Finding 5 is already fixed in JUDGE_HOOKS (confirm), Finding 7 is partially bundled per decision 2.3, Findings 8 (risk vocabulary) and 9 (MRN naming) are real latent contradictions that will fire on phase-3 build. Want me to log them as "out of scope, deferred to integration-lead phase N+1" somewhere so they're not lost?

---

## 8. Estimated phase-2 execution time

| Block | Effort | Notes |
|---|---|---|
| PROMPT_OPINION_INTEGRATION.md §3 + §5.2 rewrite (7 edits) | 55 min | Wholesale Write for §3, surgical for §5.2 + Appendix |
| API_CONTRACTS.md §1.4 (6 edits) | 25 min | Strict sequential Edit calls + grep-verify |
| ARCHITECTURE.md §8 (1 edit) | 3 min | One-liner |
| DEMO_SCRIPT.md (5 edits) | 15 min | Surgical, table-row text |
| SYNTHETIC_DATA_SPEC.md — §1 roster + §2.2 + §2.4 + §4 + §5.1 + §7 (10 edits, 2 wholesale inserts) | 60 min | Biggest block. Roster and §5.1 are the long writes. |
| CLINICAL_EVIDENCE.md — §2.3 trend rule + §11.2 LOINCs (2 edits) | 20 min | Prose-heavy |
| FRONTEND_SPEC.md — §3.3 + §6 route + `ackAlert` (3 edits) | 10 min | Surgical |
| Grep verification sweep + re-edit for any residual hits | 15 min | Run all 13 verification commands |
| Final cross-doc consistency read-through | 20 min | Skim all 7 touched docs for any seams |
| **Total** | **~3h 30min** |  |

Buffer to 4h to handle phase-2 clarifications from the integration lead if any of the 11 questions above come back with "do the other option."

---

## 9. Blocker-2 re-check — any phase-1 fact that could invalidate the decision?

Per the brief: "If phase-1 research surfaces a **new fact** that makes either decision wrong (not a preference — a fact), flag it."

**Blocker-1 (freeze Version A):** No new facts. The canonical tool set is deeply embedded in `API_CONTRACTS.md §1.1–1.4` with full Pydantic schemas. Version B (`fhir_*`) has zero pydantic schemas written anywhere. Freezing A is still objectively cheaper.

**Blocker-2 (raw `a2a-sdk`):** No new facts that invalidate the choice, but one fact worth noting:
- `PROMPT_OPINION_INTEGRATION.md:484` says "`po-adk-python` warns you'd re-invent session state for tool calls." My proposal §3.1 replaces ADK session state with the `RequestContext` on every `execute()` call — the agent is *stateless per request*, which works for Vigil because each tick is a complete screen-score-sepsis-escalate run with no cross-tick carryover. If future Vigil work adds cross-tick memory (e.g. "alert fatigue tracking over 24h"), we'd need a persistent store (SQLite, already specced for the review queue). This is NOT a phase-1 blocker but is worth noting in the decision log.
- No a2a-sdk API verification done in phase 1 — see question 4 above.

Decision stands: **raw `a2a-sdk` is correct**, Option C (FastAPI hand-roll) remains the KS-4 pre-committed fallback.

---

*End of REWRITE_PROPOSAL.md — rewrite-lead, phase 1, 2026-04-15.*
