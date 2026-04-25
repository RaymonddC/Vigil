# A2A local smoke — Option 3 wave 2

_Generated 2026-04-26 by `smoke-test` teammate._
_Branch: `submission/option-3-a2a` (HEAD `76c1c6b`)._

End-to-end smoke against a freshly restarted local stack. Verifies the
v1 wire-form agent card, the new 5-skill dispatch path, and the three
documented graceful-failure modes. No source code or tests changed.

---

## Method

### Services started
- `mcp` — `uv run python -m backend.mcp_server.server` on `:7001`
- `a2a` — `uv run python -m backend.a2a_agent` on `:9000`
- `hapi` — already running on `:8080` (`curl http://localhost:8080/fhir/metadata` → 200)
- `frontend`, `api`, `fixture` — **not** started; not part of Option 3 serving path.

The two pre-existing dev processes started 2026-04-25 19:19 (PIDs 24711, 24715) — five hours **before** the wave-1 commits (`14b64d4 → 76c1c6b` landed 2026-04-26 00:14–00:21). They were running stale code, so I killed and relaunched both from the current `submission/option-3-a2a` HEAD.

### Environment
- `LLM_PROVIDER=stub` (per brief — SBAR returns canned template; deterministic)
- `FHIR_BASE_URL=http://localhost:8080/fhir`
- `VIGIL_API_KEY=local-dev-key-anything` on the **A2A** process (so `/a2a` POST requires the header).
- `VIGIL_API_KEY` **unset** on the **MCP** process. Required workaround — see HIGH finding #1 below. The brief explicitly permits this ("If `VIGIL_API_KEY` isn't set, the middleware logs a warning and disables enforcement … fine for smoke").

### Tooling
- `curl` for the agent-card GET.
- `uv run python /tmp/vigil-smoke/smoke.py` (httpx) for JSON-RPC POSTs. Harness lives outside the repo; not committed.

---

## Results

### 1. Wire-form agent card

`curl -fsS http://localhost:9000/.well-known/agent-card.json | python3 -m json.tool`

| Assertion | Result |
|---|---|
| 5 skill IDs match locked set (`screen_vitals` / `score_risk` / `check_sepsis` / `draft_sbar` / `start_watching`) | ✅ |
| `capabilities.extensions[0].uri == "https://app.promptopinion.ai/schemas/a2a/v1/fhir-context"` | ✅ |
| `capabilities.extensions[0].params.scopes` lists 4 SMART scopes | ✅ |
| Patient/Observation/Condition each carry `required: true` | ✅ |
| `MedicationRequest.rs` carries no `required` flag | ✅ |
| `securitySchemes.apiKey.apiKeySecurityScheme.location == "header"` (NOT v0.3 `"in"`) | ✅ — the v1-form survives `model_validate → model_dump(by_alias=True)` |
| `supportedInterfaces[0].protocolBinding == "JSONRPC"` | ✅ |
| `supportedInterfaces[0].protocolVersion == "1.0"` | ✅ |
| `capabilities.streaming == false` | ✅ |
| `capabilities.pushNotifications == false` | ✅ |
| `capabilities.stateTransitionHistory == false` | ✅ |

Notable also-rans (not asserted by brief, recorded for context):
- Top-level `protocolVersion: "0.3.0"` — this is the SDK's A2A protocol version, distinct from the v1.0 declared on `supportedInterfaces`. Not a regression; matches what the v0.3 SDK serialises.
- Top-level `preferredTransport: "JSONRPC"` is also present (SDK default); not in the JSON file but emitted on the wire.
- The FHIR-context extension declares `"required": false`. The audit's prior recommendation was `"required": true` so Prompt Opinion's "Add Connection" UI would auto-prompt for FHIR. **Worth confirming with team-lead** whether this was a deliberate downgrade in the wave-1 rewrite.

Served-bytes excerpt confirming the v1 nested form:

```json
"securitySchemes": {
  "apiKey": {
    "apiKeySecurityScheme": {
      "name": "X-API-Key",
      "location": "header",
      "description": "API key required to access this agent."
    }
  }
}
```

### 2. Skill dispatch — metadata strategy

POST `/a2a` with `metadata.skill_id = "<skill>"` plus the FHIR-context block. All five round-tripped cleanly. Verified `result.status.message.metadata.skill` echoes the requested skill on every reply.

