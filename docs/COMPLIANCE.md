# COMPLIANCE.md

Vigil's compliance posture for hospital procurement, FDA SaMD review, and
SOC 2 / HIPAA / HITRUST evaluation. This document is **forward-looking** —
Vigil is a hackathon submission deployed against synthetic data with no
PHI, but the architecture is designed so the production hardening path is
incremental, not a rewrite.

Cross-referenced from `docs/CLINICAL_EVIDENCE.md` (clinical claims),
`backend/api/routes/patients.py` (Provenance + Device writes), and
`tests/validation/` (sensitivity/specificity reporting harness).

---

## 1. FDA SaMD classification (intended use)

Per FDA *Software as a Medical Device (SaMD): Clinical Evaluation* guidance
(2017) and IMDRF SaMD risk framework, Vigil's intended use places it as:

| Dimension | Vigil's classification |
|---|---|
| State of healthcare situation | **Serious** (postoperative deterioration, sepsis, postpartum hemorrhage) |
| Significance of information to clinical decision | **Inform clinical management** (Vigil never decides; clinician approves) |
| **SaMD category** | **Class II** (Inform clinical management for serious situation) |
| **510(k) pathway** | Predicate devices: TREWS (K-cleared early-warning systems), COMPOSER-LLM (Nature/npj DM 2025 prospective implementation) |

**Why Class II, not III**: Vigil's verdict is *advisory* — every escalation
requires clinician approval before any FHIR `Communication` write. The
HITL boundary is enforced architecturally:

- A2A agent can never write to FHIR (verified in `backend/a2a_agent/sentinel.py` —
  no FhirClient `post_resource` or `put_resource` call sites in the agent).
- Only `backend/api/routes/patients.py::approve_alert` writes, and only
  after a clinician's POST to `/api/patients/{id}/alerts/{alertId}/approve`.

This pattern is FDA-aligned: a Class III "AI-driven autonomous escalation"
classification is reserved for systems that take action without human review.

## 2. HIPAA mapping

Vigil at the deployed-image level maps to the HIPAA Security Rule as
follows. Items marked **(P)** are production-required gaps tracked for
post-hackathon hardening.

### Administrative safeguards (§164.308)

| Standard | Vigil status | Evidence |
|---|---|---|
| Security management process (a)(1) | Architectural — synthetic-only, no PHI | `data/seed_hapi.py` is the only data source |
| Workforce security (a)(3) | **(P)** — single-developer hackathon | post-hackathon: documented role-based access |
| Information access management (a)(4) | API-key gate on all agent + proxy endpoints | `backend/security/api_key.py` |
| Security awareness (a)(5) | n/a — no production users | — |
| Security incident procedures (a)(6) | **(P)** — minimal, log-based | post-hackathon: SIEM integration + IR runbook |
| Contingency plan (a)(7) | Containerized stateless services + persistent volume for review queue | `docker-compose.yml` |
| Audit controls (b) | Per-write `AuditEvent` resource (FHIR R4) + structured logs | `backend/api/routes/patients.py` lines 460+ |

### Technical safeguards (§164.312)

| Standard | Vigil status | Evidence |
|---|---|---|
| **Access control (a)** | API key + SHARP-context-scoped FHIR | `backend/security/api_key.py`, `backend/a2a_agent/fhir_hook.py` |
| **Audit controls (b)** | Three-resource attestation chain per write: Communication + Provenance + AuditEvent | Phase 3 commit `f1038e6` |
| **Integrity (c)** | Content-addressable AgentCard hash stamped into Provenance.signature | `backend/api/routes/patients.py::_VIGIL_AGENT_CARD_HASH` |
| **Person or entity authentication (d)** | API key (interim); SMART-on-FHIR client-credentials flow on the FHIR side via SHARP token | post-hackathon: agent-side SMART-on-FHIR via dynamic client registration |
| **Transmission security (e)** | HTTPS via Caddy + Let's Encrypt auto-TLS | `deploy/aws/Caddyfile` |

### Physical safeguards (§164.310)

| Standard | Vigil status |
|---|---|
| Facility access | AWS EC2 instance, IAM-controlled |
| Workstation use / security | n/a — no end-user workstations |
| Device + media controls | Container ephemeral; review-queue SQLite on named docker volume |

### Production gaps to PHI-readiness

