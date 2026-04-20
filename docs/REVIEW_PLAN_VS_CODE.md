# REVIEW — Plan vs Code (Drift Audit)

Auditor: plan-auditor · Date: 2026-04-20 · Scope: full repo (`HEAD` = `5561f07`)

Cross-referenced planning docs (`PROJECT_BRIEF`, `ARCHITECTURE`, `API_CONTRACTS`, `BUILD_PLAN`, `SYNTHETIC_DATA_SPEC`, `CLINICAL_EVIDENCE`, `FRONTEND_SPEC`, `DEFERRED_FINDINGS`) against committed code.

---

## 1. Critical drift (demo-blocking)

| # | Severity | Item |
|---|----------|------|
| C1 | **BLOCKER** | `enqueue_alert` never called — review queue is always empty |
| C2 | **BLOCKER** | `/tick` endpoint does not exist on A2A agent |
| C3 | **HIGH**    | `list_patients` hardcodes `trajectory: "postop"` — no postpartum |
| C4 | **HIGH**    | `/patients/[id]/alerts/[alertId]` route missing (linked from detail page) |
| C5 | **HIGH**    | `/marketplace` route missing |
| C6 | MED        | Risk vocabulary 5-level UI ↔ 3-band backend mismatch |
| C7 | MED        | MRN / patient name scheme inconsistent across all three docs and code |

### C1 — Review queue is never populated  **BLOCKER**

`backend/api/review_queue.py:84` defines `enqueue_alert(...)`, but `grep -r enqueue_alert backend/` returns only its own definition. The sentinel (`backend/a2a_agent/sentinel.py`) calls `generate_escalation_note` via MCP and emits the narrative on the A2A event queue — but never writes the draft to SQLite. Consequences:
- `GET /api/alerts` (used by FE4) always returns `{"alerts": []}`.
- `GET /api/patients/{id}/alerts/latest` always 404s.
- FE1 “unread_alerts” badge, FE2 recent-alerts panel, FE3 `alert_approved` events, FE4 Review Queue, and approve flow all have nothing to operate on.
- BUILD_PLAN B7 acceptance (“draft posted to review queue”) is unmet.

**Fix**: in `sentinel.py` after `generate_escalation_note`, parse the JSON output and call `enqueue_alert(patient_id, severity, sbar, narrative, recipient_role, model_used, communication_draft)`. API_CONTRACTS.md §1.4 describes the shape.

### C2 — `/tick` endpoint does not exist  **BLOCKER**

`backend/api/main.py:262` POSTs to `{A2A_AGENT_URL}/tick`. `backend/a2a_agent/app.py` wires only what `A2AFastAPIApplication` builds — i.e. `/a2a` JSON-RPC and `/.well-known/agent-card.json`. `grep -r "/tick" backend/a2a_agent` returns nothing. Every “Tick Now” button press (FE3) will log `agent_tick success=false detail=HTTP 404`. The poll loop advertised in the `app.py` docstring (`POLL_INTERVAL_SEC`) is also not wired — no `asyncio.create_task` anywhere in `a2a_agent/`.

**Fix**: add a plain `@app.post("/tick")` handler in `a2a_agent/app.py` that invokes one `PostopSentinelExecutor.execute()` per seeded patient (or a single demo hero), and wire an optional `asyncio.create_task` on startup when `POLL_INTERVAL_SEC` is set. BUILD_PLAN B8 calls this out explicitly.

### C3 — Trajectory hardcoded to `"postop"`  **HIGH**

`backend/api/routes/patients.py:98` writes `"trajectory": "postop"` for every patient returned by `list_patients_action`. Seed data (`data/seed_hapi.py:148-209`) contains four trajectories (`stable`, `deteriorating`, `sepsis`, `pph`) and PT-009 (C-section sepsis) + PT-010 (PPH) are explicitly postpartum. PROJECT_BRIEF §2 (“maternal as cameo”) and FRONTEND_SPEC §3.1 both require the trajectory to reflect `postop | postpartum`.

