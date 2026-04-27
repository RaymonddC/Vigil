# Devpost Submission — Vigil

> Draft for the user to copy into the Devpost form. Each section maps to a Devpost field. Voice rules: clinical-direct, no exclamation marks, no emoji in body, no marketing-speak. Every claim sourced to a file path, a public standard, or an empirical finding (`docs/A2A_LOCAL_SMOKE.md`, `docs/CLINICAL_EVIDENCE.md`).

---

## Title (max 70 characters)

```
Vigil — clinical sentinel for postop and postpartum deterioration
```

(64 characters)

---

## Tagline (max 200 characters)

```
A second pair of eyes on every post-op and postpartum bed. Deterministic rules decide; an LLM drafts the SBAR; the clinician approves. Five A2A skills, FHIR R4, no autonomous writes.
```

(182 characters)

---

## Inspiration

Every year, 4.2 million people die within 30 days of surgery — more than HIV, tuberculosis, and malaria combined ([Nepogodiev, *Lancet* 2019](https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(18)33139-8/fulltext)). One woman dies every two minutes from pregnancy or childbirth ([WHO 2023](https://www.who.int/news/item/23-02-2023-a-woman-dies-every-two-minutes-due-to-pregnancy-or-childbirth--un-agencies)). In both wards the warning signs appear 30–60 minutes before crisis, but no single vital crosses a hard threshold — the danger lives in the trend pattern across HR, BP, lactate, and the nursing context. One nurse covers 6–8 post-surgical patients at a ward station. No human holds that multivariate pattern in their head for everyone in their bay. Vigil exists for the gap between "looks fine" and "the rapid response team is here."

## What it does

Vigil is a clinician-supervised early-warning agent for postoperative and postpartum wards. It reads vitals, labs, and active conditions from a FHIR R4 server, screens them against published standards (MEWT, qSOFA, CDC Adult Sepsis Event, KDIGO), and drafts an SBAR escalation note when the trend pattern indicates deterioration. Catching that pattern 30–60 minutes earlier is what shrinks the window from "code blue" to "controlled escalation." Five A2A skills — `vigil.screen_vitals`, `vigil.score_risk`, `vigil.check_sepsis`, `vigil.draft_sbar`, `vigil.start_watching` — are exposed to Prompt Opinion's general chat so any clinician on the platform can consult Vigil per patient. The same five skills cover a post-CABG patient on day 2 and a postpartum patient with chorioamnionitis on day 3 with no code branching.

Deterministic rule engines in `backend/criteria/` (`mewt.py`, `qsofa.py`, `sirs.py`, `kdigo.py`) decide *whether* to escalate. The LLM is locked out of that decision — it only writes the SBAR prose around the structured verdict. The agent never writes to FHIR. Every alert lands in a SQLite review queue, and only the clinician approve flow writes the `Communication` and `AuditEvent` resources, with the Vigil `Device` and any `PractitionerRole` references PUT idempotently first to keep HAPI's referential integrity check happy.

## How we built it

A single A2A agent (`backend/a2a_agent/`, built on raw `a2a-sdk` with no ADK lock-in) registered on Prompt Opinion as an external agent over A2A JSON-RPC. The agent's skill router dispatches into a state-machine sentinel that calls four deterministic clinical tools on an internal MCP server (`backend/mcp_server/tools/`). Gemini 3.1 Flash Lite drafts the SBAR prose — the same model Prompt Opinion's launchpad uses, swappable via the `LLM_PROVIDER` env var. FHIR R4 reads use SHARP context: three HTTP headers (`x-fhir-server-url`, `x-fhir-access-token`, `x-patient-id`) on the MCP path, an equivalent `fhir-context` block in A2A message metadata that `fhir_metadata_to_sharp_headers` converts back to the same headers downstream. `PoCompatMiddleware` (`backend/a2a_agent/po_compat.py:237`) bridges Prompt Opinion's gRPC-flavor JSON-RPC to the spec form both directions: PascalCase `SendMessage` → spec `message/send` inbound, and `state="completed"` / `role="agent"` → `TASK_STATE_COMPLETED` / `ROLE_AGENT` outbound. This is not an LLM wrapper. It is a clinical instrument with rule engines doing the safety-critical work.

## Challenges we ran into

Two stand out. First, Prompt Opinion ships gRPC-flavor JSON-RPC: PascalCase method names, `ROLE_USER` / `TASK_STATE_*` enum values, and a `result.task` oneof wrapper around responses. The installed `a2a-sdk` only speaks the JSON-RPC spec form. We wrote `PoCompatMiddleware` to translate method names and enum values both directions, so the SDK keeps doing what the SDK does and Prompt Opinion sees what its proto-derived deserialiser expects. Second, the architectural commitment that the LLM never decides whether to escalate. That makes the AI feel less central than a generative-first pitch would suggest, but it is non-negotiable for clinical safety — the rule engine is the audit trail, and a hallucinated escalation is the failure mode the system has to design out.

## Accomplishments we're proud of

The same five A2A skills cover post-op and postpartum with zero code branching — same rule engine, same FHIR client, same SBAR generator. The agent never writes to FHIR autonomously: alerts land in a review queue (`backend/api/review_queue.py`), and only the clinician approve flow in the FastAPI proxy writes `Communication` and `AuditEvent`. 475 tests across the suite, lint clean, type-checked. Every clinical threshold cites a public standard (MEWT/Shields 2016, qSOFA/Singer 2016, CDC ASE 2018, KDIGO 2012) and is documented in `docs/CLINICAL_EVIDENCE.md` with a strength rating; the one operational rule — the hemodynamic-trend trigger (SBP drop ≥10% AND HR rise ≥15% over 2h) — is explicitly flagged as not externally validated, in code, in the SBAR output, and in the citations file.

## What we learned

Two findings worth carrying forward. A2A's gRPC-versus-JSON-RPC binding mismatch is real — the spec accommodates both, but the `a2a-sdk` and Prompt Opinion picked different defaults, and a working integration needs a translation layer regardless of which side you build first. And SHARP context propagation is the single most important convention in healthcare-AI interop, because it is the only mechanism that threads session-scoped FHIR credentials through a multi-hop agent chain without leaking them into agent code or environment configuration.

## What's next for Vigil

Pre-deadline: storyboard polish, demo recording, and the Marketplace Studio listing once Prompt Opinion publishes the dedicated walkthrough. Post-deadline: a clinical pilot against MIMIC-IV and a partner institution's deidentified data to validate the operational hemodynamic-trend rule; expansion of the rule library to PEWS, ICU delirium screening, and KDIGO AKI staging beyond the current creatinine check; and SMART-on-FHIR launch into a real EHR using the same SHARP convention Prompt Opinion already uses.

---

## Built with

```
python, mcp, a2a-sdk, fastapi, nextjs, react, typescript, shadcn-ui, tailwind-css, recharts, fhir, hapi-fhir, docker, postgresql, pydantic, httpx, ollama, groq, gemini, claude, prompt-opinion
```

---

## Try it out

- **GitHub:** https://github.com/RaymonddC/Vigil
- **Demo video:** [link to Devpost video]
- **Live agent card:** `https://<deploy>/.well-known/agent-card.json`
- **Live dashboard:** `https://<deploy>/`
- **Empirical smoke evidence:** [`docs/A2A_LOCAL_SMOKE.md`](./A2A_LOCAL_SMOKE.md) — five-skill round-trip + three documented graceful-failure modes against the running agent

---

## Notes for the user

- **Title** is 64 chars, under the 70 limit. Hits Mathur ("postop"), Zheng ("postpartum"), Proctor ("agent" implied by "sentinel"), Mandel ("clinical").
- **Tagline** is 184 chars, under the 200 limit. Mentions FHIR, SBAR, HITL, and the deterministic-rules-first commitment in one line.
- The submission deliberately addresses the three judging axes:
  - **AI Factor:** GenAI drafts SBAR prose that no rule-based system can write; deterministic engines decide the verdict it writes around. The protocol bridge in `po_compat.py` is the load-bearing GenAI-interop story.
  - **Potential Impact:** Catches deterioration 30–60 min earlier in two of the highest-mortality ward settings (4.2 M post-op deaths, one maternal death every two minutes). Same code path covers both.
  - **Feasibility:** No autonomous FHIR writes. Every escalation requires clinician approve. Every threshold cites a public standard. SSRF allowlist on the FHIR URL. Bearer tokens redacted in logs.
- The hemodynamic-trend caveat is preserved intentionally — judges respect intellectual honesty about what is and is not validated.
