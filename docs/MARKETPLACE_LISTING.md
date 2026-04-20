# Prompt Opinion Marketplace Listings — Vigil

> **Draft listings for both marketplace paths.** The user submits these through the Prompt Opinion publishing flow (see `PROMPT_OPINION_INTEGRATION.md` §6). Publishing method TBD — likely paste-your-URL + API key.

---

## Path A — MCP Server

### Title

```
Vigil Clinical Deterioration Toolkit
```

### Subtitle / Short description

```
Four reusable MCP tools for postoperative and postpartum early-warning screening. MEWT + qSOFA + CDC ASE + SBAR generation — all on FHIR R4, all deterministic, all composable.
```

### Full description

Vigil's MCP server exposes four clinical decision-support tools over Anthropic's Model Context Protocol (streamable HTTP transport). Any MCP-compatible agent on the Prompt Opinion platform can call them. Each tool enforces a published clinical standard deterministically, then optionally layers an LLM reasoning pass for patient-specific context.

**Key properties:**
- **FHIR R4 in, structured JSON out.** Every tool reads from a FHIR server via SHARP headers. No custom extensions — vanilla Observations, Conditions, Encounters.
- **Deterministic clinical rules.** MEWT thresholds (Shields 2016), qSOFA scoring (Singer 2016, Sepsis-3), CDC Adult Sepsis Event criteria (2018). The LLM adds context, never decides whether to escalate.
- **Substitutable.** Same tools work on postop cardiac surgery patients and postpartum sepsis patients. Zero code changes between wards.
- **Stateless.** `stateless_http=True` — every request carries its own FHIR context via SHARP headers.

### Tools

| # | Tool name | Description | Input | Output |
|---|---|---|---|---|
| 1 | `screen_vital_thresholds` | Fetches recent FHIR Observations (vital-signs category) and checks against MEWT/qSOFA thresholds. Returns NORMAL or TRIGGERED with breach details. | `patientId` (optional if SHARP `x-patient-id` set), `lookback_minutes` (default 360) | `{ status, breaches[], mewt_score, qsofa_score, scanned_count, rationale }` |
| 2 | `score_deterioration_risk` | Reads ≥3 vital-sign readings over a time window, computes composite risk (qSOFA base + breach weight + condition weight), returns a risk band. | `patientId`, `window_hours` (default 6) | `{ risk_band: "low"|"moderate"|"high", composite_risk: float, qsofa_score, contributing_factors[], rationale }` |
| 3 | `flag_sepsis_onset` | Applies CDC Adult Sepsis Event criteria: presumed infection + organ dysfunction (lactate, creatinine, platelets, bilirubin). Falls back to SIRS (2-of-4) when labs are sparse. | `patientId` | `{ sepsis_suspected: bool, severity: "none"|"possible"|"confirmed", criteria_met[], organ_dysfunction[], rationale }` |
| 4 | `generate_escalation_note` | Consumes outputs from tools 1–3, fetches Patient + Encounter from FHIR, calls LLM to draft a structured SBAR escalation note. **Never writes to FHIR** — returns the draft for clinician approval. | `patientId`, `vitals_result`, `risk_result`, `sepsis_result` | `{ sbar: { situation, background, assessment, recommendation }, communication_draft: FHIR Communication shape, severity, recipient_role }` |

### SHARP requirements

| Header | Required? | Notes |
|---|---|---|
| `x-fhir-server-url` | **Yes** | 400 error if missing. Validated against allowlist (SSRF protection). |
| `x-fhir-access-token` | No | Empty tolerated for dev HAPI (no auth). |
| `x-patient-id` | No | Can come from tool input `patientId` param instead. |

**Capability extension:** Server advertises `ai.promptopinion/fhir-context` so Prompt Opinion knows to inject headers.

### Example invocations

**Screen vitals (curl):**
```bash
curl -X POST https://<vigil-mcp-url>/ \
  -H "Content-Type: application/json" \
  -H "x-fhir-server-url: http://hapi:8080/fhir" \
  -H "x-patient-id: PT-007" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "tools/call",
    "params": {
      "name": "screen_vital_thresholds",
      "arguments": { "lookback_minutes": 360 }
    }
  }'
```

**Score risk (MCP SDK):**
```python
from mcp import ClientSession

async with ClientSession(transport) as session:
    result = await session.call_tool(
        "score_deterioration_risk",
        arguments={"patientId": "PT-007", "window_hours": 6},
    )
    print(result.content[0].text)  # {"risk_band": "high", ...}
```

### FHIR resources consumed

