# Functional Test Log

**Date:** 2026-04-20  
**Branch:** main  
**Tester:** functional-tester agent (vigil-review)

---

## Environment Status

| Tool | Version | Status |
|------|---------|--------|
| docker | 29.2.1 | ✅ available |
| uv | 0.11.7 | ✅ available |
| pnpm | 10.33.0 | ✅ available |

---

## Test Results

### 1. Unit + Integration Tests

```
pytest -v --tb=short
```

**Result: ✅ 312 / 312 PASSED** (22.98s)

4 deprecation warnings (non-blocking):
- `on_event` deprecated in FastAPI — affects `fhir_fixture/main.py`
- `websockets.legacy` deprecated — internal to uvicorn

---

### 2. Frontend Build

```
cd frontend && pnpm install && pnpm tsc --noEmit && pnpm build
```

**Result: ✅ PASSED**

- TypeScript: clean, no errors
- Production build: Next.js 16.2.4 (Turbopack), compiled in 45s
- All 8 routes generated successfully:

| Route | Type |
|-------|------|
| `/` | Static |
| `/_not-found` | Static |
| `/alerts` | Static |
| `/api/[...path]` | Dynamic |
| `/patients` | Static (revalidate 10s) |
| `/patients/[id]` | Dynamic |
| `/settings` | Static (revalidate 30s) |
| `/timeline` | Static |

---

### 3. Lint

```
make lint  →  uv run ruff check backend/ tests/
```

**Result: ✅ All checks passed** — zero warnings, zero errors.

---

### 4. Fixture-Mode Backend Smoke Test

**Fixture FHIR server:**

```
curl http://localhost:8080/fhir/Patient
→ total=10, entries=10  ✅
```

**MCP tool invocations (4 tools × fixture backend):**

| Tool | Patient | Expected | Actual | Pass |
|------|---------|----------|--------|------|
| `screen_vital_thresholds` | PT-001 (stable) | status=ok, 0 breaches | ok, 0 breaches | ✅ |
| `screen_vital_thresholds` | PT-009 (sepsis) | status=triggered | triggered, 6 breaches | ✅ |
| `score_deterioration_risk` | PT-001 (stable) | status=ok | ok | ✅ |
| `score_deterioration_risk` | PT-007 (deteriorating) | status=triggered | triggered | ✅ |
| `flag_sepsis_onset` | PT-009 (sepsis) | status=triggered | triggered | ✅ |
| `flag_sepsis_onset` | PT-001 (stable) | status=ok | ok | ✅ |
| `generate_escalation_note` | PT-007 | LLM call | `llm_error` + fallback SBAR | ⚠️ |

**Note on `generate_escalation_note`:** With no Ollama/Groq running, the tool returns `status: llm_error` but still produces a fallback SBAR structure (graceful degradation). This is expected behavior in CI. Tool signature is a composition pattern: it requires `vitals_result`, `risk_result`, and `sepsis_result` as inputs (outputs from the other three tools).

SHARP header routing confirmed: all tools correctly parse `x-fhir-server-url`, `x-fhir-access-token`, and `x-patient-id` from mock request context.

---

### 5. Full HAPI Smoke Test (Docker)

**Stack startup:**
```
make up  →  HAPI FHIR ready at http://localhost:8080/fhir  ✅
```

**Seed:**
```
uv run python data/seed_hapi.py ...
→ All 10 patients seeded successfully  ✅
```

**Note:** `make seed` fails with `python: No such file or directory` — the Makefile uses bare `python` instead of `uv run python`. Workaround: call directly. Minor fix needed.

**Proxy API:**
```
curl http://localhost:8000/api/patients
→ 10 patients with correct schema (id, mrn, name, age, trajectory, ...)  ✅
```

**A2A agent card:**
```
curl http://localhost:9000/.well-known/agent-card.json
→ AgentCard with name, skills, capabilities  ✅
```

**System status (`/api/status`):**
```json
{
  "fhir_healthy": true,
  "agent_healthy": true,
  "llm_provider": "ollama"
}
```
FHIR + A2A reachable. Ollama not running (expected in this env).

---

## Bug: `/api/agent/tick` Always Fails

**Severity: Medium** — Demo "Tick Now" button non-functional.

**Root cause:** `backend/api/main.py` POSTs to `{A2A_AGENT_URL}/tick` (line 262), but the A2A agent is built with `A2AFastAPIApplication` which only exposes:
- `GET /.well-known/agent-card.json`
- `POST /a2a`

There is no `/tick` route on the A2A agent. Every call to `POST /api/agent/tick` returns `{"triggered": false, "detail": "{\"detail\":\"Not Found\"}"}`.

**Observed:**
```
POST http://localhost:9000/tick  →  404 Not Found
/api/agent/tick  →  {"triggered": false, "detail": "{...Not Found...}"}
```

**Fix:** Add a `/tick` route to the A2A agent app that triggers one sentinel run cycle, or change the proxy to directly invoke the sentinel via Python rather than an HTTP round-trip.

---

## Minor Findings

| # | Finding | Severity |
|---|---------|----------|
| 1 | `make seed` uses bare `python` instead of `uv run python` | Low |
| 2 | `fhir_fixture/main.py` uses deprecated `@app.on_event("startup")` | Low |
| 3 | `generate_escalation_note` requires 3 upstream outputs as inputs — callers must chain tools manually | Info |

---

## Summary

| Check | Result |
|-------|--------|
| pytest 312 tests | ✅ All pass |
| TypeScript check | ✅ Clean |
| Frontend production build | ✅ Clean |
| Ruff lint | ✅ Clean |
| Fixture FHIR server | ✅ 10 patients |
| MCP tools (6/7 scenarios) | ✅ Correct outcomes |
| MCP tool escalation note | ⚠️ LLM graceful degradation |
| Docker HAPI stack | ✅ Up and seeded |
| Proxy `/api/patients` | ✅ 10 patients |
| A2A agent card | ✅ Serving |
| `/api/agent/tick` | ❌ 404 — A2A has no /tick route |

**Overall verdict: system is functional for core patient monitoring flows. One broken endpoint (`/api/agent/tick`) blocks the demo "Tick Now" button and should be fixed before submission.**
