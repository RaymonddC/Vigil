# Prompt Opinion Publishing Flow — Research Notes

> Researched 2026-04-21 from public sources only (no Discord). Confidence ratings reflect source authority.

---

## Q1 — How to publish an MCP server to the Marketplace

**Answer:** Self-host, then submit your public endpoint URL via `app.promptopinion.ai`.

Steps inferred from multiple public sources:

1. Deploy your FastMCP server to a publicly reachable HTTPS URL (Cloud Run, Railway, Fly.io, etc.).
2. Confirm the capability extension is declared: `caps.model_extra["extensions"] = {"ai.promptopinion/fhir-context": {}}` — the platform router inspects this to decide whether to inject SHARP headers.
3. Log in at `https://app.promptopinion.ai` and locate the MCP server registration form (no direct link is publicly documented — navigate to the Marketplace or Developer section of the dashboard).
4. Submit your public MCP endpoint URL (the root `/` path, not `/mcp`).
5. Optionally supply an API key value if you want the platform to include `X-API-Key` on inbound requests.

**What is NOT known:** Whether there is a dedicated "Add MCP Server" form in the dashboard, or whether you must go via Discord/email request. The `docs.promptopinion.ai/mcp-servers` URL returns 404. No CLI or GitHub integration is documented for external contributors.

**Confidence:** Low  
**Fallback:** If blocked at submission time, include your MCP endpoint URL and a `curl` invocation example in the Devpost description. The judges are Prompt Opinion insiders and can manually invoke it.

