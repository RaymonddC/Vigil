# Vigil — Independent Second Opinion

> Independent senior-architect cold read. Where this contradicts `REVIEW_NOTES.md`, the disagreement is explicit.
> Scope: 11 planning docs + `REVIEW_NOTES.md`. 2026-04-15.

**Bottom line.** REVIEW_NOTES gets BLOCKER-1 *inverted*, misses three additional tool-name sets, and misses a hard four-doc contradiction on the "no autonomous action" rule. The planning set is not two fixes from shippable — it's closer to a careful contract rewrite.

---

## Section 1 — Blocker 1: MCP tool architecture

### Correcting REVIEW_NOTES first

`REVIEW_NOTES.md:10-32` claims Version B (`fhir_get_vitals`/`fhir_write_observation`) appears "in 66 places across 4 docs" including ARCHITECTURE, API_CONTRACTS, PROMPT_OPINION_INTEGRATION. **Empirically false.** `grep`:

- Version B (`fhir_get_*`, `fhir_write_*`) appears in exactly **2** files: REVIEW_NOTES itself and `DEMO_SCRIPT.md:15, 67, 73, 127, 143`.
- Version A (`screen_vital_thresholds`/`score_deterioration_risk`/`flag_sepsis_onset`/`generate_escalation_note`) appears in **7** files: PROJECT_BRIEF, ARCHITECTURE (23 refs, see `ARCHITECTURE.md:38-40`), API_CONTRACTS (`§1.1–1.4` at lines 48-443), BUILD_PLAN, PROMPT_OPINION_INTEGRATION (`§5.1` lines 455-480), SYNTHETIC_DATA_SPEC, REVIEW_NOTES.

Version A isn't the minority — it's the entire contract corpus. **Only DEMO_SCRIPT drifted.**

Worse: **three additional tool sets** the review missed:

- **Set C (`BUILD_PLAN.md:108-131`, B2-B5):** `list_postop_patients`, `screen_vital_thresholds`, `summarize_patient_trajectory`, `rank_alert_priority`. Drops sepsis and SBAR entirely.
- **Set D (`JUDGE_HOOKS.md:5, 121, 149, 187`):** "MEWT, qSOFA, **CDC Severe Maternal Morbidity**, SBAR generation." CDC SMM ≠ CDC Adult Sepsis Event (different programs, different purposes).
- **Set E (`SYNTHETIC_DATA_SPEC.md:146`):** `detect_sepsis_risk`, `assess_postpartum_bleeding`, `generate_sbar_handoff`. Zero overlap with any other doc.

Real drift count: **≥5 tool-name sets, ≥13 unique names**. Blocker-1 scope is roughly 3× what REVIEW_NOTES thought.

### Option set

#### Option 1 — Freeze Version A, fix the outliers
**Steelman.** Already dominant across contract docs. Lands Mathur ("deterministic MEWT/qSOFA composition, not a black box" — `JUDGE_HOOKS.md:24`) and Hickey (SBAR is a named tool). Full Pydantic schemas already written at `API_CONTRACTS.md:48-443`. `PROMPT_OPINION_INTEGRATION.md:460` explicitly says `generate_escalation_note` has "no FHIR write" — cleanly resolves the autonomy contradiction (Section 3, finding 2). Lowest build effort because the hardest artifact exists.
**Weakness.** Doesn't investigate *why* BUILD_PLAN and SYNTHETIC_DATA drifted — if the drift reflected a real design realization, freezing re-imports the problem.
**Effort:** 6h tool layer / 2h doc rewrite. **Judges:** Mathur, Hickey, Mandel.

#### Option 2 — Adopt Version B (FHIR CRUD)
**Steelman.** The demo is the only judge-facing artifact. `DEMO_SCRIPT.md:67, 73` lands Mandel ("any MCP-compatible agent can call") and Proctor ("closed loop into the chart") on CRUD tool names directly. Tools are trivial httpx wrappers, matching `po-community-mcp/python/tools/` nearly 1:1 — lowest Prompt Opinion runtime risk.
**Weakness.** Violates `PROJECT_BRIEF.md:25` ("4 MCP tools enforce published clinical standards"). CRUD tools are undifferentiated — every MCP-FHIR example has them. Trades the Mathur hook for the Proctor hook; *net* hook count goes down.
**Effort:** 3h tools / 5h doc rewrite. **Judges:** Mandel, Proctor.

