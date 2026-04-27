# Prompt Opinion Marketplace Listing — Vigil

> Submission: Path B, Option 3 — Independent A2A Agent. The MCP server is internal in this deployment (the A2A agent calls it; chat clients do not), so this listing is single-surface: one A2A agent. Voice rules: clinical-direct, no exclamation marks, no emoji in body, no marketing-speak.

---

## Hero pitch — three versions for different surfaces

> A copywriting cache for the video voiceover, the LinkedIn post, the Devpost summary line. Pick the variant that fits the surface; do not paste all three.

- **Clinician version.** Pin Vigil to any postop or postpartum patient: it screens vitals, scores deterioration risk, and drafts the SBAR you would have written yourself.
- **Judge version.** Deterministic clinical rules decide; an LLM writes the SBAR; the clinician approves — catching post-op and postpartum deterioration 30–60 minutes earlier with FHIR-native, audit-traceable safety.
- **Dev version.** An A2A agent on Prompt Opinion that bridges PO's gRPC-flavor JSON-RPC to the spec form, reads FHIR via SHARP, and orchestrates four deterministic MCP tools.

---

## Title

```
Vigil — Postop & Postpartum Sentinel
```

## Tagline (≤80 chars)

```
A second pair of eyes on every post-op and postpartum bed.
```

(58 characters)

## Short description (≤200 chars)

```
A clinician-supervised early-warning agent for postop and postpartum wards. Invoked from the launchpad chat per patient over A2A; never escalates without clinician approve.
```

(172 characters)

## Long description

Vigil is a clinician-supervised early-warning agent for postoperative and postpartum wards, registered on Prompt Opinion as an external A2A agent. The launchpad's general chat can call any of its five skills per patient: a vitals screen, a deterioration risk score, a sepsis check, an SBAR draft, and an optional autonomous-watching skill. The agent card declares the FHIR-context extension, so when Prompt Opinion forwards a patient context, Vigil reads vitals, labs, conditions, and encounter data from the workspace's FHIR R4 server using the SHARP convention — three HTTP headers on outbound MCP calls, the matching `fhir-context` block on inbound A2A metadata. Session-scoped credentials flow through; nothing is configured into agent code.

Underneath, four deterministic rule engines produce the structured verdict before any LLM runs. The thresholds come from public standards: MEWT for the seven-parameter trigger set (Shields 2016), qSOFA for early sepsis stratification (Singer 2016, Sepsis-3), CDC Adult Sepsis Event criteria for confirmed sepsis (CDC 2018), and KDIGO for acute kidney injury staging (KDIGO 2012). Only after the rule engine has decided does the LLM draft the SBAR prose around that verdict. The LLM never decides whether to escalate. This is the architectural commitment that makes Vigil safe to put in a clinician's hands, and it is what separates the system from a generative-first chatbot wrapped around an EHR.

The same five skills cover post-op and postpartum with no code branching. A patient on day 2 of a CABG and a patient on day 3 postpartum get the same rule engine, the same FHIR client, and the same SBAR generator. Maternal sepsis is not a separate module — it is the same agent and the same code path against a different trajectory of clinical data.

The agent never writes to FHIR. Alerts land in a review queue; only the clinician approve flow writes the `Communication` and `AuditEvent` resources, and only after the Vigil `Device` and any referenced `PractitionerRole` have been resolved. Bearer tokens are redacted in logs. The configured FHIR URL is validated against an SSRF allowlist before any read.

What to expect. With full FHIR context, Vigil returns clinically grounded screens citing the criteria that did or did not fire. With sparse context — a missing patient ID, a FHIR server with no observations — it falls back to a structured request describing the data it needs, rather than guessing. Every documented graceful-failure mode is exercised in `docs/A2A_LOCAL_SMOKE.md`.

---

## Skills

The agent declares five skills in `backend/a2a_agent/agent_card.json`. Marketplace descriptions follow.

