# Vigil — API Contracts

Single source of truth for every interface between Vigil components. Frontend and backend agree on shapes here before any code is written.

- **Stack:** Python 3.11+, `mcp` Python SDK (FastMCP), `a2a-sdk` (Google), `pydantic` v2, FastAPI, HAPI FHIR `v7.2.0`.
- **Domain:** One MCP server, 4 tools, 1 A2A agent (Postop Sentinel). Same tools serve postop AND postpartum trajectories via synthetic FHIR data.
- **FHIR:** R4, served at `http://localhost:8080/fhir`.
- **SHARP:** 3 headers on MCP calls; different path (message metadata) on A2A calls.

References cited inline. Sources:
- `https://github.com/prompt-opinion/po-community-mcp/tree/main/python`
- `https://github.com/prompt-opinion/po-adk-python/tree/main/shared`
- `https://github.com/google/a2a-python/blob/main/src/a2a/types.py`
- `https://build.fhir.org/observation-vitalsigns.html`

---

## 1. MCP Tool Contracts

All tools live on one FastMCP server (`backend/mcp_server/server.py`). Every tool accepts the same SHARP context via FastMCP `Context` and reads the three headers plus patient ID from there (see Section 2). Tools return Pydantic models serialized to JSON via `model_dump_json()`; FastMCP wraps them in the MCP `CallToolResult` envelope.

### Common error envelope

All tools share this error discriminator returned in the `status` field:

```python
from enum import Enum
from pydantic import BaseModel, Field

class ToolStatus(str, Enum):
    OK = "ok"                         # Happy path
    TRIGGERED = "triggered"           # Deterministic rule fired
    BAD_INPUT = "bad_input"           # Pydantic validation failed
    FHIR_UNAVAILABLE = "fhir_error"   # HAPI unreachable / 5xx
    FHIR_NOT_FOUND = "fhir_not_found" # Resource missing
    LLM_UNAVAILABLE = "llm_error"     # Ollama/Groq/Claude down

class ToolError(BaseModel):
    status: ToolStatus                # Discriminator
    message: str                      # Human-readable reason
    detail: dict | None = None        # Structured context for debugging
```

On `BAD_INPUT`, FastMCP raises `ValueError` (per `mcp_utilities.create_text_response`, see po-community-mcp). On FHIR/LLM failures, the tool returns a normal result with `status != OK` so the agent can reason about it instead of crashing.

---

### 1.1 `screen_vital_thresholds`

**Purpose:** Deterministically screens the most recent vital signs against MEWT (Modified Early Warning / Trigger) criteria and flags any that cross a threshold.

**Standard enforced:** MEWT (Modified Early Warning Thresholds). No LLM involved — pure Python rules. Source: `https://www.mdcalc.com/calc/1875/modified-early-warning-score-mews-clinical-deterioration`.

**FHIR reads:**
- `Observation?patient={id}&category=vital-signs&_sort=-date&_count=50`
- Required fields: `code.coding[].code` (LOINC), `valueQuantity.value`, `valueQuantity.unit`, `effectiveDateTime`.

**LOINC codes consumed:** `8480-6` SBP, `8462-4` DBP, `8867-4` HR, `9279-1` RR, `59408-5` SpO2, `8310-5` temp, `9192-6` urine output.

**Input schema**

```python
from typing import Annotated, Literal
from pydantic import BaseModel, Field

class ScreenVitalsInput(BaseModel):
    """Input for screen_vital_thresholds."""

    patient_id: Annotated[str | None, Field(
        default=None,
        description="FHIR Patient.id. Optional if SHARP x-patient-id header is set."
    )] = None
    lookback_minutes: Annotated[int, Field(
        default=240, ge=15, le=1440,
        description="How far back to scan vitals, in minutes. Default 4 hours."
    )] = 240
    trajectory: Annotated[Literal["postop", "postpartum"], Field(
        default="postop",
        description="Selects which MEWT threshold table to use. Postpartum uses HTN-tuned cutoffs."
    )] = "postop"
```

**Output schema**

```python
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Literal

class VitalBreach(BaseModel):
    """One vital that violated a MEWT threshold."""

    loinc: str                        # LOINC code of the offending vital
    label: str                        # Human label, e.g. "SBP"
    value: float                      # Observed numeric value
    unit: str                         # UCUM unit
    threshold: str                    # e.g. "<90" or ">=130"
    severity: Literal["yellow", "red"]  # MEWT band
    observed_at: datetime             # effectiveDateTime from Observation

class ScreenVitalsOutput(BaseModel):
    """Output for screen_vital_thresholds."""

    status: ToolStatus                # OK | TRIGGERED | FHIR_*
    patient_id: str                   # Echoed back for the agent
    trajectory: str                   # "postop" | "postpartum"
    breaches: list[VitalBreach]       # Empty when status == OK
    scanned_count: int                # Number of Observations evaluated
    window_start: datetime            # Start of lookback window (UTC)
    window_end: datetime              # "Now" at evaluation time
```

**Request example**

```json
{
  "patient_id": "patient-42",
  "lookback_minutes": 240,
  "trajectory": "postop"
}
```

**Happy path response**

```json
{
  "status": "ok",
  "patient_id": "patient-42",
  "trajectory": "postop",
  "breaches": [],
  "scanned_count": 18,
  "window_start": "2026-04-15T08:00:00Z",
  "window_end": "2026-04-15T12:00:00Z"
}
```

**Triggered response**