| `skill_id` requested | resolved (`result.status.message.metadata.skill`) | response excerpt (≤200 chars) | ✅/⚠️ |
|---|---|---|---|
| `vigil.screen_vitals`  | `vigil.screen_vitals`  | `Vital screen for \`PT-001\`: no MEWT breaches across \`0\` recent observations. All vitals within thresholds.` | ✅ |
| `vigil.score_risk`     | `vigil.score_risk`     | `Deterioration risk for \`PT-001\`: band \`low\` (qSOFA \`0 / 3\`, composite \`0.05\`). Rationale: qSOFA=0; No qSOFA criteria met; 1 active condition(s)` | ✅ |
| `vigil.check_sepsis`   | `vigil.check_sepsis`   | `Sepsis screen for \`PT-001\`: not suspected. Mode \`cdc_ase\`, no criteria met.` | ✅ |
| `vigil.draft_sbar`     | `vigil.draft_sbar`     | `SBAR for \`PT-001\` — severity \`info\`, recipient \`charge_nurse\` (model \`stub/template\`).  S: Patient shows signs requiring clinical attention. B: Postoperative monitoring detected parameter changes.` | ✅ |
| `vigil.start_watching` | `vigil.start_watching` | `Vigil's autonomous polling loop is configured at the deployment level via the \`POLL_INTERVAL_SEC\` env var (set to \`0\` in Option 3 to disable). To enable continuous monitoring of \`PT-001\`...` | ✅ |

All five: `HTTP 200`, `result.status.state == "completed"`, single text part, prose (not raw JSON, not stack trace, not unfilled template).

Full raw response shape for `vigil.screen_vitals` (verbatim):

```json
{
  "id": "1",
  "jsonrpc": "2.0",
  "result": {
    "contextId": "6a5fba3e-2c58-4a8b-ab24-e9edc7fa3b4a",
    "id": "3a090695-e507-4390-9687-b2c8e0df12eb",
    "kind": "task",
    "status": {
      "message": {
        "kind": "message",
        "messageId": "c3b4610e-9be4-4fb2-845c-882f7cb400ec",
        "metadata": {"skill": "vigil.screen_vitals", "patient_id": "PT-001"},
        "parts": [{"kind": "text", "text": "Vital screen for `PT-001`: no MEWT breaches across `0` recent observations. All vitals within thresholds."}],
        "role": "agent"
      },
      "state": "completed"
    }
  }
}
```

### 3. Skill dispatch — keyword strategy

POST `/a2a` with the FHIR-context block but **no** `skill_id` — keyword resolution drives off `parts[0].text`.

| text prompt | resolved skill | expected | ✅/⚠️ |
|---|---|---|---|
| `Check this patient for sepsis`   | `vigil.check_sepsis`   | `vigil.check_sepsis`   | ✅ |
| `Draft an SBAR escalation note`   | `vigil.draft_sbar`     | `vigil.draft_sbar`     | ✅ |
| `Score deterioration risk`        | `vigil.score_risk`     | `vigil.score_risk`     | ✅ |
| `Run vital sign screen`           | `vigil.screen_vitals`  | `vigil.screen_vitals`  | ✅ |
| `Start watching this patient`     | `vigil.start_watching` | `vigil.start_watching` | ✅ |
| `""` (empty)                      | `vigil.screen_vitals`  | `vigil.screen_vitals` (default) | ✅ |

All six: `HTTP 200`, `result.status.state == "completed"`, prose body in the same shape as cycle 1. Empty-text case correctly falls through to `DEFAULT_SKILL` (`vigil.screen_vitals`) per `skill_router.py:43`.

### 4. Failure modes

All three failure modes return `HTTP 200` and `result.status.state == "completed"` with a friendly one-liner — never `failed`, never 5xx.

| Mode | Result |
|---|---|
| (a) **No FHIR context** — entire `metadata` object dropped | ✅ `state=completed`. Reply: _"I couldn't run any check because the request was missing FHIR connection context. Please ensure the FHIR-context extension is enabled on this agent connection."_ — emitted from `sentinel.py:103-108`. |
| (b) **`patientId` missing** from FHIR context | ✅ `state=completed`. Reply: _"I couldn't run any check because no patient_id was supplied in the FHIR context. Pick a patient in Prompt Opinion before invoking this skill."_ — emitted from `sentinel.py:115-120`. |
| (c) **MCP unreachable** (killed `mcp` process, sent `vigil.screen_vitals`) | ✅ `state=completed`. Reply: _"I couldn't screen vitals for \`PT-001\` because the MCP tool was unreachable: MCP tool 'screen_vital_thresholds' failed: All connection attempts failed."_ — emitted from `sentinel.py:204-208` after `McpClientError` from `mcp_client.py:149-160`. |

Note: replies (a) and (b) are emitted before skill resolution, so the response message metadata does **not** include the `skill` / `patient_id` keys (the `_emit_completed` calls at sentinel.py:103 and :115 omit `metadata=`). Reply (c) is emitted after dispatch, so its metadata is populated. Cosmetic only — the chat client renders `parts[0].text` either way.

---

## Findings worth flagging to team-lead

### 🚨 HIGH — A2A → MCP call path is unauthenticated

`backend/a2a_agent/mcp_client.py:65-71`:

```python
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
if sharp_headers:
    headers.update(sharp_headers)
```

No `X-API-Key` is ever attached to the outbound MCP request. With the canonical `.env` setting `VIGIL_API_KEY=local-dev-key-anything`, the MCP server's `build_api_key_middleware` (`backend/security/api_key.py:42-50`) responds `401 Unauthorized` to every A2A→MCP call. **First-pass cycle 1 evidence (saved at `/tmp/vigil-smoke/cycle1.log`):**

