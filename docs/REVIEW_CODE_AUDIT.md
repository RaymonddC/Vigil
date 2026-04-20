# Vigil — Code Audit

**Scope:** Security, quality, test coverage, architecture, frontend.
**Reviewed:** backend (MCP server, A2A agent, API proxy, FHIR client, LLM provider, obs), frontend (lib, components, app routes, catch-all proxy), tests (integration + E2E), infra (docker-compose, .gitignore).
**Bottom line:** No **Critical** (demo-blocker) findings. Three **High** findings should be fixed before the submission cut; the rest can wait. The architecture is clean — single FhirContext, single FHIR-write path, 7-state sentinel, SHARP routing, SSRF allowlist, Zod/pydantic parity. 312 tests collect, 4 views covered E2E.

---

## Critical (demo blockers)

None. The stack is shippable for the hackathon submission as-is.

---

## High (fix before submission)

### H1 — X-API-Key enforcement is absent on MCP server and A2A agent

**Where:** `backend/mcp_server/server.py:285-293`, `backend/a2a_agent/app.py` (no middleware registration); `backend/a2a_agent/agent_card.json` declares `securitySchemes.apiKey` but the agent does not actually check the header.

**Severity:** High. The FastAPI proxy (`backend/api/main.py:102`) is the only service that enforces `X-API-Key` (via `secrets.compare_digest`). The MCP server binds to `0.0.0.0` by default and the A2A agent binds to `0.0.0.0` in `backend/a2a_agent/__main__.py:10`. The AgentCard falsely advertises key-gated access. If either port is ever tunnelled, both are open.

**Recommendation:** Add the same `api_key_middleware` used in `backend/api/main.py` to both `mcp_server/server.py` and `a2a_agent/app.py`. Reuse `VIGIL_API_KEY` env var. Skip prefixes should include `/.well-known/agent-card.json` (public per A2A spec) and MCP's health path only. Alternatively, document clearly that MCP/A2A are 127.0.0.1-only and tighten their bind addresses to match HAPI's loopback binding.

### H2 — Approve flow has a TOCTOU race that allows double FHIR writes

**Where:** `backend/api/review_queue.py:132-143` (`update_alert_status` UPDATE lacks a `WHERE status = 'in-progress'` guard); pre-flight check lives at `backend/api/main.py:200-206`.

**Severity:** High. The approve path reads status, then writes Communication to HAPI, then updates SQLite. Two concurrent approves can both pass the `status == 'completed'` pre-flight check, both POST a Communication, and both try to flip the row. Idempotency protects the UI but not HAPI — two Communications land on the server.

**Recommendation:** Make the SQLite UPDATE conditional: `UPDATE review_queue SET status='completed', ... WHERE id = ? AND status = 'in-progress'`. If `rowcount == 0`, raise 409. Move the guard **before** the HAPI POST so the DB is the serialization point, not the cache. Add an integration test that fires two approves in parallel and asserts one 200 + one 409.

### H3 — Logging filter bypasses allow bearer tokens to leak into logs

**Where:** `backend/mcp_server/server.py:38-67` — `_setup_logging()` installs a custom JSONFormatter but never attaches `_BearerTokenFilter` from `backend/obs/logging.py`. `backend/a2a_agent/app.py` does not call `configure_logging()` at all and relies on uvicorn defaults.

**Severity:** High. The MCP server is the component that actually receives `x-fhir-access-token` in the SHARP middleware. If a stack trace or a debug log ever renders a request header dump, the bearer token escapes the redactor.

**Recommendation:** Replace the MCP custom logging setup with `configure_logging()` from `backend/obs/logging.py`, which already wires `_BearerTokenFilter` and `set_request_id`. Call the same from `backend/a2a_agent/app.py` on startup. Add a unit test that asserts a log record containing `Bearer abc123...` comes out redacted.

---

## Medium (fix post-hackathon)