#### Option 3 — Hybrid 4+4 = 8 tools (REVIEW_NOTES pick)
**Steelman.** Doubles the Marketplace footprint. Rule tools need CRUD tools internally anyway, so publishing both is near-zero marginal cost. Serves all 5 judges on paper.
**Weakness.** **8 tools is sprawl, not a story.** A 3-minute video cannot introduce 8 tools — the other 5 become vestigial Devpost copy. Mandel's "substitutable" ethos rewards parsimony. Adds 3-4h unbudgeted integration overhead.
**Effort:** 9h tools / 5h doc rewrite. **Judges:** nominally all 5, diluted per-judge.

#### Option 4 — Compose at the agent: 1 macro tool + 3 CRUD primitives
**Steelman.** Publish `monitor_patient_deterioration` (full screen→risk→sepsis→SBAR pipeline, single call) + `fhir_get_vitals`/`fhir_get_labs`/`fhir_get_meds` as primitives. Matches how po-community-mcp actually scopes things. Gives the demo **one magic moment** to show at 1:00–1:15 rather than four separate tool calls — tighter for a 3-minute cut. Aligns with Mandel's actual SMART ethos (thin primitives, intelligence in the client). Sidesteps the Set C/D/E naming chaos because there's only one branded tool.
**Weakness.** Loses the "4 reusable tools" framing that PROJECT_BRIEF is built around. Macro tool becomes a blob — if it crashes on stage there's no graceful fallback. Hickey hook is only satisfied if the macro tool is named carefully.
**Effort:** 5h tools / 6h doc rewrite. **Judges:** Mandel strongest, Mathur/Proctor moderate, Hickey conditional.

### Recommendation — disagreeing with REVIEW_NOTES

**Option 1.** I reject the Hybrid pick:

1. REVIEW_NOTES justified Hybrid on the false premise that Version B was entrenched in 4 docs. It isn't. Once corrected, Hybrid's "doc-cost only ~3h" collapses — you'd be *adding* CRUD language to PROJECT_BRIEF/ARCHITECTURE/API_CONTRACTS where none exists today.
2. A 3-minute video cannot introduce 8 tools. Mandel documents a preference for "substitutable" over "comprehensive" (`JUDGE_HOOKS.md:50`). Four sharp tools beat eight.

Doc rewrite: ~2h (DEMO_SCRIPT tool names, BUILD_PLAN B2-B5, JUDGE_HOOKS:5, SYNTHETIC_DATA_SPEC §4). Cheap, decisive.

---

## Section 2 — Blocker 2: A2A SDK choice

#### Option A — `google-adk` + `po-adk-python` (REVIEW_NOTES pick)
**Steelman.** Only known-good Prompt Opinion integration pattern. `shared/app_factory.py`, `shared/fhir_hook.py`, `shared/middleware.py` are copy-paste drop-ins (~150 LOC total). `to_a2a()` serves `/.well-known/agent-card.json` for free. `before_model_callback=extract_fhir_context` solves the SHARP-over-A2A metadata bridge with zero hand-rolling.
**Weakness — REVIEW_NOTES missed this.** ADK is Gemini-shaped by default. `PROMPT_OPINION_INTEGRATION.md:94, 270` shows `model="gemini-2.5-flash"` + `GOOGLE_API_KEY` required. That directly kills the `LLM_PROVIDER=ollama|groq|anthropic|stub` abstraction in `PROJECT_BRIEF.md:56` and `ARCHITECTURE.md:248-266`, and breaks `DEMO_SCRIPT.md:18`'s "LLM_PROVIDER=claude" precondition. ADK's "model-agnostic interface" is a real thing but adapting Claude/Ollama into it at hackathon speed is an unbudgeted 3-6h spike on top of the claimed 1-2h copy job.
**Effort:** 4-6h realistic; 2h doc rewrite. **Lock-in:** high. **Build changes:** F1 swaps deps, F5 becomes ADK model-shim, B7 rewrites around `Agent(...)`.

