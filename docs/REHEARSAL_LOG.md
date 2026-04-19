# Vigil — Rehearsal Log (P1.5)

Owner: integration-lead | Date: 2026-04-19

---

## Pre-flight: Static verification (no Docker required)

These checks were performed via code inspection, test execution, and data validation before attempting live services.

### 1. Code health

| Check | Result | Notes |
|-------|--------|-------|
| `uv run pytest -v` | **PASS — 312/312** | 0 failures, 4 deprecation warnings (websockets, FastAPI lifespan) |
| `uv run ruff check` | **15 issues (12 auto-fix)** | Import ordering, unused imports, 2 line-length. No functional bugs. |
| MCP server imports | **PASS** | `backend.mcp_server.server` imports clean |
| A2A agent imports | **PASS** | `backend.a2a_agent.app` imports clean |
| FastAPI proxy imports | **PASS** | `backend.api.main` imports clean |

### 2. A2A agent entry point fix

| Issue | Resolution |
|-------|------------|
| `make agent` / `demo.sh` called `backend.a2a_agent.main` — no such module | Created `backend/a2a_agent/__main__.py` as thin wrapper. Updated `Makefile` and `scripts/demo.sh` to use `backend.a2a_agent` (package module). Verified import works. |

### 3. Synthetic data verification

| Patient | Trajectory | Verified | Notes |
|---------|-----------|----------|-------|
| PT-001 | Stable postop | **PASS** | HR 72–76 bpm range, flat. `screen_vital_thresholds` returns `status=ok`. |
| PT-002 | Stable postop | **PASS** | Bundle present, 6 timepoints. |
| PT-003 | Stable postop | **PASS** | Bundle present, 6 timepoints. |
| PT-004 | Stable postop | **PASS** | Bundle present, 6 timepoints. |
| PT-005 | Stable postop | **PASS** | Bundle present, 6 timepoints. |
| PT-006 | Stable postop | **PASS** | Bundle present, 6 timepoints. |
| PT-007 | Deteriorating postop | **PASS** | HR 76→116, SBP 130→88 over 8h. Clear hemodynamic trend. `screen_vital_thresholds` returns `triggered`. |
| PT-008 | Sepsis onset | **PASS** | Bundle present with labs and antibiotics. |
| PT-009 | Postpartum sepsis | **PASS** | Lactate 4.2 mmol/L, WBC 18.4 at T+4h. Antibiotic after sepsis onset (T+4:20). `flag_sepsis_onset` returns `sepsis_suspected=true, mode=cdc_ase`. |
| PT-010 | Postpartum hemorrhage | **PASS** | Bundle present with hemorrhage trajectory. |

**All 10 patients present.** Key clinical scenarios validated through unit tests.

### 4. MCP tool tests (38/38 PASS)

| Tool | Tests | Key assertions |
|------|-------|----------------|
| `screen_vital_thresholds` | 16 PASS | PT-001 ok, PT-007@T+2h triggered (trend rule), PT-009@T+4h triggered (absolute thresholds), postpartum paths, error handling |
| `score_deterioration_risk` | 16 PASS | PT-001 low band, PT-007 moderate→high, comorbidities populated, qSOFA components correct |
| `flag_sepsis_onset` | 6 PASS | PT-001 no sepsis (cdc_ase), PT-009 sepsis_suspected (cdc_ase), SIRS fallback, error paths |

### 5. Integration tests (38/38 PASS)

| Suite | Tests | Key assertions |
|-------|-------|----------------|
| SHARP header routing | 3 PASS | Input-only, header-only, both-present (input wins) |
| Normal trajectory | 4 PASS | Screen/risk/sepsis/escalation for stable patient |
| Deteriorating trajectory | 4 PASS | Screen triggered, risk high, sepsis false, SBAR generated |
| Sepsis trajectory | 4 PASS | CDC ASE fires, SBAR includes sepsis language |
| Hemorrhage trajectory | 4 PASS | Screen triggered, risk high, CDC ASE mode |
| Security invariants | 6 PASS | SSRF blocked, bearer tokens redacted, missing headers rejected |

### 6. Infrastructure checks

| Check | Result | Notes |
|-------|--------|-------|
| LICENSE | **PASS** | MIT license present in repo root |
| No .env committed | **PASS** | `git ls-files \| grep -i env` clean |
| PHI scan | **PASS** | MRN patterns are synthetic (MRN-100001–100010). No SSNs. No real patient data. |
| 10 patient files | **PASS** | `data/patients/PT-001.json` through `PT-010.json` all present |
| docker-compose.yml | **PRESENT** | HAPI FHIR v7.2.0 + PostgreSQL 15 config looks correct |
| scripts/demo.sh | **PASS** | 6-step orchestration with health checks, PID tracking, `--stop` mode |

