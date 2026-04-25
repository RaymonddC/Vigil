# A2A agent refactor audit — Option 3 fitness

_Generated 2026-04-25 by `a2a-audit` teammate (Plan-mode, read-only)._
_Branch: `submission/option-3-a2a`._

## Current state

### HTTP surface today
Built by `a2a.server.apps.A2AFastAPIApplication` in `backend/a2a_agent/app.py:73-78`.

| Method | Path | Source | What it does |
|---|---|---|---|
| GET | `/.well-known/agent-card.json` | `add_routes_to_app` | Returns the AgentCard (public, exempted from API-key middleware via `_A2A_SKIP_PREFIXES` in `app.py:81`) |
| GET | `/.well-known/agent.json` | back-compat alias | Same, deprecated path |
| POST | `/` | `add_routes_to_app` (`rpc_url` default = `/`) | A2A JSON-RPC entrypoint; dispatches `message/send`, `tasks/get`, etc., into `DefaultRequestHandler` → `PostopSentinelExecutor.execute()` |
| POST | `/tick` | `app.py:100-110` (Vigil custom) | Non-A2A admin endpoint — runs `run_cycle_for_all_patients`. Used by FE3 "Tick Now". |

**Card URL bug:** `agent_card.json:5` declares `"url": "http://localhost:9000/a2a"`, but `A2AFastAPIApplication.build()` mounts the JSON-RPC route at `/`. So Prompt Opinion will read the card and POST to `/a2a` — which 404s. Either change the card URL to `http://localhost:9000/` or call `app_builder.build(rpc_url="/a2a")`. One-line fix.

### Agent card today (`backend/a2a_agent/agent_card.json`)

```json
"url": "http://localhost:9000/a2a",
"capabilities": {
  "streaming": true,
  "extensions": [{
    "uri": "ai.promptopinion/fhir-context",
    "required": true,
    "params": { "metadata_key_suffix": "fhir-context",
                "fields": ["fhirUrl","fhirToken","patientId"] }
  }]
},
"skills": [
  { "id": "vigil.monitor_patient", "name": "Monitor patient for deterioration", ... },
  { "id": "vigil.explain_alert",   "name": "Explain an existing alert",        ... }
],
"securitySchemes": { "apiKey": { "type":"apiKey","in":"header","name":"X-API-Key" } },
"security": [{ "apiKey": [] }]
```

- FHIR-context extension declared correctly (URI matches `po-adk-python` convention; `required: true` makes Prompt Opinion show the toggle).
- API-key security declared correctly; middleware enforced via `backend/security/api_key.py` and `app.py:82`.
- **Skills are aspirational, not wired.** Only `vigil.monitor_patient` is functionally backed; `vigil.explain_alert` has no handler.

### SHARP context handling

1. **A2A in** — `fhir_hook.py:34-47` `extract_fhir_from_metadata(metadata)` walks `message.metadata`, picks the first key containing `fhir-context`, coerces JSON-string values via `_coerce`, returns `(key, {fhirUrl, fhirToken, patientId})`. Substring match (matches `po-adk-python` behaviour).
2. **A2A out → MCP** — `fhir_hook.py:50-68` `fhir_metadata_to_sharp_headers(fhir_dict)` maps `{fhirUrl,fhirToken,patientId}` → `{x-fhir-server-url, x-fhir-access-token, x-patient-id}`.

Both helpers are called from `sentinel.py:72-88`. Bearer token forwarded only when present.

### MCP integration

`backend/a2a_agent/mcp_client.py` — `VigilMcpClient`, an httpx wrapper that:
- Posts JSON-RPC to `${VIGIL_MCP_URL}/mcp` (default `http://localhost:7001/mcp`).
- Sets `Accept: application/json, text/event-stream` per MCP Streamable HTTP spec.
- Forwards SHARP headers (param `sharp_headers`) unchanged.
- Parses both JSON and SSE response bodies (`mcp_client.py:113-129`).
- Raises `McpClientError` on HTTP ≥400 or JSON-RPC `error` field.

Tool names called from the executor (`sentinel.py:109-213`) — match the 4 tools registered in `backend/mcp_server/server.py` 1:1:
- `screen_vital_thresholds`
- `score_deterioration_risk`
- `flag_sepsis_onset`
- `generate_escalation_note`

### Autonomous loop

- **Where:** `app.py:120-153` (`_poll_loop` + `_start_poll_loop` startup hook).
- **Cadence:** `POLL_INTERVAL_SEC` env, default 900s. `<=0` disables.
- Runs `run_cycle_for_all_patients` for every seeded HAPI patient → enqueues to SQLite review queue on trigger.
- Uses synthetic SHARP headers built from `FHIR_BASE_URL` + `patient_id` (no bearer token — only works against unauth HAPI).

`POST /tick` is the same pipeline triggered manually.

The A2A `execute()` path (`sentinel.py:60-304`) runs the **identical** state machine for a single patient driven by a request, then *also* enqueues to the review queue (`sentinel.py:237-246`).

## Gap vs. Option 3 invocation model

### Missing for the host's request-response flow