#### Option B — Raw `a2a-sdk` + hand-rolled metadata bridge
**Steelman.** Matches 5 of 11 docs already (PROJECT_BRIEF:53, ARCHITECTURE:206, API_CONTRACTS:5, BUILD_PLAN:54, RISK_REGISTER:18). Zero model lock-in — your existing `LLMProvider` from `ARCHITECTURE.md:250-266` Just Works because you own the handler. The "metadata bridge" — the supposedly hard part — is already written at `API_CONTRACTS.md:620-657` (~30 lines). The AgentCard JSON is already written at `API_CONTRACTS.md:522-580` in the exact shape a2a-sdk's Pydantic model consumes.
**Weakness.** `PROMPT_OPINION_INTEGRATION.md:484` warns you'd "re-invent session state for tool calls." Of the three things it names (AgentCard, metadata bridge, session state), only the third is real work. You end up hand-porting ~80 lines of `po-adk-python/shared/`.
**Effort:** 6-8h; 1h doc rewrite (amend PROMPT_OPINION_INTEGRATION §5.2). **Lock-in:** low. **Build changes:** F5 stays; B7 writes a `TaskHandler` subclass.

#### Option C — Hand-rolled A2A in ~50 lines of FastAPI
**Steelman.** `RISK_REGISTER.md:61` already endorses this as KS-4 — the team has implicitly signed off on its feasibility. The surface Prompt Opinion actually exercises is tiny: `message/send`, `tasks/get`, well-known agent-card GET. Three endpoints in 60 lines of FastAPI (already in the stack). Zero dependencies beyond what you're already installing.
**Weakness.** If Prompt Opinion's runtime probes for `tasks/cancel` / `tasks/subscribe` / streaming, your 60 lines eat an unpredictable T-3d bug.
**Effort:** 3-4h + 2-4h tail risk. **Lock-in:** zero.

#### Option D — LangGraph / Pydantic AI / CrewAI
**Steelman.** LangGraph maps the 5-state screen→score→sepsis→SBAR→queue machine in ~40 lines with visible state transitions that could render directly as the `/patients/[id]` "What triggered" card. Pydantic AI has tighter FastMCP integration. Both read as "serious agent stacks" to judges.
**Weakness — fatal.** Prompt Opinion's runtime only speaks A2A. Neither emits an A2A AgentCard or speaks A2A JSON-RPC. You'd still need one of A/B/C as an outer wrapper. **Rule out.**

### Recommendation — disagreeing with REVIEW_NOTES

**Option B.** REVIEW_NOTES' `google-adk` pick argues "1-2h copy job." True only if you accept Gemini as the sole LLM — which breaks PROJECT_BRIEF's non-negotiable provider abstraction. The real `google-adk` cost is 1-2h + 3-6h model-adapter spike + LLM_PROVIDER=claude risk on demo day.

Option B preserves the abstraction, leaves 5 docs untouched, and the "hard parts" already exist verbatim in API_CONTRACTS. REVIEW_NOTES' fear of "re-inventing the agent card JSON" is a phantom — the JSON exists. Option C (KS-4) remains the right fallback if B bogs beyond 8h.

---

## Section 3 — Things the original review missed

Numbered findings, file:line + suggested fix.

1. **REVIEW_NOTES miscounts the tool drift.** `REVIEW_NOTES.md:20, 25`: 66 refs across 4 docs. Actual: 5 refs in 1 doc, and ≥3 extra tool sets unflagged. **Fix:** rewrite BLOCKER-1 sourcing.

2. **Four docs disagree on "no autonomous action" — agent actually writes FHIR.** `PROJECT_BRIEF.md:60, 71` and `ARCHITECTURE.md:277-278` forbid autonomous writes; writes happen only on approval. But `API_CONTRACTS.md:349, 375, 432` has `generate_escalation_note` itself POSTing `Communication` with `persist=True` default. `JUDGE_HOOKS.md:97` (H10) makes "agent writes a Communication FHIR resource on screen" the single highest-leverage Proctor hook. `DEMO_SCRIPT.md:73, 127, 143` shows `fhir_write_observation` doing similar. `PROMPT_OPINION_INTEGRATION.md:460` contradicts API_CONTRACTS by saying `generate_escalation_note` has "no FHIR write." **This is bigger than BLOCKER-1** — it maps onto the single highest-leverage judge-facing claim. **Fix:** tool returns SBAR + `communication_draft`; review queue writes `Communication` on clinician approve. Update all 4 docs.