**Sources:**
- [po-overview README](https://github.com/prompt-opinion/po-overview) — "publish endpoints to the registry for immediate organization access"
- [Agents Assemble devpost](https://agents-assemble.devpost.com/) — Step 4: "Publish project to Prompt Opinion Marketplace"
- [po-community-mcp README](https://github.com/prompt-opinion/po-community-mcp) — no publishing instructions; references SHARP spec only

---

## Q2 — How to publish an A2A agent

**Answer:** 4-step registration — deploy → configure workspace URL → provide agent card URL to PO → supply API key.

This is the best-documented path. From `po-adk-python/README.md`:

1. **Deploy** your agent to a public HTTPS URL (Cloud Run recommended — see GCP deploy commands in the README).
2. **Set `PO_PLATFORM_BASE_URL`** env var to your workspace URL:  
   `PO_PLATFORM_BASE_URL=https://your-workspace.promptopinion.ai`  
   This makes the FHIR extension URI workspace-scoped:  
   `https://your-workspace.promptopinion.ai/schemas/a2a/v1/fhir-context`
3. **Provide to Prompt Opinion:**
   - Agent card URL: `https://your-agent.example.com/.well-known/agent-card.json`
   - Your `X-API-Key` value (the platform sends this header on all inbound requests)
4. **Platform auto-discovery:** PO fetches the agent card, reads `supportedInterfaces` to find your endpoint, learns whether an API key is required, and begins routing requests.

**How you "provide" the URL + API key** is not spelled out in any public doc (likely a form in `app.promptopinion.ai` — no direct URL found). Based on po-overview issue #28 ("Allow adding External Agent to Orchestrator Agent"), external agent addition may also happen in-app via the Orchestrator Agent config UI.

**Required agent card fields for v1:**
- `supportedInterfaces[].url` — your public endpoint
- `supportedInterfaces[].protocolBinding` — `"application/json-rpc"`
- `supportedInterfaces[].protocolVersion` — `"2.0"`
- `capabilities.stateTransitionHistory` — must be `false`
- `securitySchemes` — typed-key nesting format (`apiKeySecurityScheme`)

**Confidence:** Medium  
(The *fields* are confirmed from the README; the exact *submission mechanism* — web form vs. API call vs. Discord request — is inferred, not confirmed.)

**Sources:**
- [po-adk-python README §Registration with Prompt Opinion](https://github.com/prompt-opinion/po-adk-python/blob/main/README.md)
- [po-overview issues](https://github.com/prompt-opinion/po-overview/issues) — issue #28 implies external agents are added through the platform UI

---

## Q3 — Is there a manifest / config file format?

**Answer:** No — no `prompt_opinion_config.json` or equivalent manifest exists.

Direct evidence:
- Neither `po-community-mcp` nor `po-adk-python` contain any manifest file.
- The `po-overview` README describes registration as "publish endpoints to the registry" — no manifest mentioned.
- Search of both repos' file trees found no JSON config file with platform-specific fields.

The *de facto* manifest for MCP is the capability extension in `get_capabilities` (advertises `ai.promptopinion/fhir-context`). The *de facto* manifest for A2A is the agent card JSON at `/.well-known/agent-card.json` — this serves as the registration document.

**Confidence:** High (no manifest file exists in any reference repo; registration is URL-based)

**Discord question if needed:** "Do you require a `prompt_opinion_config.json` or any named manifest file in the repo, or is the agent card / capability extension the complete registration artifact?"

**Sources:**
- [po-community-mcp repo](https://github.com/prompt-opinion/po-community-mcp) — no manifest found
- [po-adk-python repo](https://github.com/prompt-opinion/po-adk-python) — no manifest found; agent card is the registration document

---

## Q4 — Is there a CLI for publishing?

**Answer:** No public CLI exists.

Evidence:
- No `po`, `promptopinion`, or `po-cli` command referenced in any README, docs, or GitHub issue.
- The GitHub Actions workflows visible in `po-community-mcp` (`deploy-dotnet-dev.yaml`, `deploy-dotnet-prod.yaml`, `deploy-ts-dev.yaml`, `deploy-ts-prod.yaml`) are Prompt Opinion's **internal** CI/CD pipelines, not public tooling. There is no `deploy-python-*.yaml`, confirming the Python path is not on their internal deploy pipeline.
- `docs.promptopinion.ai` navigation shows only "Getting Started" and "FHIR Context" — no CLI section.
- No npm package, PyPI package, or Homebrew formula found for a Prompt Opinion CLI.

**Confidence:** High (absence of evidence across all repos and docs)

**Discord question if needed:** "Is there an official `po` or `promptopinion` CLI for validation or publishing, or is registration done entirely through the web dashboard?"

**Sources:**
- [po-community-mcp](https://github.com/prompt-opinion/po-community-mcp) — internal deploy YAMLs only
- [po-overview](https://github.com/prompt-opinion/po-overview) — no CLI reference
- [docs.promptopinion.ai](https://docs.promptopinion.ai/) — no CLI section

---

## Q5 — Hackathon credentials / free tier

**Answer:** Free accounts are confirmed for all Agents Assemble participants. No special hackathon credentials beyond a standard free account.

Confirmed from Devpost:
- "Register: Sign up on the Hackathon Website and **create a free account at Prompt Opinion**" — `https://app.promptopinion.ai`
- The getting-started docs walk through creating a free account using a Google Gemini API key (free from Google AI Studio) — no payment required.
- Platform provides free access to the workspace, synthetic EHR data, and the agent composition UI.

**Workspace URL format:** `https://your-workspace.promptopinion.ai` — each account gets a subdomain. The `fhir_extension_uri` is workspace-scoped, not shared across participants.

**No evidence found for:**
- A shared hackathon workspace or pre-provisioned credentials
- A special "Agents Assemble" promo code or API key
- A test/sandbox mode distinct from production

**Confidence:** Medium  
(Free account access confirmed; whether there are *special* hackathon-only credentials — e.g., higher rate limits, pre-loaded FHIR test data — is unknown.)

**Discord question if needed:** "Is there a shared hackathon workspace or special credentials for Agents Assemble participants, or does everyone use their own free account? Also: is the `fhir_extension_uri` always workspace-scoped, or can we use a shared test URI?"

**Sources:**
- [Agents Assemble devpost](https://agents-assemble.devpost.com/) — "create a free Prompt Opinion account"
- [docs.promptopinion.ai/getting-started](https://docs.promptopinion.ai/getting-started) — free Gemini key walkthrough

---

## Additional Findings

### HTTPS requirement
Almost certainly required — the Prompt Opinion platform makes outbound calls to your deployed endpoint. Cloud Run provides HTTPS by default; Railway and Fly.io do as well. No explicit cert requirement stated in docs, but plain HTTP endpoints would be rejected in practice.

### FHIR version / SMART app launch compliance
No evidence of any FHIR version check or SMART app launch conformance test performed by the platform. The platform passes through a bearer token from the user's EHR session — your code reads it from the `x-fhir-access-token` header without further validation. FHIR R4 is the assumed version (all reference code uses R4 endpoints).

### Test / sandbox mode
No test or sandbox mode found in any public documentation. The getting-started flow uses a synthetic patient created directly in the workspace — this appears to be the "sandbox" equivalent.

### Rate limits / publishing fees
No rate limits or fees documented publicly. Free tier appears unlimited for hackathon purposes.

### "Publish to Marketplace" button
`app.promptopinion.ai` is fully authenticated — could not inspect the dashboard. Based on po-overview issue #28 (adding external agents) and the general pattern described, there is likely a form in the Agent or Marketplace section of the dashboard. Confirmed via Devpost that the step exists; mechanism unknown without login.

---

## Discord Questions Prioritized

Ask these on day 1, in order of blocking risk:

1. **(BLOCKING — MCP)** What is the exact flow to list a community Python MCP server on the Prompt Opinion Marketplace? Is it a form in `app.promptopinion.ai`, a Discord request, or a PR against a registry repo?
2. **(BLOCKING — A2A)** To register an external A2A agent, do we submit the agent card URL + API key via a form in the app? Or is there a different channel (Discord, email, API call)?
3. **(MEDIUM — credentials)** Is there a shared hackathon workspace or special credentials for Agents Assemble participants, or does each builder use their own free account? Is the `fhir_extension_uri` workspace-scoped?
4. **(LOW — manifest)** Do you require any `prompt_opinion_config.json` manifest file, or are the agent card + MCP capability extension the complete registration artifacts?
5. **(LOW — CLI)** Is there an official `po` CLI for validation or publishing, or is everything done through the web dashboard?