- **(P) Encryption at rest**: SQLite review queue is plain-file. SQLCipher migration is one config change away (`PRAGMA key`); not enabled until first PHI deployment.
- **(P) BAA chain**: Hackathon has no BAA. Production deployment requires signed BAAs with: cloud provider, LLM provider (Anthropic / Google / OpenAI), FHIR-server hosting partner.
- **(P) De-identification controls**: Vigil's MCP tools deliberately avoid PII fields (no name, no DOB beyond age computation). Synthetic data eliminates the question for the hackathon submission.

## 3. SOC 2 readiness mapping (Trust Services Criteria)

| TSC | Vigil status | Evidence |
|---|---|---|
| **Security (CC)** | API key, TLS, immutable container builds, PR-based change control | GitHub branch protection + auto-deploy from `main` |
| **Availability (A)** | Containerized stateless services, restart-policy unless-stopped, health-checks on all services | `docker-compose.yml` |
| **Processing integrity (PI)** | Deterministic-first architecture, 654 passing tests, ruff-clean | `tests/`, CI gate via `make test` |
| **Confidentiality (C)** | Synthetic-only at hackathon; LLM provider chosen at deploy time (no vendor lock-in) | `LLM_PROVIDER` env (Ollama / Groq / Claude / Gemini) |
| **Privacy (P)** | n/a in hackathon (no PHI); mapped above for production |

**SOC 2 Type 1 timeline post-hackathon**: 3-6 months with a third-party
auditor, contingent on a real customer pilot.

## 4. HITRUST CSF v11 alignment (selected controls)

Vigil's architecture pre-implements the HITRUST controls most commonly
flagged in healthcare AI assessments:

| Control family | Vigil approach |
|---|---|
| **04 Security Policy** | Single-source architectural invariants in `CLAUDE.md`; no implicit conventions |
| **06 Compliance** | This document; cross-references to clinical evidence + validation |
| **08 Network Protection** | Caddy reverse proxy is the only public entrypoint; HAPI bound to 127.0.0.1 |
| **09 Transmission Protection** | TLS via Let's Encrypt; SHARP context never logged in cleartext (`_redact_token`) |
| **10 Password Management** | API key as interim; rotation via env var only — no DB-stored creds |
| **11 Access Control** | API key middleware + SHARP-token scoping per request |
| **12 Audit Logging** | Triple-resource FHIR write (Communication + Provenance + AuditEvent) |

## 5. TRIPOD+AI 2024 reporting compliance

Per Collins GS et al, *TRIPOD+AI statement*, BMJ 2024;385:e078378.

| TRIPOD+AI item | Vigil implementation |
|---|---|
| **3 (Title)** | AgentCard `name` + `description` declare the model's intended use |
| **6 (Source of data)** | `data/seed_hapi.py` documents synthetic-only data origin |
| **9 (Eligibility / sample)** | `data/patients/_index.json` enumerates the 10-patient cohort with trajectory labels |
| **15 (Outcome)** | `tests/validation/test_validation_harness.py` defines TP/FN/TN/FP with named clinical-trajectory ground truth |
| **16 (Interpretability)** | Phase 3 SHAP-style feature attribution in `screen_vitals` + `score_risk` chat replies |
| **19 (Uncertainty)** | Per-skill confidence tags (HIGH/MEDIUM/LOW + reason); 95% CI on `forecast_trajectory` |
| **22 (Performance)** | `tests/validation/test_validation_harness.py` reports sensitivity/specificity/lead time + the comparative harness pits Vigil against NEWS2-only and qSOFA-only |
| **26 (Intended use + version)** | Provenance writes carry `Device.version` (semver from AgentCard) + AgentCard SHA-256 hash in `signature.data` |

## 6. Open issues (post-hackathon roadmap)

1. **Real prospective validation** against MIMIC-IV or eICU-CRD (PhysioNet credentialing required).
2. **Clinician advisor on record** (currently single-developer; needs MD co-author).
3. **SMART-on-FHIR agent-side authorization** (replaces interim API key gate).
4. **SQLCipher** for the review queue at-rest encryption.
5. **Pilot deployment** with IRB approval + outcome metrics.
6. **510(k) pre-submission package** (Q-Sub) referencing TREWS / COMPOSER-LLM as predicates.
7. **Multi-region deployment** + DR runbook.

---

## Cross-references

- `docs/CLINICAL_EVIDENCE.md` — every clinical claim cited.
- `docs/PROJECT_BRIEF.md` — submission scope.
- `docs/PROMPT_OPINION_INTEGRATION.md` — SHARP context propagation.
- `tests/validation/` — quantitative + comparative validation.
- `backend/api/routes/patients.py` lines 62-145 — Provenance + Device writes.
- `backend/security/api_key.py` — interim API-key gate.