| Resource | Direction | LOINC codes used |
|---|---|---|
| `Observation` (vital-signs) | Read | 8480-6, 8462-4, 8867-4, 9279-1, 59408-5, 8310-5 |
| `Observation` (laboratory) | Read | 2524-7, 6690-2, 2160-0, 1975-2, 777-3 |
| `Condition` | Read | Active comorbidities for risk weighting |
| `Encounter` | Read | Admission context, procedure type |
| `Patient` | Read | Demographics for SBAR context |

### Screenshots

| Screenshot | File |
|---|---|
| Agent timeline showing 4 tool calls | `docs/img/agent-timeline.png` |
| Patient detail with vitals trend | `docs/img/patient-detail.png` |
| SBAR escalation note panel | `docs/img/sbar-panel.png` |

---

## Path B — A2A Agent

### Title

```
Vigil Postop Sentinel
```

### Subtitle / Short description

```
A2A agent that monitors postop and postpartum patients for deterioration. Runs a 7-state machine, calls 4 MCP tools, drafts SBAR notes — never acts without clinician approval.
```

### Full description

The Vigil Postop Sentinel is an A2A agent (Agent-to-Agent protocol, JSON-RPC) that continuously monitors patients for signs of clinical deterioration. It orchestrates Vigil's four MCP tools in a state machine:

```
IDLE → POLLING → SCREENING → RISK_SCORING → SEPSIS_CHECK →
  [if triggered: ESCALATING → AWAITING_REVIEW] → back to IDLE
```

**How it works:**
1. Agent tick fires (configurable interval, default 900s, 30s for demo).
2. Fetches latest FHIR Observations for the patient.
3. Calls `screen_vital_thresholds` — if NORMAL, returns to IDLE.
4. If TRIGGERED, calls `score_deterioration_risk` and `flag_sepsis_onset`.
5. If any escalation condition met, calls `generate_escalation_note`.
6. Posts the SBAR draft to the review queue. **Never writes to FHIR.**
7. Clinician reviews in the dashboard, clicks "Approve & send RRT."
8. FastAPI proxy writes `Communication` + `AuditEvent` to HAPI FHIR.

**Key properties:**
- **Human in the loop.** Every escalation requires explicit clinician approval. The agent drafts, it waits.
- **FHIR context via metadata.** The A2A message `metadata` carries FHIR server URL, bearer token, and patient ID under the `fhir-context` key. The agent bridges this to SHARP headers for downstream MCP calls.
- **LLM-agnostic.** `LLM_PROVIDER` env var switches between Ollama, Groq, Claude, or stub. No model lock-in.
- **Same agent, different ward.** No code changes between postop cardiac surgery and postpartum sepsis paths.

### Agent card

Served at `GET /.well-known/agent-card.json`.

```json
{
  "name": "Vigil Postop Sentinel",
  "description": "Continuously monitors postop and postpartum patients for deterioration. Runs MEWT, qSOFA, and CDC ASE screens against FHIR vitals and labs, then drafts SBAR escalation notes for the clinical team.",
  "version": "0.1.0",
  "url": "https://<deploy>/a2a",
  "preferred_transport": "JSONRPC",
  "protocol_version": "0.2",
  "provider": {
    "organization": "Team Vigil (Agents Assemble 2026)",
    "url": "https://github.com/RaymonddC/Vigil"
  },
  "capabilities": {
    "streaming": true,
    "push_notifications": false,
    "extensions": [
      {
        "uri": "ai.promptopinion/fhir-context",
        "description": "Accepts FHIR context via A2A message metadata.",
        "required": true,
        "params": {
          "metadata_key_suffix": "fhir-context",
          "fields": ["fhirUrl", "fhirToken", "patientId"]
        }
      }
    ]
  },
  "skills": [
    {
      "id": "vigil.monitor_patient",
      "name": "Monitor patient for deterioration",
      "description": "End-to-end screen: pulls recent vitals and labs, runs MEWT + qSOFA + CDC ASE, and returns a structured alert with an SBAR note when any trigger fires.",
      "tags": ["healthcare", "postop", "postpartum", "sepsis", "early-warning"]
    },
    {
      "id": "vigil.explain_alert",
      "name": "Explain an existing alert",
      "description": "Given a prior alert id, returns the evidence trail.",
      "tags": ["healthcare", "explainability"]
    }
  ],
  "security_schemes": {
    "apiKey": { "type": "apiKey", "in": "header", "name": "X-API-Key" }
  },
  "security": [{ "apiKey": [] }]
}
```

### SHARP requirements (via A2A metadata)

FHIR context is NOT passed via HTTP headers on the A2A path. Instead, it travels inside the JSON-RPC message metadata:

```json
{
  "params": {
    "message": {
      "metadata": {
        "https://vigil.local/schemas/a2a/v1/fhir-context": {
          "fhirUrl": "http://hapi:8080/fhir",
          "fhirToken": "",
          "patientId": "PT-007"
        }
      }
    }
  }
}
```