1. **No skill dispatch.** `PostopSentinelExecutor.execute()` ignores the inbound message text and the declared skill ID. It always runs the full pipeline. The A2A `Message` shape (verified at `.venv/.../a2a/types.py`) has no native `skill_id` field — skill selection is the agent's responsibility, typically by inspecting `context.message.parts[*].text` or by Prompt Opinion injecting a hint into `message.metadata` (unverified, see Open Q1).
2. **The card lies about the route.** `url: ".../a2a"` vs. actual mount at `/`. Will break Prompt Opinion's `Add Connection → Check` step.
3. **Only 2 skills declared, only 1 implemented.** Judges asking "score sepsis" or "draft an SBAR" get the full pipeline — can't get granular answers.
4. **A2A reply always wraps an SBAR write.** `sentinel.py:237-277` enqueues *before* emitting `TaskState.completed`. For Option 3, the reply should just be the answer; queue-write should be opt-in.
5. **No skill-level error envelope.** Failures → `TaskState.failed` with raw `str(e)`. For chat output, replies need to be readable one-line summaries.

### Present but doesn't fit (keep but disable / rename)

- **Autonomous polling loop.** Set `POLL_INTERVAL_SEC=0` for the Option-3 deploy. Optionally re-expose as `vigil.start_watching` skill.
- **`POST /tick` admin endpoint.** Keep as-is for our dashboard's "Tick Now" button.
- **Review-queue enqueue inside `execute()`.** Move into `vigil.draft_sbar` only.

## Proposed skill surface

| Skill ID | Maps to MCP tool(s) | Inputs | Output |
|---|---|---|---|
| `vigil.screen_vitals` | `screen_vital_thresholds` | `patient_id` (from SHARP), optional `lookback_minutes` | MEWT result, breach list, narrative |
| `vigil.score_risk` | `score_deterioration_risk` | `patient_id` | Risk band + qSOFA score + rationale |
| `vigil.check_sepsis` | `flag_sepsis_onset` | `patient_id` | `sepsis_suspected: bool` + ASE evidence |
| `vigil.draft_sbar` | all 3 screens + `generate_escalation_note` | `patient_id`, optional `recipient_role` | Full SBAR + severity, optional alert_id |
| `vigil.start_watching` *(optional)* | toggles autonomous loop | `patient_id`, `interval_sec` | Acknowledgement |
| `vigil.explain_alert` *(stretch)* | reads SQLite review queue | `alert_id` | Evidence trail |

Each handler is ~30 LOC: read SHARP + patient_id, call 1–4 MCP tools, format reply.

## Refactor size — Surgical add (2–3 days)

| File | Change | Approx LOC |
|---|---|---|
| `backend/a2a_agent/agent_card.json` | Replace 2 skills with 4–6; fix `url` (or update `app.py` build call) | ~40 |
| `backend/a2a_agent/sentinel.py` | Refactor `execute()` to dispatch by skill; move existing logic into `_handle_draft_sbar()`; add 3 new handlers | ~150 net (–60 / +210) |
| `backend/a2a_agent/skill_router.py` *(new)* | `resolve_skill(message: Message) -> SkillId` — metadata first, keyword fallback | ~60 |
| `backend/a2a_agent/app.py` | One-line: `app_builder.build(rpc_url="/a2a")`. Optionally `POLL_INTERVAL_SEC=0` for prod profile | ~3 |
| `tests/test_a2a_skill_dispatch.py` *(new)* | Per-skill unit tests; mirror `test_sharp_compliance.py` style | ~120 |
| `docs/API_CONTRACTS.md` §3 | Update declared skills list | ~25 |

Net: ~400 lines across 6 files. Largely additive; no churn to MCP, FHIR client, criteria, or review-queue code.

### Risks

1. **Skill dispatch heuristic** — Prompt Opinion's "which skill is the user asking for" contract is undocumented in our notes. Build a fallback (text keywords) + sniff for metadata hint. Open Q1.
2. **Queue-write semantics shift** — moving enqueue into only `draft_sbar` is a behaviour change. `test_sentinel.py` will need updates.
3. **Autonomous loop + A2A** writing concurrently to SQLite — already covered by `claim_alert_for_writing` race semantics.
4. **Card URL fix** — anyone who has cached the agent card needs to refetch.

## Open questions for team-lead

1. **How does Prompt Opinion's general chat tell our agent which skill to invoke?** Build (a) keyword/LLM heuristic AND (b) metadata sniff; let runtime evidence decide.
2. **Keep the autonomous loop?** Default `POLL_INTERVAL_SEC=0`; expose `vigil.start_watching` as opt-in.
3. **Should `draft_sbar` enqueue to the review queue?** For Option 3, *no* — Prompt Opinion's general chat is the human-in-the-loop. Skip the enqueue, return the SBAR.
4. **Card URL: change card to `/` or change build to `/a2a`?** Update the build call so the card stays semantically clean.
5. **`vigil.explain_alert`** — punt or implement? Defer to post-MVP.
6. **Skill IDs naming** — `vigil.screen_vitals` (dot-separated, vendor prefix). Decide before writing the card.