```json
{
  "status": "triggered",
  "patient_id": "patient-42",
  "trajectory": "postop",
  "breaches": [
    {
      "loinc": "8480-6", "label": "SBP", "value": 86.0, "unit": "mm[Hg]",
      "threshold": "<90", "severity": "red",
      "observed_at": "2026-04-15T11:48:00Z"
    },
    {
      "loinc": "8867-4", "label": "HR", "value": 126.0, "unit": "/min",
      "threshold": ">=120", "severity": "yellow",
      "observed_at": "2026-04-15T11:48:00Z"
    }
  ],
  "scanned_count": 18,
  "window_start": "2026-04-15T08:00:00Z",
  "window_end": "2026-04-15T12:00:00Z"
}
```

**Error handling**
- **Malformed input:** Pydantic raises, FastMCP surfaces `ValueError`.
- **FHIR fetch fails:** `status=fhir_error`, empty `breaches`, `detail.http_status` populated.
- **No vitals in window:** `status=ok` with `scanned_count=0`.
- **LLM unavailable:** N/A — no LLM path.

---

### 1.2 `score_deterioration_risk`

**Purpose:** Computes a qSOFA score plus a lightweight composite trend score over the last N hours to estimate short-horizon deterioration probability.

**Standard enforced:** qSOFA (deterministic, 0–3). Composite trend is heuristic (delta SBP, delta HR, SpO2 slope) and documented as non-clinical. Reference: `https://www.mdcalc.com/calc/3909/qsofa-quick-sofa-score-sepsis`.

**FHIR reads:**
- `Observation?patient={id}&category=vital-signs&_sort=-date&_count=100`
- `Condition?patient={id}` (for comorbidity flags that modify trend weighting).
- Required fields: as in 1.1, plus `Condition.code.coding[].code`.

**Input schema**

```python
class ScoreRiskInput(BaseModel):
    """Input for score_deterioration_risk."""

    patient_id: Annotated[str | None, Field(
        default=None,
        description="FHIR Patient.id. Optional if SHARP header set."
    )] = None
    window_hours: Annotated[int, Field(
        default=6, ge=1, le=48,
        description="Trend window for slope computation, in hours."
    )] = 6
    trajectory: Annotated[Literal["postop", "postpartum"], Field(
        default="postop",
        description="Selects comorbidity weighting profile."
    )] = "postop"
```

**Output schema**

```python
class RiskScoreOutput(BaseModel):
    """Output for score_deterioration_risk."""

    status: ToolStatus                # OK | TRIGGERED | FHIR_*
    patient_id: str                   # Echoed back
    qsofa_score: int = Field(ge=0, le=3)  # Deterministic qSOFA
    qsofa_components: dict[str, bool] # {"rr_ge_22": True, "sbp_le_100": False, "altered_mental": False}
    composite_risk: float = Field(ge=0.0, le=1.0)  # Heuristic 0-1
    risk_band: Literal["low", "moderate", "high"]  # Bucketed composite
    rationale: str                    # Short deterministic string
    contributing_conditions: list[str]  # SNOMED or text labels of comorbidities used
```

**Request example**

```json
{ "patient_id": "patient-42", "window_hours": 6, "trajectory": "postop" }
```

**Happy path response**

```json
{
  "status": "ok",
  "patient_id": "patient-42",
  "qsofa_score": 0,
  "qsofa_components": {"rr_ge_22": false, "sbp_le_100": false, "altered_mental": false},
  "composite_risk": 0.12,
  "risk_band": "low",
  "rationale": "qSOFA=0; SBP stable; HR stable; no trend breach.",
  "contributing_conditions": []
}
```

**Triggered response**

```json
{
  "status": "triggered",
  "patient_id": "patient-42",
  "qsofa_score": 2,
  "qsofa_components": {"rr_ge_22": true, "sbp_le_100": true, "altered_mental": false},
  "composite_risk": 0.71,
  "risk_band": "high",
  "rationale": "qSOFA=2 meets sepsis screen; SBP trending down 18 mmHg over 4h.",
  "contributing_conditions": ["44054006 Type 2 diabetes"]
}
```

**Error handling:** Same as 1.1 plus — if fewer than 3 observations exist for slope, `composite_risk` is still computed from qSOFA only and `rationale` notes "insufficient trend data".

---

### 1.3 `flag_sepsis_onset`

**Purpose:** Runs the CDC Adult Sepsis Event (ASE) / SRS surveillance definition against labs + vitals + antibiotic administration to flag likely sepsis onset in the last 24h.

**Standard enforced:** CDC Adult Sepsis Event criteria (`https://www.cdc.gov/sepsis/hcp/clinical-tools/index.html`). Deterministic — no LLM. Fallback: if labs are sparse (hackathon data), uses SIRS 2-of-4 as a degraded mode and marks `mode="sirs_fallback"`.

**FHIR reads:**
- `Observation?patient={id}&category=vital-signs`
- `Observation?patient={id}&category=laboratory` (WBC `6690-2`, lactate `2524-7`, creatinine `2160-0`, bilirubin `1975-2`, platelets `777-3`).
- `MedicationAdministration?patient={id}` (antibiotic presence signal).
- `Encounter?patient={id}` (admit time reference).

**Input schema**

```python
class FlagSepsisInput(BaseModel):
    """Input for flag_sepsis_onset."""

    patient_id: Annotated[str | None, Field(default=None, description="FHIR Patient.id. Optional if SHARP header set.")] = None
    evaluation_window_hours: Annotated[int, Field(
        default=24, ge=1, le=72,
        description="How far back to scan for onset evidence."
    )] = 24
```

**Output schema**