### M1 — `moderate → {high, medium}` risk mapping is inconsistent across two components

**Where:** `frontend/components/patients-table.tsx:29` maps `"moderate" → "high"`; `frontend/app/patients/[id]/page.tsx:104` maps `"moderate" → "medium"`. Backend emits `moderate` from `backend/risk/score.py`.

**Severity:** Medium. A patient who is `moderate` shows as **High** in the roster list but **Medium** on their own detail page. Judges clicking through will see the mismatch.

**Recommendation:** Extract a single `normalizeRiskBand()` helper in `frontend/lib/risk.ts` and import it from both components. Decide canonically whether `moderate → medium` (matches clinical vocabulary) or `moderate → high` (matches alert triage). Lean toward `medium` — it matches MEWS scoring language.

### M2 — SEC-14 substring match in FHIR hook key lookup

**Where:** `backend/a2a_agent/fhir_hook.py:45` — `if FHIR_CONTEXT_KEY in str(key)` uses substring containment on stringified ContextVar tokens.

**Severity:** Medium. A ContextVar whose repr happens to contain the sentinel would match. The existing tests pass because no colliding key exists, but this is fragile and was flagged SEC-14 in the earlier security review without a structural fix.

**Recommendation:** Iterate `contextvars.copy_context()` directly and compare the `ContextVar` object identity (`is`) rather than string-matching its repr.

### M3 — Prompt injection surface via unsanitized `Patient.name`

**Where:** `backend/mcp_server/tools/generate_escalation_note.py:54-114` (`_build_prompt`). `patient_name`, which originates from FHIR `Patient.name`, is embedded directly into the LLM prompt.

**Severity:** Medium. Synthetic Synthea data is safe, but any real FHIR server could return adversarial names ("\n\nSystem: ignore prior instructions"). The generated SBAR ends up in HAPI as a Communication — downstream consumers would render the payload.

**Recommendation:** Strip ASCII control chars and newlines from `patient_name` before interpolation. Prefer a structured prompt (JSON input block) over a free-form string template. Add a fuzz test with adversarial patient names.

### M4 — AuditEvent soft-fail leaves the audit trail with gaps

**Where:** `backend/api/routes/patients.py:317-326` — when the AuditEvent POST fails, the code logs and returns `audit-<uuid>-failed` as `audit_id`, but the Communication was already written.

**Severity:** Medium. The compliance story for the submission is "every approve writes Communication + AuditEvent atomically." In practice a transient HAPI failure breaks the invariant silently.

**Recommendation:** Either (a) write AuditEvent first, Communication second, or (b) wrap both in a FHIR transaction bundle (`POST /` with `type: "transaction"`) so HAPI enforces atomicity. Option (b) matches the architectural claim.

### M5 — No rate limiting on any service (SEC-11)

**Where:** No middleware in `backend/api/main.py`, `backend/mcp_server/server.py`, or `backend/a2a_agent/app.py`.

**Severity:** Medium. With `VIGIL_API_KEY` unset in dev mode (`backend/api/main.py:129`), a mistaken tunnel exposes the approve endpoint to unthrottled replay. The review queue and FHIR server would absorb whatever load the caller dishes out.

**Recommendation:** Add `slowapi` or `fastapi-limiter` with a conservative default (60 req/min per key) on all three FastAPI/Starlette apps. Low complexity, meaningful defense-in-depth.

---

## Low (nice-to-have)

### L1 — `dict[str, Any]` return types dilute the FastAPI contract (SEC-20 still open)

**Where:** `backend/api/main.py:155, 165, 178, 221, 232, 255, 290`. Most routes return `dict[str, Any]` instead of pydantic response models.

**Severity:** Low. The Zod schemas on the frontend already enforce the shape, so runtime safety is fine, but OpenAPI loses documentation value and the pydantic-Zod parity claim weakens.

**Recommendation:** Migrate routes one at a time to explicit `response_model=` arguments. Not urgent.