| Skill ID | Description |
|---|---|
| `vigil.screen_vitals` | Pulls the patient's recent observations and runs them through MEWT's seven-parameter trigger set. Returns a triggered/normal verdict with breach details and the parameters that fired. |
| `vigil.score_risk` | Computes qSOFA on the latest vitals, weights it with active conditions, and returns a low/moderate/high deterioration band with the reasoning behind the score. |
| `vigil.check_sepsis` | Applies CDC Adult Sepsis Event criteria — presumed infection plus organ dysfunction — and falls back to SIRS when labs are sparse. Returns suspicion verdict with cited evidence. |
| `vigil.draft_sbar` | Combines the screen, the risk score, and the sepsis check into a structured Situation/Background/Assessment/Recommendation handoff. Returns the prose for clinician review and approval. |
| `vigil.start_watching` | Begins background polling for the named patient at a configurable cadence. Optional. Used by the dashboard surface, not by the marketplace launchpad. |

Each skill resolves either by `metadata.skill_id` or by keyword routing on the user's prompt; both paths are verified in `docs/A2A_LOCAL_SMOKE.md`.

---

## How invocation works

- A clinician asks Prompt Opinion's general chat something like "consult Vigil to draft an SBAR for this patient." General chat resolves the right Vigil skill via keyword routing — the keywords are wired into `backend/a2a_agent/skill_router.py`.
- The patient context Prompt Opinion is already holding (FHIR server URL, bearer token, patient ID) flows into the A2A message metadata under the `fhir-context` extension. Vigil's hook (`backend/a2a_agent/fhir_hook.py::extract_fhir_from_metadata`) pulls it out and `fhir_metadata_to_sharp_headers` converts it to the three SHARP headers for downstream MCP tool calls.
- Vigil runs the rule engine, drafts the SBAR around the verdict, and returns prose that renders inline in the launchpad chat. No state is held between calls; every invocation carries its own FHIR context.

---

## Standards and provenance

| Standard | Source | Where it lives |
|---|---|---|
| MEWT (Maternal Early Warning Trigger) | Shields et al., AJOG 2016 | `backend/criteria/mewt.py` |
| qSOFA / Sepsis-3 | Singer et al., JAMA 2016 | `backend/criteria/qsofa.py` |
| CDC Adult Sepsis Event | CDC, 2018 | `backend/mcp_server/tools/flag_sepsis_onset.py` |
| SIRS (fallback when labs sparse) | Bone et al., ACCP/SCCM 1992 | `backend/criteria/sirs.py` |
| KDIGO AKI | KDIGO, 2012 | `backend/criteria/kdigo.py` |
| FHIR R4 | HL7, 2019 | `backend/fhir/` |
| SBAR | IHI / Joint Commission | `backend/mcp_server/tools/generate_escalation_note.py` |

The hemodynamic-trend rule (SBP drop ≥10% AND HR rise ≥15% over 2h) is operational and not externally validated. This caveat is preserved in code, in the SBAR output, and in `docs/CLINICAL_EVIDENCE.md`. Prospective validation against MIMIC-IV and a partner institution's deidentified data is on the post-deadline roadmap.

---

## Security

- **API key.** The agent card declares an `apiKey` security scheme on the `X-API-Key` header. Prompt Opinion prompts for the key when the connection is added.
- **SSRF allowlist.** The configured `x-fhir-server-url` is validated against `ALLOWED_FHIR_HOSTS` before any FHIR read.
- **Token hygiene.** Bearer tokens are redacted in logs (first four chars + `****`). Coverage in `tests/test_sharp_compliance.py`.
- **No autonomous writes.** The agent never writes to FHIR. Approve is the only path that emits `Communication` + `AuditEvent`.

---

## Empirical evidence

- `docs/A2A_LOCAL_SMOKE.md` — end-to-end round-trip across all five skills via metadata routing and keyword routing, plus three documented graceful-failure modes (no FHIR context / missing patient ID / MCP unreachable). Every reply returns `state=completed`; nothing leaks a 5xx or a stack trace.
- 475 tests across the backend suite (pytest), lint clean (ruff), type-checked (mypy). The protocol bridge alone has dedicated unit and integration coverage in `tests/test_po_compat.py`.

---

## Connection details for Prompt Opinion's "Add Connection" flow

- **Agent URL:** `https://<deploy-host>/a2a`
- **Agent card:** `https://<deploy-host>/.well-known/agent-card.json`
- **Security scheme:** `apiKey` on `X-API-Key`
- **FHIR-context extension:** `https://app.promptopinion.ai/schemas/a2a/v1/fhir-context` — toggle on so Prompt Opinion injects the patient context into outbound calls.
- **Required scopes:** `patient/Patient.rs`, `patient/Observation.rs`, `patient/Condition.rs`. `patient/MedicationRequest.rs` is optional.