```python
class SepsisFlagOutput(BaseModel):
    """Output for flag_sepsis_onset."""

    status: ToolStatus                   # OK | TRIGGERED | FHIR_*
    patient_id: str                      # Echoed back
    sepsis_suspected: bool               # True iff TRIGGERED
    mode: Literal["cdc_ase", "sirs_fallback"]  # Which rule path fired
    criteria_met: list[str]              # Human strings, e.g. "lactate>=2.0 mmol/L"
    onset_estimate: datetime | None      # Earliest moment all criteria coincided
    evidence: dict                       # Raw values used (for audit)
```

**Request example**

```json
{ "patient_id": "patient-42", "evaluation_window_hours": 24 }
```

**Triggered response**

```json
{
  "status": "triggered",
  "patient_id": "patient-42",
  "sepsis_suspected": true,
  "mode": "cdc_ase",
  "criteria_met": [
    "presumed infection (antibiotic started)",
    "organ dysfunction: lactate 2.4 mmol/L",
    "organ dysfunction: SBP 86 mmHg"
  ],
  "onset_estimate": "2026-04-15T10:30:00Z",
  "evidence": {
    "lactate_loinc": "2524-7", "lactate_value": 2.4,
    "abx_code": "J01DD04", "sbp": 86
  }
}
```

**Happy path response**

```json
{
  "status": "ok",
  "patient_id": "patient-42",
  "sepsis_suspected": false,
  "mode": "cdc_ase",
  "criteria_met": [],
  "onset_estimate": null,
  "evidence": {"lactate_value": 1.1, "abx_code": null}
}
```

**Error handling:** On any FHIR failure, `status=fhir_error` and `sepsis_suspected=false` (fail-safe: never return `true` without evidence). LLM not used.

---

### 1.4 `generate_escalation_note`

**Purpose:** Produces a clinician-ready SBAR escalation note from the outputs of the first three tools and writes a FHIR `Communication` resource for audit.

**Standard enforced:** None clinically — this is the LLM-backed tool. Content follows SBAR structure (Situation, Background, Assessment, Recommendation). Model: `llama3.1` via Ollama locally, Groq for demo, Claude as fallback.

**FHIR reads:** `Patient/{id}` (name, MRN), `Encounter?patient={id}&status=in-progress`, `Procedure?patient={id}&_sort=-date&_count=1`.
**FHIR writes:** None. The tool returns an unpersisted `communication_draft` (a valid `Communication` resource shape with no `id`). The FastAPI proxy's approve endpoint (`§6.4`) is the only path in the stack that writes `Communication` + `AuditEvent` to HAPI, and it does so only when a clinician clicks Approve in the frontend.

**Input schema**

```python
from typing import Any

class EscalationInput(BaseModel):
    """Input for generate_escalation_note."""

    patient_id: Annotated[str | None, Field(default=None, description="FHIR Patient.id. Optional if SHARP header set.")] = None
    vitals_result: Annotated[dict[str, Any], Field(
        description="Raw JSON from screen_vital_thresholds (ScreenVitalsOutput)."
    )]
    risk_result: Annotated[dict[str, Any], Field(
        description="Raw JSON from score_deterioration_risk (RiskScoreOutput)."
    )]
    sepsis_result: Annotated[dict[str, Any], Field(
        description="Raw JSON from flag_sepsis_onset (SepsisFlagOutput)."
    )]
    recipient_role: Annotated[Literal["charge_nurse", "resident", "attending", "rapid_response"], Field(
        default="charge_nurse",
        description="Drives tone and urgency."
    )] = "charge_nurse"
```

**Output schema**

```python
class SBAR(BaseModel):
    """Structured SBAR block."""

    situation: str       # One-sentence current status
    background: str      # Relevant postop/postpartum context
    assessment: str      # Interpretation of vitals/risk/sepsis
    recommendation: str  # Concrete action requested

class EscalationOutput(BaseModel):
    """Output for generate_escalation_note."""

    status: ToolStatus              # OK | LLM_UNAVAILABLE | FHIR_*
    patient_id: str                 # Echoed back
    sbar: SBAR                      # Structured block
    narrative: str                  # Rendered plain-text version
    severity: Literal["info", "urgent", "critical"]  # Deterministic from inputs
    recipient_role: str             # Echoed back
    communication_draft: dict       # Unpersisted FHIR Communication resource shape — see §5.6. No id; no POST. The FastAPI proxy writes this (status="completed") via the /approve endpoint when a clinician acknowledges.
    generated_at: datetime          # Server clock at LLM completion
    model_used: str                 # "ollama/llama3.1" | "groq/..." | "claude-opus-4-6"
```

**Request example**

```json
{
  "patient_id": "patient-42",
  "vitals_result": { "status": "triggered", "breaches": [ {"label":"SBP","value":86.0} ] },
  "risk_result":   { "status": "ok",        "qsofa_score": 2, "risk_band": "high" },
  "sepsis_result": { "status": "triggered", "sepsis_suspected": true, "mode": "cdc_ase" },
  "recipient_role": "rapid_response"
}
```

**Happy path response**

```json
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

**Error handling**
- **Malformed input:** Pydantic raises.
- **LLM unavailable:** Falls back through Ollama -> Groq -> Claude. If all fail, `status=llm_error`, SBAR populated with a deterministic template-based narrative, `model_used="template_fallback"`.
- **No FHIR write path:** the tool itself never writes. Persistence happens later at the `/approve` endpoint (§6.4); failures there surface as a distinct error on that endpoint, not on this tool.

---

## 2. SHARP Context Contract

**Three HTTP headers, case-insensitive** — verbatim from `po-community-mcp/python/mcp_constants.py`:

```python
FHIR_SERVER_URL_HEADER = "x-fhir-server-url"
FHIR_ACCESS_TOKEN_HEADER = "x-fhir-access-token"
PATIENT_ID_HEADER = "x-patient-id"
```

Source: `https://github.com/prompt-opinion/po-community-mcp/blob/main/python/mcp_constants.py`.