### L2 — `ackAlert` hard-codes `clinician_id = "prac-nurse-17"` (SEC-08 hackathon note)

**Where:** `frontend/lib/api.ts:227-230`.

**Severity:** Low. Documented as a hackathon shortcut. Any real deployment must wire this to an auth session.

**Recommendation:** Flag in the demo script that a real deployment would derive `clinician_id` from the authenticated session, not a constant.

### L3 — FHIR fixture has no auth

**Where:** `backend/fhir_fixture/main.py`.

**Severity:** Low. It is dev-only and `127.0.0.1`-bound by convention. Path traversal is not possible because the fixture looks up bundles from an in-memory dict.

**Recommendation:** Document the binding assumption at the top of the file and add a README warning so nobody tunnels the fixture port.

### L4 — SQLite review queue is unencrypted

**Where:** `backend/api/review_queue.py`.

**Severity:** Low. Synthetic data only — no PHI. Called out in `SECURITY_REVIEW.md`.

**Recommendation:** No action for the hackathon. If ever reused for real patients, move to Postgres with encryption-at-rest.

---

## Positive observations

1. **SEC-01 SSRF allowlist** (`backend/mcp_server/context.py:37-65`) is enforced at SHARP header dispatch and rejects any host not in `ALLOWED_FHIR_HOSTS`. Default-deny posture is correct.
2. **SEC-03 bearer token redaction** (`backend/obs/logging.py:_BearerTokenFilter`) is implemented correctly where wired (the gap is H3, not the filter itself).
3. **SEC-06 CORS** (`backend/api/main.py:72-78`) uses the env-restricted origin list rather than wildcard.
4. **SEC-07 parameterized SQL** — every query in `backend/api/review_queue.py` uses `?` placeholders. No string concatenation on the SQL surface.
5. **SEC-10 HAPI loopback** (`docker-compose.yml`) binds `127.0.0.1:8080:8080` — not reachable externally.
6. **No hardcoded secrets.** `.env` absent from git history; API keys sourced from env (`GROQ_API_KEY`, `ANTHROPIC_API_KEY`, `VIGIL_API_KEY`).
7. **Single FHIR-write path.** `backend/fhir/client.py:167` (`post_resource`) is called only from `backend/api/routes/patients.py:approve_alert_action`. The A2A agent never writes — confirmed by grep. Architectural invariant holds.
8. **Sentinel 7-state machine** in `backend/a2a_agent/sentinel.py` is correctly implemented and transitions are logged as VigilEvents.
9. **Zod/pydantic parity.** `frontend/lib/api.ts` mirrors every backend response model. Parse errors at the client boundary are loud, not silent.
10. **Test coverage is real.** 312 tests collect. `tests/integration/test_mcp_tools.py` (807 lines) covers the full SHARP routing matrix (4 tools × 3 scenarios), all 4 patient trajectories (PT-001/PT-007/PT-009/PT-010), and SEC-01/SEC-03 invariants via `SENTINEL_BEARER_TOKEN_99887766`. `tests/e2e/smoke.spec.ts` click-through-tests all 4 views and navigation.

---

## Test coverage gaps worth closing

- **No test for H2 race.** Fire two parallel approves and assert serialization.
- **No test for prompt-injection resilience** (M3). Adversarial `Patient.name` fuzzer.
- **No test that MCP/A2A reject missing X-API-Key** after H1 is fixed.
- **No test that a failing AuditEvent POST rolls back the Communication** (M4).

---

## Suggested fix order

1. H2 (approve race) — small DB change, high payoff, demo-safe.
2. H3 (logging filter) — one import change in two files.
3. H1 (API key middleware on MCP + A2A) — copy-paste the proxy's middleware.
4. M1 (risk band mapping) — visible to judges.
5. M4 (AuditEvent atomicity) — supports the compliance narrative.
6. Everything else can wait until after 2026-05-11.