The agent extracts this via `extract_fhir_from_metadata()` and bridges it to SHARP headers for downstream MCP tool calls.

### Example invocation (curl)

```bash
curl -X POST https://<vigil-agent-url>/a2a \
  -H "X-API-Key: <your-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{ "kind": "text", "text": "Screen PT-007 for deterioration" }],
        "metadata": {
          "https://vigil.local/schemas/a2a/v1/fhir-context": {
            "fhirUrl": "http://hapi:8080/fhir",
            "fhirToken": "",
            "patientId": "PT-007"
          }
        }
      }
    }
  }'
```

### State machine

| State | Trigger | MCP tool called | Outcome |
|---|---|---|---|
| IDLE | Timer / manual tick | — | → POLLING |
| POLLING | Fetch latest Observations | — | → SCREENING |
| SCREENING | Run threshold check | `screen_vital_thresholds` | NORMAL → IDLE, TRIGGERED → RISK_SCORING |
| RISK_SCORING | Trend analysis | `score_deterioration_risk` | → SEPSIS_CHECK |
| SEPSIS_CHECK | CDC ASE criteria | `flag_sepsis_onset` | → ESCALATING (if triggered) or IDLE |
| ESCALATING | Draft SBAR | `generate_escalation_note` | → AWAITING_REVIEW |
| AWAITING_REVIEW | Clinician action | — | Approve → FHIR write, Dismiss → IDLE |

### Screenshots

| Screenshot | File |
|---|---|
| Agent timeline with state badges | `docs/img/agent-timeline.png` |
| Review queue with approve button | `docs/img/review-queue.png` |
| Sonner toast after approval | `docs/img/approve-toast.png` |

---

## Config file drafts (speculative)

> **Status:** No `prompt_opinion_config.json` exists in either reference repo. These are drafted optimistically. Confirm format on Discord before submission. See `PROMPT_OPINION_INTEGRATION.md` §7.

### MCP Server config

```json
{
  "name": "vigil-mcp",
  "version": "1.0.0",
  "type": "mcp_server",
  "description": "Four clinical early-warning tools for postoperative and postpartum deterioration detection. FHIR R4 in, structured JSON out.",
  "tools": [
    "screen_vital_thresholds",
    "score_deterioration_risk",
    "flag_sepsis_onset",
    "generate_escalation_note"
  ],
  "fhir_resources_required": [
    "Patient",
    "Observation",
    "Condition",
    "Encounter",
    "Procedure"
  ],
  "sharp_context": true,
  "capabilities": {
    "extensions": {
      "ai.promptopinion/fhir-context": {}
    }
  },
  "tags": [
    "healthcare",
    "clinical-decision-support",
    "postoperative",
    "postpartum",
    "sepsis",
    "mewt",
    "qsofa",
    "sbar",
    "fhir-r4"
  ]
}
```

### A2A Agent config

```json
{
  "name": "vigil-agent",
  "version": "1.0.0",
  "type": "a2a_agent",
  "description": "Postoperative + postpartum deterioration sentinel. Orchestrates 4 MCP tools in a 7-state machine and drafts SBAR escalation notes for clinician approval.",
  "agent_card_url": "https://<deploy>/.well-known/agent-card.json",
  "security": {
    "apiKey": {
      "header": "X-API-Key"
    }
  },
  "fhir_extension_uri": "ai.promptopinion/fhir-context",
  "tags": [
    "healthcare",
    "agentic",
    "postoperative",
    "postpartum",
    "sepsis",
    "sbar",
    "early-warning"
  ]
}
```

---

## Publishing checklist

- [ ] Deploy MCP server to Cloud Run / Railway / Fly with public URL
- [ ] Deploy A2A agent to Cloud Run / Railway / Fly with public URL
- [ ] Verify `GET /.well-known/agent-card.json` returns valid JSON
- [ ] Verify MCP capability extension includes `ai.promptopinion/fhir-context`
- [ ] Test end-to-end with curl examples above against deployed URLs
- [ ] Register on Prompt Opinion (method TBD — URL paste + API key likely)
- [ ] Attach screenshots from `docs/img/`
- [ ] If registration is blocked: document deployed URLs in Devpost, include curl examples in README

---

## Fallback (if marketplace publishing is blocked at deadline)

Per `PROMPT_OPINION_INTEGRATION.md` §6:
- Submit GitHub repo URL + demo video directly to Devpost
- Note in description: "Deployed to Cloud Run at `<url>`; agent card at `<url>/.well-known/agent-card.json`; Prompt Opinion registration pending per Discord guidance"
- Include curl invocation examples in README so judges can reproduce