### FhirContext dataclass

From `po-community-mcp/python/fhir_context.py`:

```python
from dataclasses import dataclass

@dataclass
class FhirContext:
    url: str                   # Base URL, e.g. "http://localhost:8080/fhir"
    token: str | None = None   # Bearer token; None for unauth HAPI in dev
```

### Reading headers inside a FastMCP tool

Pattern lifted directly from `po-community-mcp/python/tools/patient_age_tool.py` + `fhir_utilities.py`:

```python
from mcp.server.fastmcp import Context
from fhir_context import FhirContext

def get_fhir_context(ctx: Context) -> FhirContext | None:
    request = ctx.request_context.request  # Starlette Request
    url = request.headers.get("x-fhir-server-url")
    if not url:
        return None
    token = request.headers.get("x-fhir-access-token")
    return FhirContext(url=url, token=token)

def get_patient_id_if_context_exists(ctx: Context) -> str | None:
    request = ctx.request_context.request
    return request.headers.get("x-patient-id")
```

### Advertising capability via `get_capabilities` patch

From `po-community-mcp/python/mcp_instance.py` — we monkey-patch the MCP server to add the extension marker so Prompt Opinion knows to inject FHIR headers:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Vigil Postop Sentinel", stateless_http=True, host="0.0.0.0")

_original_get_capabilities = mcp._mcp_server.get_capabilities

def _patched_get_capabilities(notification_options, experimental_capabilities):
    caps = _original_get_capabilities(notification_options, experimental_capabilities)
    caps.model_extra["extensions"] = {"ai.promptopinion/fhir-context": {}}
    return caps

mcp._mcp_server.get_capabilities = _patched_get_capabilities
```

The extension key `ai.promptopinion/fhir-context` is the signal Prompt Opinion uses to decide whether to forward SHARP headers to this MCP server.

---

## 3. A2A AgentCard Contract

Shape targets the **A2A v1** AgentCard spec (canonical reference: `prompt-opinion/po-adk-python/shared/app_factory.py`). The card is loaded by `app.py` through a thin `AgentCardV1` subclass (see §3.4) so the v1 wire shapes survive the round-trip through the installed v0.3 `a2a-python` SDK; the SDK serves the card via `model_dump(exclude_none=True, by_alias=True)`.

**Endpoints (Option-3 deployment):**

- `GET /.well-known/agent-card.json` — public; whitelisted from API-key middleware (`backend/a2a_agent/app.py::_A2A_SKIP_PREFIXES`).
- `POST /a2a` — JSON-RPC entrypoint (`message/send`, `tasks/get`, …). The card's top-level `url` and `supportedInterfaces[0].url` both point here.
- `POST /tick` — Vigil-internal admin route, not advertised on the card. Triggers `run_cycle_for_all_patients` for the dashboard's "Tick Now" button.

The agent card lives at `backend/a2a_agent/agent_card.json` and is loaded by `app.py` at startup; the `A2A_PUBLIC_URL` env var (set by `deploy/aws/user-data.sh` from `SITE_DOMAIN`) overrides the top-level `url` before validation, so the production deploy ships the canonical HTTPS URL while the dev shape stays valid JSON pointing at `http://localhost:9000/a2a`.

**Vigil's AgentCard JSON** (matches `backend/a2a_agent/agent_card.json` 1:1)

```json
{
  "name": "Vigil — Postop & Postpartum Sentinel",
  "description": "Continuously monitors postoperative and postpartum patients for deterioration. Runs MEWT, qSOFA, and CDC ASE screens against FHIR vitals and labs. Drafts SBAR escalation notes for clinician review.",
  "version": "1.0.0",
  "url": "http://localhost:9000/a2a",
  "provider": {
    "organization": "Team Vigil (Agents Assemble 2026)",
    "url": "https://github.com/raymond/vigil"
  },
  "documentationUrl": "https://github.com/raymond/vigil/blob/main/docs/API_CONTRACTS.md",
  "defaultInputModes":  ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "capabilities": {
    "streaming": false,
    "pushNotifications": false,
    "stateTransitionHistory": false,
    "extensions": [
      {
        "uri": "https://app.promptopinion.ai/schemas/a2a/v1/fhir-context",
        "description": "FHIR context allowing the agent to query a FHIR server securely. Vigil reads the context from A2A message metadata under any key containing the substring 'fhir-context' and translates {fhirUrl, fhirToken, patientId} into the three SHARP HTTP headers when calling its MCP tools.",
        "required": false,
        "params": {
          "scopes": [
            { "name": "patient/Patient.rs",        "required": true },
            { "name": "patient/Observation.rs",    "required": true },
            { "name": "patient/Condition.rs",      "required": true },
            { "name": "patient/MedicationRequest.rs" }
          ]
        }
      }
    ]
  },
  "supportedInterfaces": [
    { "url": "http://localhost:9000/a2a", "protocolBinding": "JSONRPC", "protocolVersion": "1.0" }
  ],
  "skills": [
    { "id": "vigil.screen_vitals",  "name": "Screen vitals for early-warning thresholds", "description": "Runs MEWT against the patient's most recent vitals. Returns triggered/not, breach list with severity, narrative summary.", "tags": ["screen", "vitals", "mewt"] },
    { "id": "vigil.score_risk",     "name": "Score deterioration risk",                  "description": "Computes qSOFA and a composite deterioration band (low/moderate/high). Returns score, rationale, and contributing signals.", "tags": ["risk", "qsofa", "news2"] },
    { "id": "vigil.check_sepsis",   "name": "Check for sepsis onset",                    "description": "Applies CDC Adult Sepsis Event criteria (SIRS + infection + organ dysfunction). Returns suspicion verdict with cited evidence.", "tags": ["sepsis", "ase", "infection"] },
    { "id": "vigil.draft_sbar",     "name": "Draft SBAR escalation note",                "description": "Combines all three screens with the LLM-drafted Situation/Background/Assessment/Recommendation handoff. Returns the prose for clinician review.", "tags": ["sbar", "escalate", "handoff"] },
    { "id": "vigil.start_watching", "name": "Start autonomous watching",                 "description": "Begins background monitoring for the named patient. Optional. Demo-only.", "tags": ["watch", "monitor"] }
  ],
  "securitySchemes": {
    "apiKey": {
      "apiKeySecurityScheme": {
        "name": "X-API-Key",
        "location": "header",
        "description": "API key required to access this agent."
      }
    }
  },
  "security": [ { "apiKey": [] } ]
}
```