```
text: I couldn't screen vitals for `PT-001` because the MCP tool was unreachable:
      MCP tool 'screen_vital_thresholds' failed: HTTP 401: {"error":"Unauthorized"}.
```

Only after I restarted MCP with `VIGIL_API_KEY` unset did the smoke succeed. In the docker-compose deploy this will fail closed: `docker-compose.yml` propagates `VIGIL_API_KEY` to **both** the `a2a` and `mcp` services (single env var across the stack), so the agent will 401 on every skill that touches MCP — i.e. four of the five.

The graceful-failure handling means the user sees a polite "I couldn't reach the clinical-tools service" rather than a 5xx, but that's the wrong outcome for the demo. Fix shape (do not apply during this smoke): inject `X-API-Key: os.environ['VIGIL_API_KEY']` into the headers dict in `VigilMcpClient.call_tool` when the env var is set, the same way the FE proxy does it via `buildServerHeaders` (`frontend/lib/api.ts`).

This is a deploy-blocking issue if the EC2 stack is brought up with `VIGIL_API_KEY` set on both services (the current `.github/workflows/deploy.yml` path).

### ⚠️ MEDIUM — response text is in `status.message.parts`, not `artifacts`

The brief expected `result.artifacts[*].parts[*]`. The current executor emits the prose in `result.status.message.parts[*]` and never populates `artifacts`. Per `_emit_status` (`sentinel.py:457-483`), the message is wrapped inside `TaskStatus(state=..., message=Message(parts=[TextPart(...)]))` and that's the only carrier.

A2A spec permits both shapes. Whether Prompt Opinion's general chat reads `artifacts` first or `status.message.parts` first is undocumented in our notes — worth checking against `prompt-opinion/po-adk-python` reference before the deploy. If the marketplace UI strictly reads `artifacts`, our chat replies will appear empty.

### ⚠️ LOW — FHIR-context extension is now `required: false`

Per `agent_card.json:21`, the extension is no longer required. The audit (`docs/A2A_REFACTOR_AUDIT.md` §"FHIR-context extension declared correctly") expected `required: true` so Prompt Opinion's "Add Connection" UI auto-prompts for FHIR. With `required: false` the user has to remember to flip the toggle, and our error-path messages assume FHIR context will be present. Confirm intentional vs. wave-1 rewrite slip.

### ℹ️ INFO — failure-mode replies (a) and (b) lack skill metadata

Replies for "no FHIR context" / "missing patient_id" return with `result.status.message.metadata == {}` because the early-return paths at `sentinel.py:103` and `:115` call `_emit_completed` without the `metadata=` kwarg. Cosmetic; the chat surface only reads `parts[0].text`.

### ℹ️ INFO — vitals dataset returns 0 observations

`Vital screen for \`PT-001\`: no MEWT breaches across \`0\` recent observations.` The HAPI seed for PT-001 isn't returning vitals (probably because the smoke posts a placebo bearer token that HAPI ignores, and the synthetic data lookup is keyed differently). Not a smoke-blocker — the dispatch + envelope handling are correct — but it means the demo's "screen finds breaches" moment can't be reproduced without a tweaked seed or a re-run after `make seed`.

---

## Pre-deploy checklist (Wave 3 readiness)

### ✅ Ready
- Wire-form agent card serves the v1 nested `securitySchemes.apiKey.apiKeySecurityScheme.location` shape end-to-end (assertion that the audit specifically called out as the "did the v1 nested form survive" gate).
- All 5 declared skills dispatch correctly via metadata-hint routing.
- All 5 skill keywords (+ default) dispatch correctly via text routing.
- All 3 graceful-failure modes return `state=completed` with friendly prose, never `failed`/5xx.
- 28 wave-1 unit tests still pass (asserted by team-lead per brief; not re-run here).
- Full request → MCP → response round-trip works against the real HAPI on `:8080`.

### 🚨 BLOCK before public deploy
- **HIGH**: Wire `X-API-Key` into `VigilMcpClient.call_tool`. Without it, the A2A pod 401s against the MCP pod whenever `VIGIL_API_KEY` is set on both — which is the canonical compose deploy.

### ⚠️ Confirm before deploy
- **MED**: Decide whether to also emit the reply in `result.artifacts[]` for stricter A2A clients. Test against `prompt-opinion/po-adk-python` reference.
- **LOW**: Confirm `extensions[0].required: false` is intentional. If not, flip back to `true` and re-test the Prompt Opinion "Add Connection → Check" flow.

### ℹ️ Nice to have
- Add `skill` / `patient_id` to the metadata on the early-return failure paths in `sentinel.py:103-108` and `:115-120` so observability stays consistent across success + failure.
- Re-seed HAPI vitals so PT-001 actually has observations to breach in the demo path (`make seed` from a fresh state).