**Fix**: infer trajectory from Condition codes or Procedure SNOMED. Cesarean section (`11466000`), normal delivery (`3950001`), pre-eclampsia (`398254007`), chorioamnionitis (`11612004`) → `postpartum`. Everything else → `postop`.

### C4 — Deep-link route missing  **HIGH**

`frontend/app/patients/[id]/page.tsx:462` links to `/patients/${id}/alerts/${latestAlert.alert_id}` as the CTA (“View full alert & approve →”). `frontend/app/patients/[id]/` contains only `error.tsx` + `page.tsx`. A click from the patient detail page 404s to `not-found.tsx`. FRONTEND_SPEC §3.3 and BUILD_PLAN FE5 reference this page.

### C5 — `/marketplace` route missing  **HIGH**

FRONTEND_SPEC §3.4 specifies a `/marketplace` page (sidebar entry + wireframe). `frontend/app/` has no `marketplace/` directory. The judges (Mathur, Mandel) specifically look for the Prompt Opinion Marketplace story — losing this page removes a scoring hook.

### C6 — Risk vocabulary mismatch  **MED**

`backend/schemas.py` defines `risk_band: Literal["low","moderate","high"]` (3 levels); `frontend/lib/risk.ts` uses 5 levels (`normal/low/medium/high/critical` per FRONTEND_SPEC §4.1). `backend/api/routes/patients.py:63-64` bridges this with a lossy map: `{critical→high, urgent→moderate, info→low}`, default `low`. Consequence: UI colors `normal` and `medium` never render for server data — detail page falls back to hardcoded defaults. Already recorded as DEFERRED_FINDINGS #8; still not fixed.

### C7 — MRN / patient name scheme  **MED**

Three non-overlapping conventions:

| Source                       | MRN         | Name                    |
|------------------------------|-------------|-------------------------|
| API_CONTRACTS §6.1 example   | `MRN-0042`  | `Jane Doe`              |
| `data/seed_hapi.py:297-306`  | `MRN-100001`| `Patient Synthetic 1`   |
| FRONTEND_SPEC §3.1 mockup    | `102394`    | `Reyes, Maria`          |

UI will render real backend values (`Patient, Synthetic 1` + `MRN-100001`) — diverges visibly from spec screenshots. Demo polish issue. DEFERRED_FINDINGS #9 tracks this.

---

## 2. Drift table — ~15 spec items mapped to code