Two parent-injected fields appear on the wire even though the source JSON omits them: `"preferredTransport": "JSONRPC"` and `"protocolVersion": "0.3.0"`. Both come from the v0.3 `AgentCard` defaults that we don't override in the subclass; they're harmless alongside the v1 `supportedInterfaces` declaration. When the SDK ships a v1-native card class these defaults disappear.

### 3.1 Skill catalogue

Each skill is a single-purpose handler in `backend/a2a_agent/sentinel.py`. The text response is plain prose suitable for chat surfaces (Prompt Opinion's launchpad chat); structured detail rides as JSON in the `Task.metadata` artifact when the caller wants it.

| Skill ID | Triggering text examples | MCP tool(s) called | Text response shape |
|---|---|---|---|
| `vigil.screen_vitals` | "screen vitals", "any breach in the last 4h", "MEWT", "early-warning" | `screen_vital_thresholds` | One sentence: *"MEWT triggered: SBP 86 (red, <90) and HR 126 (yellow, ≥120) at 11:48Z; 18 obs scanned."* When clean: *"No MEWT breach across 18 observations in the last 240 min."* |
| `vigil.score_risk` | "deterioration risk", "qSOFA", "how worried", "score this patient" | `score_deterioration_risk` | Two sentences: qSOFA + risk band line, then the deterministic rationale and any contributing comorbidities. |
| `vigil.check_sepsis` | "sepsis", "ASE", "septic", "infection workup" | `flag_sepsis_onset` | One paragraph: verdict (`sepsis_suspected: true/false`), mode (`cdc_ase` vs. `sirs_fallback`), the bullet list of criteria met, and the onset estimate when present. |
| `vigil.draft_sbar` | "SBAR", "draft an escalation", "write the handoff", "escalate" | All three screens above + `generate_escalation_note` | Full SBAR prose (S/B/A/R blocks) followed by recipient role and severity. **No review-queue enqueue happens here** (see §3.3). |
| `vigil.start_watching` | "watch this patient", "monitor in the background", "start polling" | none — toggles in-process state on the autonomous loop (see `app.py::_poll_loop`) | One-sentence ack with the cadence and patient id. Demo-only; production deploy keeps `POLL_INTERVAL_SEC=0`. |

The previous draft of this section listed `vigil.monitor_patient` and `vigil.explain_alert`. Both are gone. The first folded into `vigil.draft_sbar` (which is the actual end-to-end escalation flow); the second is deferred per `docs/A2A_REFACTOR_AUDIT.md` Open Q5.

### 3.2 Skill dispatch (two-strategy routing)

The A2A `Message` shape has no native `skill_id` field. Vigil resolves the target skill in `backend/a2a_agent/skill_router.py::resolve_skill` using two strategies, in order:

1. **Metadata hint.** If the inbound `message.metadata` carries a key whose suffix is `skill-id` (e.g. `"http://vigil.local/schemas/a2a/v1/skill-id": "vigil.draft_sbar"`), use that value directly. Mirrors the substring-match convention used for `fhir-context` in §4. This is the path Prompt Opinion's launchpad takes when the user invokes a skill explicitly.
2. **Keyword fallback.** If no metadata hint is present, scan `message.parts[*].text` for the per-skill trigger keywords listed in the §3.1 table. The exact keyword map is the source of truth in `skill_router.py`; treat the column above as illustrative, not exhaustive. Ties resolve in the order the table is written (most specific skills first).

If neither strategy resolves a skill, the router falls back to `vigil.draft_sbar` so the launchpad-chat path always returns useful prose. Per-skill error envelopes follow the `ToolStatus` discriminator from §1; on failure the executor emits a one-line readable summary in `text` and surfaces the structured `ToolError` on the task artifact.

### 3.3 Write semantics — `draft_sbar` does not enqueue

Inside Vigil there are two independent paths that produce SBARs:

- The **autonomous poll loop** (`app.py::_poll_loop`, also reachable via `POST /tick`) is the only path that enqueues alerts to the SQLite review queue (`backend/api/review_queue.py::enqueue_alert`). The clinician dashboard surfaces these and a human approve writes the FHIR `Communication` + `AuditEvent` via the FastAPI proxy (`§6.4`).
- The **A2A `vigil.draft_sbar` skill** returns the SBAR prose to the calling host and stops. It does **not** enqueue, because Prompt Opinion's launchpad chat *is* the human-in-the-loop surface for the Option-3 path; double-enqueuing would produce duplicate clinician work. The agent never POSTs to FHIR; nothing on the A2A path writes anywhere except the in-memory `TaskStore`.

### 3.4 v1 schema notes & the `AgentCardV1` subclass

A2A v1 (per `po-adk-python`) tightens a few fields relative to the v0.x schema this codebase shipped on:

- `capabilities.stateTransitionHistory` MUST be `false` (we set it explicitly).
- `securitySchemes.apiKey` uses the nested form `{ "apiKeySecurityScheme": { "name": ..., "location": "header", ... } }` — note `location`, not `in` — and `security: [{"apiKey": []}]` references it by key.
- `supportedInterfaces` replaces v0.3's `additionalInterfaces`; each entry is `{url, protocolBinding, protocolVersion}` instead of `{transport, url}`.
- The FHIR-context extension URI is `https://app.promptopinion.ai/schemas/a2a/v1/fhir-context` (the v0 form was `ai.promptopinion/fhir-context`).
- Per-scope `required` flags live inside `extensions[].params.scopes[].required`; the extension's top-level `required` stays `false` (declares that the agent functions without context if the host doesn't have one to share).