3. **Five tool-name sets, not two.** Sets C/D/E detailed in §1. **Fix:** after freezing canonical tools, grep every doc and replace.

4. **SHARP header list contradicts itself.** `PROJECT_BRIEF.md:57` / `API_CONTRACTS.md:450-452` / `PROMPT_OPINION_INTEGRATION.md:164-166` all say `x-fhir-server-url`, `x-fhir-access-token`, `x-patient-id`. `BUILD_PLAN.md:78, 146, 208, 346` instead says `x-fhir-server-url`, `x-llm-provider`, `x-llm-api-key`. LLM provider is NOT a SHARP header. If BUILD_PLAN ships, `RISK_REGISTER.md:41 R11` (SHARP conformance) fails on first test. **Fix:** rewrite BUILD_PLAN F5/B8/I2.

5. **CDC ASE vs CDC SMM confusion.** `CLINICAL_EVIDENCE.md §4` + `API_CONTRACTS.md:260-280` enforce CDC Adult Sepsis Event. `JUDGE_HOOKS.md:5, 121, 149, 187` refers to "CDC Severe Maternal Morbidity" as a named tool. Different standards from different CDC programs. SMM is a structural outcome indicator set, not a real-time trigger. **Fix:** rewrite JUDGE_HOOKS references to "CDC Adult Sepsis Event applied to postpartum."

6. **Synthetic patient count drift: 10 → 11.** `PROJECT_BRIEF.md:58` locks 10. `SYNTHETIC_DATA_SPEC.md:9-30` adds PT-011 and concludes "Roster is 11." `FRONTEND_SPEC.md:131` hard-codes `[All 10]`. `DEMO_SCRIPT.md` references 4. **Fix:** drop PT-011, rebalance to 3+3+2+2=10.

7. **Frontend approve button contradicts API contract.** `FRONTEND_SPEC.md:207` says approve is "client-side only... No network call." `API_CONTRACTS.md:894-908` specifies `POST /approve` that writes Communication.status + AuditEvent. Also route mismatch: frontend `/ack` (`FRONTEND_SPEC.md:350`) vs backend `/approve`. **Fix:** commit to backend contract, strip "client-side only" language.

8. **Risk vocabulary mismatch.** `FRONTEND_SPEC.md:105-113` uses 5 levels (`normal|low|medium|high|critical`). `API_CONTRACTS.md:212` uses 3 (`low|moderate|high`) + separate 3-value severity (`info|urgent|critical`). `<RiskBadge>` cannot render `moderate`. **Fix:** unify on 4 levels across front+back.

9. **MRN / patient name schemes don't match.** `API_CONTRACTS.md:711`: `MRN-0042` + "Jane Doe". `SYNTHETIC_DATA_SPEC.md:11-29`: `MRN-100001..100011` + "Synthetic Patient 1". `FRONTEND_SPEC.md:132-135`: `102394, 110201` + real-sounding names (`Reyes, Maria`; `Osei, Kwame`). Three incompatible conventions; the real-sounding names risk the R17 PHI-lookalike check. **Fix:** align to SYNTHETIC_DATA naming.

10. **MCP / A2A port numbers disagree across docs.** MCP: `:7001` (ARCHITECTURE:224) / `:7000` (DEMO_SCRIPT:15) / `:5001` (PROMPT_OPINION_INTEGRATION:46). A2A: `:7002` / `:9000` / `:9000` / `:8001` across the same 4 docs. **Fix:** pick one each, lock in docker-compose.

11. **`google-adk` requires Gemini, breaks LLM abstraction.** Detailed in §2. **Fix:** Option B.