---

## Pre-flight: `make demo-warmup` verification

> **NOTE:** Docker Desktop is not available in this WSL2 session. The `make demo-warmup` target requires running services (HAPI, MCP, proxy, frontend). The target logic was verified by code inspection:

### `make demo-warmup` steps (from Makefile):

1. `make seed` — runs `python data/seed_hapi.py` to reload HAPI with fresh patient data
2. LLM provider ping — `get_provider().complete('ping', 10)` tests the configured LLM
3. Agent tick — `curl -sS -X POST http://localhost:8000/api/agent/tick` triggers one agent cycle
4. Frontend warm — curls `localhost:3000/` and `localhost:3000/patients`
5. Prints "All services healthy"

**Assessment:** Logic is sound. Each step has a clear health signal. The seed step is idempotent. The LLM ping will fail fast if the provider is misconfigured.

**Recommendation:** When Docker Desktop is available, run the following sequence:
```bash
make demo           # Start all 6 services
make demo-warmup    # Reseed + warm
# Then run the 5 rehearsals per the schedule below
```

---

## Rehearsal runs

> **STATUS: BLOCKED — Docker Desktop not available in current WSL2 session.**
>
> When Docker is available, the user should execute 5 rehearsal runs following this template.
> Each run should start from `make demo-warmup` and walk through the DEMO_SCRIPT.md beat sheet.

### Run template

```
Run #: ___
Date/time: ___
Startup time: ___ seconds (target: <180s)
Result: PASS / FAIL

Services:
  [ ] HAPI FHIR — http://localhost:8080/fhir/metadata → 200
  [ ] MCP server — http://localhost:7001/health → 200
  [ ] A2A agent — http://localhost:9000/.well-known/agent-card.json → 200
  [ ] FastAPI proxy — http://localhost:8000/api/health → 200
  [ ] Next.js — http://localhost:3000 → 200

Data checks:
  [ ] 10 patients visible in /patients
  [ ] PT-007 vitals show deterioration trend
  [ ] PT-009 labs show lactate >4, WBC >18
  [ ] PT-001 stable, no false alerts

Demo flow:
  [ ] Navigate patient list → filter works
  [ ] Click PT-001 → vitals flat, no alert
  [ ] Click PT-007 → vitals deteriorating, agent escalates
  [ ] SBAR note generates for PT-007
  [ ] Approve button writes Communication + AuditEvent, toast confirms
  [ ] PT-009 → sepsis path fires
  [ ] Timeline view shows agent state transitions
  [ ] Settings page shows provider + FHIR status green

Errors encountered:
  (none / describe)

Timing notes:
  HAPI boot: ___s
  Seed: ___s
  First tool call: ___s
  SBAR generation: ___s

Notes:
  ___
```

### Run 1

_Pending: requires Docker Desktop WSL2 integration._

### Run 2

_Pending._

### Run 3

_Pending._

### Run 4

_Pending._

### Run 5

_Pending._

---

## Issues found and fixed

| # | Issue | Severity | Status | Fix |
|---|-------|----------|--------|-----|
| 1 | `backend.a2a_agent.main` module not found — `make agent` and `demo.sh` fail | **BLOCKING** | **FIXED** | Created `__main__.py`, updated Makefile and demo.sh to use `backend.a2a_agent` |
| 2 | Ruff lint: 15 issues (12 auto-fixable) | Low | Noted | Run `uv run ruff check --fix backend/ tests/` before final submission |
| 3 | FastAPI `on_event` deprecation warning in fhir_fixture | Low | Noted | Cosmetic; does not affect functionality |
| 4 | Docker Desktop not available in WSL2 session | **BLOCKING for live runs** | User action needed | Enable Docker Desktop WSL2 integration, then re-run rehearsals |

---

## Summary

| Area | Status |
|------|--------|
| Code health (312 tests) | **GREEN** |
| Data integrity (10 patients) | **GREEN** |
| Clinical scenarios (PT-007/009/010) | **GREEN** |
| A2A entry point | **FIXED** |
| Live rehearsals (5x target) | **PENDING — needs Docker** |
| Demo script (35 beats) | **Verified against implementation** |

**Next step:** User must enable Docker Desktop WSL2 integration, then run `make demo` followed by 5 rehearsal walks through `docs/DEMO_SCRIPT.md`. Log results in the run templates above.