**Installed-SDK gap and the subclass escape hatch.** `a2a-python` (in `pyproject.toml`) is on the v0.3 schema. Three of the v1 wire fields above don't survive a round-trip through the parent's typed Pydantic fields: `supportedInterfaces` is silently dropped (extra field), the nested `apiKeySecurityScheme` form silently misvalidates as `MutualTLSSecurityScheme` (the discriminated union picks the first compatible variant; mTLS has no required fields), and `apiKeySecurityScheme.location` would fail validation (the parent accepts `in` only).

We adopt the same escape hatch the reference does (`po-adk-python/shared/app_factory.py`): subclass and override the field types so the v1 nested shapes pass through as raw containers.

```python
# backend/a2a_agent/agent_card_v1.py
from typing import Any
from a2a.types import AgentCard, AgentExtension
from pydantic import Field

class AgentExtensionV1(AgentExtension):
    params: dict[str, Any] | None = Field(default=None)

class AgentCardV1(AgentCard):
    supportedInterfaces: list[dict[str, Any]] = Field(default_factory=list)
    securitySchemes: dict[str, Any] | None = None
```

`app.py` then loads the card via `AgentCardV1.model_validate(_card_data)` instead of the parent class. A round-trip smoke verified that `securitySchemes.apiKey.apiKeySecurityScheme.location`, `supportedInterfaces[].protocolBinding`/`protocolVersion`, and `extensions[0].params.scopes` all survive serialization on the way out.

Two harmless v0.3-defaulted fields still appear on the served wire because the subclass doesn't override them: `preferredTransport: "JSONRPC"` and `protocolVersion: "0.3.0"`. Both are tolerated alongside the v1 declarations; if Prompt Opinion's `Add Connection → Check` flags either, add explicit overrides to `AgentCardV1`. When `a2a-sdk` ships a v1-native card class with the matching shapes, drop `agent_card_v1.py` and switch `app.py` back to importing `AgentCard` directly.

---

## 4. A2A Message Contract (FHIR via metadata, not headers)

**Critical distinction:** MCP calls use 3 HTTP headers for SHARP context. **A2A calls use message metadata** — the FHIR credentials travel inside the JSON-RPC body, not in HTTP headers. This is how Prompt Opinion hands context to ADK agents. Source: `po-adk-python/shared/fhir_hook.py` + `shared/middleware.py`.

### Wire format

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [{ "kind": "text", "text": "Screen patient-42 for deterioration." }],
      "metadata": {
        "http://vigil.local/schemas/a2a/v1/fhir-context": {
          "fhirUrl":   "http://localhost:8080/fhir",
          "fhirToken": "",
          "patientId": "patient-42"
        }
      }
    }
  }
}
```

The metadata key MUST contain the substring `fhir-context` (constant `FHIR_CONTEXT_KEY = "fhir-context"` in `po-adk-python/shared/fhir_hook.py`). The hook matches by substring, not exact URI, so any URI-shaped key containing `fhir-context` works.

### `extract_fhir_context` callback pattern

Adapted verbatim from `po-adk-python/shared/fhir_hook.py` (`https://github.com/prompt-opinion/po-adk-python/blob/main/shared/fhir_hook.py`). When using the a2a-sdk directly instead of ADK, register the equivalent as a request-intercept middleware:

```python
# backend/a2a_agent/fhir_hook.py
import json
from typing import Any

FHIR_CONTEXT_KEY = "fhir-context"

def _coerce(value: Any) -> dict | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None

def extract_fhir_from_payload(payload: dict) -> tuple[str | None, dict | None]:
    """Return (metadata_key, fhir_dict) or (None, None).

    Checks params.metadata first, then params.message.metadata as fallback
    — matches po-adk-python middleware's bridging behaviour.
    """
    if not isinstance(payload, dict):
        return None, None
    params = payload.get("params") or {}
    candidates = [
        params.get("metadata"),
        (params.get("message") or {}).get("metadata"),
    ]
    for meta in candidates:
        if isinstance(meta, dict):
            for key, value in meta.items():
                if FHIR_CONTEXT_KEY in str(key):
                    return key, _coerce(value)
    return None, None
```

In the Vigil A2A server, the agent's request handler calls `extract_fhir_from_payload` once per incoming JSON-RPC request and stores `(fhirUrl, fhirToken, patientId)` on the current task context. When the agent internally calls the MCP server, it translates them back into the 3 SHARP headers.

---

## 5. FHIR R4 Resource Shapes

All examples are valid FHIR R4 as served by HAPI `v7.2.0`. LOINC codes confirmed against `https://build.fhir.org/observation-vitalsigns.html`.

### 5.1 Observation — vital sign (SBP example)