| # | Spec item (source) | Status | Evidence |
|---|---|---|---|
| 1 | 4 MCP tools (API_CONTRACTS §1) | ✅ IMPLEMENTED | `backend/mcp_server/server.py:104,145,185,218` |
| 2 | SHARP headers + capability patch (§2) | ✅ IMPLEMENTED | `server.py:88-97`, `middleware.py`, `context.py` |
| 3 | 7-state agent FSM (ARCHITECTURE §4) | ✅ IMPLEMENTED | `sentinel.py:64-188`, `schemas.AgentState` |
| 4 | AgentCard JSON-RPC (§3) | ✅ IMPLEMENTED | `a2a_agent/app.py:46,60-65`, `agent_card.json` |
| 5 | `communication_draft` never written by tool (§1.4) | ✅ IMPLEMENTED | `generate_escalation_note.py:151-203` returns only |
| 6 | Approve = only FHIR write (§6.4) | ✅ IMPLEMENTED | `routes/patients.py:241-353` posts Comm + Audit |
| 7 | LLM abstraction via `LLM_PROVIDER` (F5) | ✅ IMPLEMENTED | `backend/llm/provider.py:197-224` |
| 8 | Ollama / Groq / Claude / Stub (F5) | ✅ IMPLEMENTED | `provider.py:54-195` — all 4 concrete classes |
| 9 | FastAPI proxy on 127.0.0.1 (§6 / SEC-19) | ✅ IMPLEMENTED | `DEVELOPMENT.md` + `main.py` docstring |
| 10 | X-API-Key enforcement (SEC-05) | ✅ IMPLEMENTED | `main.py:101-118` |
| 11 | CORS restricted, not wildcard (SEC-06) | ✅ IMPLEMENTED | `main.py:72-78`, `mcp_server/server.py:288-293` |
| 12 | AuditEvent on approve (§5.7) | ✅ IMPLEMENTED | `routes/patients.py:275-314` |
| 13 | 10 patients × 6 timepoints × 4 trajectories (SYNTHETIC_DATA §1) | ✅ IMPLEMENTED | `seed_hapi.py:52-145,148-209` |
| 14 | CDC ASE antibiotic check (§1.3) | ⚠ DRIFTED | `flag_sepsis_onset.py` prefers ATC `J01*`; seed data ships RxNorm `309264/1659149` → falls through to display-keyword path (still works, but brittle) |
| 15 | Review queue populated by agent (B7) | ❌ MISSING | `enqueue_alert` has zero callers (see C1) |
| 16 | `/tick` endpoint (BUILD_PLAN B8) | ❌ MISSING | No handler in `a2a_agent/app.py` (see C2) |
| 17 | POLL_INTERVAL_SEC loop (B8) | ❌ MISSING | Variable read at `app.py:33`, never consumed |
| 18 | `trajectory` per patient (§1.1, FRONTEND_SPEC §3.1) | ⚠ DRIFTED | Hardcoded `"postop"` (see C3) |
| 19 | `/marketplace` page (FRONTEND_SPEC §3.4) | ❌ MISSING | No `frontend/app/marketplace/` |
| 20 | `/patients/{id}/alerts/{alertId}` page (FE5) | ❌ MISSING | Linked but not present (see C4) |
| 21 | 5-level risk vocabulary (FRONTEND §4.1) | ⚠ DRIFTED | Schema caps at 3 bands (see C6) |
| 22 | MRN scheme `MRN-####` (§6.1) | ⚠ DRIFTED | Seed uses `MRN-100001`; mock uses `102394` (see C7) |
| 23 | qSOFA from §1.2 spec | ✅ IMPLEMENTED | `criteria/qsofa.py` + `score_deterioration_risk.py` |
| 24 | MEWT hemodynamic trend (CLINICAL_EVIDENCE §2.3) | ⚠ MINOR | `mewt._check_hemodynamic_trend` uses 10% SBP / 15% HR / 2h; spec says “sustained >110” but impl fires on single sample >110 — over-eager, not under. |
| 25 | SQLite review queue persists across restart (SEC-16 / DEFERRED #24) | ✅ IMPLEMENTED | `review_queue.py:28,236` — file-backed, `init_db` idempotent |

---

## 3. Silent additions (code without a spec)

Features shipped that no planning doc describes. None is harmful; two (S3, S4) would benefit from being backfilled into API_CONTRACTS §6 so the judging rubric can find them.

| # | Addition | Location | Note |
|---|---|---|---|
| S1 | `GET /api/health` | `main.py:149` | Standard; add to §6.0 |
| S2 | `GET /api/events/tail?since=` (polling feed for FE3) | `main.py:232` + `obs/metrics.get_events_since` | Acts as the “SSE-lite” that BUILD_PLAN B9 described in prose but never gave a schema |
| S3 | `GET /api/alerts` (cross-patient queue for FE4) | `main.py:220` | Used by `frontend/app/alerts/page.tsx` |
| S4 | `GET /api/status` (LLM / FHIR / agent health for FE6) | `main.py:289` | Used by Settings page; returns token totals, cache stats |
| S5 | `POST /api/agent/tick` | `main.py:254` | Public entry for FE3 “Tick Now”; depends on C2 |
| S6 | `X-Request-Id` propagation middleware | `main.py:87-93` | Good hygiene; missing from SECURITY_REVIEW |
| S7 | LLM response cache (cache-hit=0 prompt tokens) | `generate_escalation_note.py:259-273` + `backend/cache/` | Undocumented in §1.4; influences token-metrics accuracy |
| S8 | AuditEvent “soft-fail” path | `routes/patients.py:317-326` | Commits Communication even if AuditEvent POST fails. Not in §5.7 — should be called out (DEFERRED candidate). |
| S9 | `review_queue.init_db()` runs at import time | `review_queue.py:236` | Side-effect-on-import; conflicts with `on_startup` that also calls it |
| S10 | `StubProvider` for CI | `provider.py:176-194` | Useful; mention in F5 acceptance |

---

## 4. Documentation gaps (code covers, docs don’t)

Where the spec is silent but the code makes a load-bearing decision a judge may ask about.

- **Composite risk formula.** `score_deterioration_risk.py` computes `base = qsofa/3 + min(breaches*0.15, 0.3) + min(conditions*0.05, 0.15)` with bands `<0.3 low, 0.3-0.6 moderate, ≥0.6 high`. API_CONTRACTS §1.2 declares the tool output but not the math. Add a short §1.2.1 formula table. Mathur/Zheng will ask.
- **Severity → risk-band mapping.** The lossy map in `routes/patients.py:63-64` is the sole reason the UI risk badge changes on new alerts. Document in §6.1.
- **Recipient-role defaults.** `sentinel.py:204-208`: sepsis ⇒ `rapid_response`, else ⇒ `charge_nurse`. Not in §4.
- **LLM cache semantics.** Cache key = prompt+model+fhir_url+patient_id (`generate_escalation_note.py:259`). Token metrics report 0 prompt tokens on cache hit — affects dashboard numbers on replay.
- **AuditEvent failure handling.** See S8; silent failure is a policy decision, not an error.
- **Antibiotic detection strategy.** Tool tries ATC J01* prefix first, then falls back to a display-string keyword list (`cefazolin`, `piperacillin`, `ampicillin`, …). Seed data uses RxNorm — the fallback is what actually fires. Document in §1.3.
- **Capability extension key.** `mcp_server/server.py:93` advertises `ai.promptopinion/fhir-context`; `agent_card.json:22` references the same. Single source-of-truth constant would help.
- **Patient name generation.** `Synthetic Patient N` format set in `seed_hapi.py:302`; conflicts with UI mock names. Either update the mock or document the synthetic pattern.

---

## 5. Recommended action order

Ranked by demo-risk reduction per minute of work.

1. **C1** — wire `enqueue_alert` into `sentinel.py` after a successful `generate_escalation_note`. (~20 lines)
2. **C2** — add `POST /tick` to `a2a_agent/app.py` that iterates seeded patients and calls `executor.execute(...)`. (~30 lines)
3. **C3** — infer `trajectory` from Condition/Procedure codes in `list_patients_action`. (~15 lines)
4. **C4** — create `frontend/app/patients/[id]/alerts/[alertId]/page.tsx` with the SBAR + approve UI (FRONTEND_SPEC §3.3). (~150 LOC)
5. **C5** — stub `/marketplace` page per FRONTEND_SPEC §3.4. (~80 LOC)
6. **C6** — widen `RiskScoreOutput.risk_band` to 5 levels OR narrow the frontend vocabulary. Pick one and update DEFERRED_FINDINGS #8.
7. Doc patch — fold formulas, severity map, cache key, antibiotic fallback, AuditEvent soft-fail into API_CONTRACTS as §1.2.1 / §1.3.1 / §6.1 addenda.
8. Polish — align MRN / name convention across seed + spec + UI mocks.

Items 1–3 are on the P0 critical path for the `make demo` happy-path; without them no alert ever renders, no button does anything, and the “postpartum cameo” story disappears.