12. **Mathur hook cites the *banned* wording.** `JUDGE_HOOKS.md:14` quotes Mathur's paper as stating postop mortality is "the **third-leading cause** of global deaths." `CLINICAL_EVIDENCE.md:24, §12 item 4` explicitly flags this as incorrect — the Nepogodiev wording is "third greatest *contributor*." Mathur is the single judge most likely to catch a misquote of a paper he co-authored. **Fix:** rewrite JUDGE_HOOKS:14.

13. **JUDGE_HOOKS commits to MIMIC-IV validation; BUILD_PLAN does not schedule it.** `JUDGE_HOOKS.md:98, 147` promises "Validated only on MIMIC-IV subset + synthetic bundles." BUILD_PLAN has zero MIMIC-IV task. The slide would be false. **Fix:** rewrite slide to "validated on synthetic bundles against published MEWT/qSOFA/CDC ASE thresholds — local prospective validation required" (DECIDE-AI-legal).

14. **Synthetic data missing resources the tools require.** `API_CONTRACTS.md:179, 266-268` reads `Condition?patient` (comorbidity weighting for `score_deterioration_risk`) and `MedicationAdministration?patient` (antibiotic detection for CDC ASE). `SYNTHETIC_DATA_SPEC §5` generates only Patient, Encounter, Procedure, 7 vital Observations. **The CDC ASE path always falls to `sirs_fallback`** — including on the PT-009 demo beat that `ARCHITECTURE.md:162-164` claims fires CDC SRS 3/3. **Fix:** add `Condition` + `MedicationAdministration` generation to `SYNTHETIC_DATA_SPEC §5` and F3 acceptance criteria (1-2h).

15. **No lab Observations either.** `API_CONTRACTS.md:265` reads lactate (2524-7), WBC (6690-2), creatinine (2160-0), bilirubin, platelets. SYNTHETIC_DATA_SPEC generates zero labs. `DEMO_SCRIPT.md:24, 82` promises "lactate >4, WBC >18" on PT-009 with no data to back it. **Fix:** add §2.5 lab panel table keyed to trajectory+timepoint.

16. **Expected-alert ground truth doesn't match the thresholds.** `SYNTHETIC_DATA_SPEC.md:137-140` says PT-007 TRIGGERED at T+2h, but per §2.2 the T+2h vitals are SBP 111 / HR 88 / RR 18 — none cross MEWT thresholds per `CLINICAL_EVIDENCE §2.2-2.3` (HR>110/130, SBP<90/85, RR>24/30). The only trigger that could fire is a "trend" rule that §6 waves at but never quantifies. The `BUILD_PLAN.md:116-118` integration test will then pass or fail by accident. **Fix:** add a quantitative trend rule to CLINICAL_EVIDENCE §2.3 ("SBP drops ≥10% over 2h AND HR rises ≥15%") and make the numbers actually cross it, or move the ground-truth TRIGGERED marker to T+4h.

17. **Frontend proxy layer specified but not in BUILD_PLAN.** `API_CONTRACTS.md:824-912` specifies a Python FastAPI proxy at `backend/api/` with 4 endpoints. `FRONTEND_SPEC.md:343` depends on it. BUILD_PLAN FE5 (`BUILD_PLAN.md:183`) is a Next.js route handler, not the FastAPI proxy — different process. **The demo flow `frontend → FastAPI → HAPI` is unowned.** **Fix:** add task B10 "FastAPI frontend proxy" ~2h.

18. **Agent polling path is contradicted.** `ARCHITECTURE.md:181`: agent fetches latest Observation bundle "directly from HAPI (bypassing MCP for the poll)." `PROJECT_BRIEF.md:10`: "A2A agent calls the MCP tools in a 15-minute monitoring loop." One says MCP, one says direct. **Fix:** agent polls via MCP (honest reuse story, one FHIR client path). Document in ARCHITECTURE §4.

19. **R01 has no human owner.** `RISK_REGISTER.md:13` (Prompt Opinion publishing flow, P×I=20, the highest risk) assigns to "Tech Lead" — no named role exists in BUILD_PLAN §5 matching this. The work is non-engineering (Discord asks at `PROMPT_OPINION_INTEGRATION.md:572-578`). **Fix:** assign to demo-producer day 1, escalate at 48h.