```json
{
  "resourceType": "Observation",
  "id": "obs-sbp-884",
  "status": "final",
  "category": [{
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/observation-category",
      "code": "vital-signs",
      "display": "Vital Signs"
    }]
  }],
  "code": {
    "coding": [{ "system": "http://loinc.org", "code": "8480-6", "display": "Systolic blood pressure" }],
    "text": "SBP"
  },
  "subject": { "reference": "Patient/patient-42" },
  "encounter": { "reference": "Encounter/enc-77" },
  "effectiveDateTime": "2026-04-15T11:48:00Z",
  "valueQuantity": { "value": 86, "unit": "mm[Hg]", "system": "http://unitsofmeasure.org", "code": "mm[Hg]" }
}
```

LOINC table used by Vigil (all category `vital-signs` unless noted):

| Vital | LOINC | UCUM unit |
|---|---|---|
| Systolic BP | `8480-6` | `mm[Hg]` |
| Diastolic BP | `8462-4` | `mm[Hg]` |
| Heart rate | `8867-4` | `/min` |
| Respiratory rate | `9279-1` | `/min` |
| SpO2 | `59408-5` | `%` |
| Body temperature | `8310-5` | `Cel` |
| Urine output (24h) | `9192-6` | `mL` |

### 5.2 Patient (minimal synthetic)

```json
{
  "resourceType": "Patient",
  "id": "patient-42",
  "identifier": [{
    "system": "http://vigil.local/mrn",
    "value": "MRN-0042"
  }],
  "name": [{ "family": "Doe", "given": ["Jane"] }],
  "gender": "female",
  "birthDate": "1983-07-19"
}
```

### 5.3 Encounter (procedure visit)

```json
{
  "resourceType": "Encounter",
  "id": "enc-77",
  "status": "in-progress",
  "class": { "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP", "display": "inpatient encounter" },
  "type": [{
    "coding": [{ "system": "http://snomed.info/sct", "code": "8715000", "display": "Hospital admission for surgical procedure" }]
  }],
  "subject": { "reference": "Patient/patient-42" },
  "period": { "start": "2026-04-14T17:30:00Z" },
  "participant": [{
    "type": [{ "coding": [{ "system": "http://terminology.hl7.org/CodeSystem/v3-ParticipationType", "code": "PPRF", "display": "primary performer" }]}],
    "individual": { "reference": "Practitioner/prac-surgeon-9", "display": "Dr. Chen" }
  }]
}
```

### 5.4 Procedure

```json
{
  "resourceType": "Procedure",
  "id": "proc-321",
  "status": "completed",
  "code": {
    "coding": [{ "system": "http://snomed.info/sct", "code": "38628009", "display": "Laparoscopic cholecystectomy" }]
  },
  "subject": { "reference": "Patient/patient-42" },
  "encounter": { "reference": "Encounter/enc-77" },
  "performedDateTime": "2026-04-14T18:10:00Z"
}
```

### 5.5 Condition (comorbidity)

```json
{
  "resourceType": "Condition",
  "id": "cond-101",
  "clinicalStatus": { "coding": [{ "system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active" }] },
  "verificationStatus": { "coding": [{ "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed" }] },
  "code": {
    "coding": [{ "system": "http://snomed.info/sct", "code": "44054006", "display": "Type 2 diabetes mellitus" }]
  },
  "subject": { "reference": "Patient/patient-42" },
  "recordedDate": "2024-11-02"
}
```

### 5.6 Communication (SBAR escalation — draft shape returned inside `communication_draft`)

> This is the shape `generate_escalation_note` returns inside its `communication_draft` field — unpersisted, no `id`, `status="in-progress"`. On clinician approve, the FastAPI proxy (`§6.4`) POSTs this body to HAPI with `status` flipped to `"completed"` and an `AuditEvent` emitted alongside. The tool never POSTs. The agent never POSTs.


```json
{
  "resourceType": "Communication",
  "id": "comm-884",
  "status": "in-progress",
  "category": [{
    "coding": [{ "system": "http://terminology.hl7.org/CodeSystem/communication-category", "code": "alert" }]
  }],
  "priority": "urgent",
  "subject": { "reference": "Patient/patient-42" },
  "encounter": { "reference": "Encounter/enc-77" },
  "sent": "2026-04-15T12:01:10Z",
  "sender": { "reference": "Device/vigil-postop-sentinel", "display": "Vigil Postop Sentinel" },
  "recipient": [{ "reference": "PractitionerRole/rapid-response", "display": "Rapid Response Team" }],
  "payload": [{
    "contentString": "S: Post-op day 1 patient with SBP 86 and qSOFA 2; sepsis suspected.\nB: 42yo s/p lap chole 18h ago; Hx T2DM.\nA: Meets CDC ASE: lactate 2.4, SBP 86, abx started.\nR: Activate rapid response, repeat lactate, 500ml NS bolus, notify attending."
  }]
}
```

### 5.7 AuditEvent (agent action log)

```json
{
  "resourceType": "AuditEvent",
  "id": "audit-55",
  "type": { "system": "http://dicom.nema.org/resources/ontology/DCM", "code": "110100", "display": "Application Activity" },
  "subtype": [{ "system": "http://vigil.local/audit", "code": "tool.flag_sepsis_onset" }],
  "action": "E",
  "recorded": "2026-04-15T12:01:09Z",
  "outcome": "0",
  "agent": [{
    "who": { "reference": "Device/vigil-postop-sentinel" },
    "requestor": false,
    "type": { "coding": [{ "system": "http://terminology.hl7.org/CodeSystem/extra-security-role-type", "code": "AGNT" }] }
  }],
  "source": {
    "observer": { "reference": "Device/vigil-postop-sentinel" }
  },
  "entity": [{
    "what": { "reference": "Patient/patient-42" },
    "type": { "system": "http://terminology.hl7.org/CodeSystem/audit-entity-type", "code": "1" }
  }]
}
```

---

## 6. Frontend API Contract

**Decision: option (b) — thin FastAPI proxy at `backend/api/`.** Direct HAPI calls from the Next.js frontend would leak bearer tokens into the browser and would force the UI to do FHIR bundle parsing on every render. The proxy aggregates and normalizes. It is **read-mostly**; the approve endpoint is a mock clinician action.

Base URL: `http://localhost:8000/api`. All responses are JSON. Errors follow `{"error": "...", "detail": "..."}` with appropriate HTTP codes.

### `GET /api/patients`

List of monitored patients with a status summary.

Response:

```json
{
  "patients": [
    {
      "id": "patient-42",
      "mrn": "MRN-0042",
      "name": "Jane Doe",
      "age": 42,
      "trajectory": "postop",
      "latest_risk_band": "high",
      "latest_alert_at": "2026-04-15T12:01:10Z",
      "unread_alerts": 1
    }
  ]
}
```

### `GET /api/patients/{id}`

Full dashboard payload for a patient detail page.

```json
{
  "patient": { "id": "patient-42", "mrn": "MRN-0042", "name": "Jane Doe", "age": 42, "birth_date": "1983-07-19", "gender": "female" },
  "encounter": { "id": "enc-77", "start": "2026-04-14T17:30:00Z", "status": "in-progress" },
  "procedure": { "code": "38628009", "display": "Laparoscopic cholecystectomy", "performed_at": "2026-04-14T18:10:00Z" },
  "comorbidities": [{ "code": "44054006", "display": "Type 2 diabetes mellitus" }],
  "vitals_timeseries": [
    { "loinc": "8480-6", "label": "SBP", "unit": "mm[Hg]",
      "points": [{ "t": "2026-04-15T11:48:00Z", "v": 86 }, { "t": "2026-04-15T11:00:00Z", "v": 102 }] }
  ],
  "risk": { "qsofa_score": 2, "composite_risk": 0.71, "band": "high", "rationale": "qSOFA=2 meets sepsis screen." },
  "recent_alerts": [
    { "id": "comm-884", "severity": "critical", "sent": "2026-04-15T12:01:10Z", "status": "in-progress" }
  ]
}
```

### `GET /api/patients/{id}/alerts/latest`

Returns the most recent SBAR for a patient.

```json
{
  "alert_id": "comm-884",
  "severity": "critical",
  "sent": "2026-04-15T12:01:10Z",
  "recipient_role": "rapid_response",
  "sbar": {
    "situation": "Post-op day 1 with SBP 86 and qSOFA 2; sepsis suspected.",
    "background": "42yo s/p lap chole 18h ago; Hx T2DM.",
    "assessment": "Meets CDC ASE criteria.",
    "recommendation": "Rapid response, repeat lactate, 500ml NS, notify attending."
  },
  "narrative": "S: ... B: ... A: ... R: ...",
  "model_used": "ollama/llama3.1",
  "status": "in-progress"
}
```

### `POST /api/patients/{id}/alerts/{alertId}/approve`

Mock clinician ack. Flips the FHIR `Communication.status` from `in-progress` to `completed` and writes an `AuditEvent`.

Request body:

```json
{ "clinician_id": "prac-nurse-17", "note": "Acknowledged, RRT dispatched." }
```

Response:

```json
{ "alert_id": "comm-884", "status": "completed", "acknowledged_at": "2026-04-15T12:03:44Z", "audit_id": "audit-56" }
```

### Frontend-to-backend auth

For the hackathon: single shared `X-API-Key` header on all `/api/*` calls (matches `po-adk-python` middleware convention). Production would upgrade to OIDC.

---

## 7. Versioning & Compatibility

- **MCP tools:** Tool names are frozen at v1. New fields on input/output schemas MUST be optional with a default — Pydantic will accept old clients. Removing or renaming a field requires a new tool name (e.g. `score_deterioration_risk_v2`). Breaking changes are never silent.
- **AgentCard:** `version` follows semver. Minor bumps add skills or optional extensions; major bumps may change the `url` or remove a skill. Clients should read `protocol_version` to negotiate.
- **FHIR resources:** Vigil reads R4 only. If HAPI is upgraded, we pin `hapiproject/hapi:v7.2.0`. Custom profiles (if any) live under `http://vigil.local/StructureDefinition/*` and are additive.
- **Frontend API:** URL-prefixed versioning (`/api/v1/...`) will be introduced the first time we need a breaking change. Until then, additive only: new fields appear in responses, old fields never disappear mid-version.
- **SHARP headers:** Controlled by Prompt Opinion, not us. We forward whatever they send and never rename the three header constants.

---

## Appendix: Source citations

- SHARP headers & FHIR client & capability patch: `https://github.com/prompt-opinion/po-community-mcp/tree/main/python` (`mcp_constants.py`, `fhir_context.py`, `fhir_client.py`, `mcp_instance.py`, `tools/patient_age_tool.py`).
- A2A FHIR metadata pattern: `https://github.com/prompt-opinion/po-adk-python/blob/main/shared/fhir_hook.py` and `shared/middleware.py`.
- AgentCard / AgentSkill / AgentExtension types: `https://github.com/google/a2a-python/blob/main/src/a2a/types.py`.
- FHIR R4 vital signs profile & LOINC codes: `https://build.fhir.org/observation-vitalsigns.html`.
- qSOFA: `https://www.mdcalc.com/calc/3909/qsofa-quick-sofa-score-sepsis`.
- CDC Adult Sepsis Event: `https://www.cdc.gov/sepsis/hcp/clinical-tools/index.html`.
- MEWS: `https://www.mdcalc.com/calc/1875/modified-early-warning-score-mews-clinical-deterioration`.