20. **KS-4 trigger condition doesn't match its risk.** `RISK_REGISTER.md:61` KS-4 triggers on "a2a-sdk breaking change" (R06). The actual a2a-sdk risk we care about is R11 (runtime mismatch with Prompt Opinion). If the team pins versions — which R06 mitigation mandates — there is no "breaking change" trigger path at all. **Fix:** re-route KS-4 off R11.

21. **"Send to Epic" button has no backend and is explicitly anti-scope.** `DEMO_SCRIPT.md:79` shows clicking "Send to Epic." `BUILD_PLAN.md:362` anti-scope list says "no EHR integration (Epic/Cerner/Athena)." The button leads nowhere. **Fix:** rename to "Approve & Send RRT" matching `FRONTEND_SPEC.md:199`.

22. **`list_postop_patients` is a category error as an MCP tool.** `BUILD_PLAN.md:108-112` (B2) implements patient enumeration as an MCP tool. MCP tools should act on a patient-in-context, not enumerate the cohort. The frontend already needs this on the proxy (`/api/patients`). **Fix:** delete B2, move to the backend proxy. Frees 2h.

23. **Uncitable "AIDS+TB+malaria combined" also in PROJECT_BRIEF.** REVIEW_NOTES NIT-5 flagged DEMO_SCRIPT only, but `PROJECT_BRIEF.md:16` has the same phrase. **Fix:** edit both.

24. **Review queue persistence is hand-wavy but the approve flow assumes it.** `ARCHITECTURE.md:289` leaves SQLite-vs-in-memory open. The approve flow in API_CONTRACTS §6 assumes survival across page reload. In-memory breaks the demo if the frontend reloads. **Fix:** commit to SQLite, close ARCHITECTURE §9.3.

---

## Section 4 — Overall confidence read

**What's genuinely strong.** `CLINICAL_EVIDENCE.md` is the best artifact — every claim sourced, weak claims self-flagged, substitute phrasings offered inline. `PROMPT_OPINION_INTEGRATION.md` has copy-ready code with GitHub permalinks, not pseudocode. `RISK_REGISTER.md`'s kill-switch list is decisively pre-committed. `JUDGE_HOOKS.md` maps 3+ named hooks to every judge (once you fix findings 5 and 12). The synthetic vitals tables (§2.1-2.4) are clinically plausible *in isolation*.

**What's fragile.** Three things could sink the submission: (1) the autonomy contradiction (finding 2) — four docs disagree on whether the agent writes FHIR, and that's the load-bearing story for both Mandel and Proctor, the two hooks most likely to be probed on stage. (2) The synthetic-data-vs-tools gap (findings 14, 15, 16) — the tools read resources the spec doesn't generate, the narration references labs that don't exist, the expected-alert ground truth is against thresholds the data doesn't cross. The backend integration test (`BUILD_PLAN B6`) will fail on first run and the team will spend unbudgeted hours debugging whether rules or data are wrong. (3) BUILD_PLAN is the most drifted doc in the set (3 tool-name sets, wrong SHARP headers, missing B10 proxy task, MIMIC-IV referenced but not scheduled) and it's the dispatch document — errors get amplified 5× by parallel work.

**Probability ≥ 37/40 at current state: ~15-20%.** To hit 37/40 you need AI Factor 10, Impact 10, Feasibility 9, Buildability 8. The *story* for Impact 10 (stats + substitutability + agentic) and AI Factor 10 (LLM over deterministic rules) exists. Feasibility 9 is conditional on resolving the autonomy contradiction and regenerating synthetic data with labs/conditions. Buildability 8 is the weakest — BUILD_PLAN is inconsistent with itself and the 28h critical path assumes tools it doesn't schedule. My read: resolving findings 2, 3, 4, 14, 15, 16 moves probability to ~40-45%. Resolving all 24 moves to ~55-60%. Beyond 60% depends on the actual build landing and the demo recording cleanly — outside planning-set control.

The plan is survivable but not one REVIEW_NOTES away from shippable. It's closer to one careful rewrite pass away.

---

*End of second opinion.*
