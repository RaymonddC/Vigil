# Prompt Opinion Publishing Flow — Research Notes

> **UPDATED 2026-04-22:** Darena Health published the official "Agents Assemble Challenge — Getting Started" video on YouTube ([Qvs_QK4meHc](https://www.youtube.com/watch?v=Qvs_QK4meHc)). The video answers Q1 and Q2 definitively — no Discord needed. The answers below are now **HIGH confidence** with the canonical source. See `## Confirmed Publishing Flow (from official video)` at the bottom of this file for the locked walkthrough.

> Original research from 2026-04-21 (public sources, no Discord). Confidence ratings retained for historical context.

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

~~Ask these on day 1, in order of blocking risk:~~ **NO LONGER NEEDED — answered by Darena Health's official Getting Started video (2026-04-22). See section below.** The blocking questions Q1, Q2, Q3 (workspace scope), Q4 (manifest), and Q5 (CLI) are all definitively resolved.

The only thing not covered in the video that may still warrant a Discord ask is whether participants get a shared `fhir_extension_uri` for cross-team interop, but that doesn't block our submission — each team's workspace-scoped URI works for the judging flow.

---

## Confirmed Publishing Flow (from official video — HIGH confidence)

**Source:** "Agents Assemble Challenge — Getting Started" by Darena Health, https://www.youtube.com/watch?v=Qvs_QK4meHc (uploaded ~2026-04). Walkthrough delivered by the platform's product lead.

### Marketplace publishing — both Path A and Path B

The dashboard at `app.promptopinion.ai` has a section labelled **"Marketplace Studio"** at the bottom of the left nav. Publishing is done from there:

1. Open `app.promptopinion.ai` → log in
2. Click **Marketplace Studio** (bottom of left nav)
3. Choose **MCP Server** or **Agent** depending on what you're publishing
4. Click **Add / Publish**, paste your endpoint URL (same form as adding to your own workspace)
5. The listing becomes discoverable for judges to test

**Required before judging starts.** Quote: *"This step will be needed before the judging starts."*

### Path A — MCP server registration (private workspace test path)

Same form, just routed to your own workspace instead of the public marketplace:

1. Workspace Hub → "Add new MCP server"
2. Paste URL: `https://<your-host>/mcp` (note: include the `/mcp` path)
3. Name it, choose **"Streamable HTTP"** transport
4. **Check the box for "pass token"** — this is what triggers the SHARP `x-fhir-access-token` injection at runtime
5. Click **Test** — the platform fetches your tools list and shows them registered
6. Click **Save**

Vigil endpoint: our MCP server is mounted at `/mcp` via the FastAPI mount in `backend/mcp_server/server.py` — already correct.

### Path B — External A2A agent registration

1. Workspace Hub → **"Connect external agent"** → Add connection
2. Paste agent **base URL** (NOT the `/.well-known/agent-card.json` path — just `https://<your-host>`)
3. Click **Check** — platform auto-fetches the AgentCard and displays the declared skills
4. If your AgentCard declares an API-key security scheme, paste your `VIGIL_API_KEY` value
5. **Toggle "FHIR context" → ON** — so the platform injects FHIR metadata into A2A messages at the `https://vigil.local/schemas/a2a/v1/fhir-context` extension key
6. Click **Save**

Vigil A2A: AgentCard already advertises the `ai.promptopinion/fhir-context` extension as required, and `apiKey` security scheme (X-API-Key header). Both already match the form fields the video shows.

### Important runtime detail

> *"When you create the workspace within Prompt Opinion it is actually a fire server. So you can pretty much make any fire server calls from that MCP server which will be made to your workspace."*

So at runtime, the SHARP `x-fhir-server-url` will point to the **judge's PO workspace FHIR endpoint** — not their local HAPI, not our HAPI, not our fixture. Our MCP tools query whatever workspace is calling. This means the fixture-mode deploy is fine for our hosting (judges don't hit our FHIR), as long as we never hardcode FHIR URLs.

**Action:** verify our `FHIR_BASE_URL` env var is only a fallback default and that SHARP headers always win. (Already true in `backend/mcp_server/context.py` — confirmed.)

### Free LLM option

Quote: *"to get you started, what you can do is you can use Google AI Studio... we recommend the Gemini 3.1 Flash Light"* (free Gmail-tier API key, paste into PO settings).

So if the user wants to skip Anthropic / Groq billing, **Gemini Flash Light is the platform-default free option** for testing. For the demo recording, Claude or Groq still produces nicer SBAR prose, but there's no hard blocker.

### Submission checklist (revised)

Replaces the speculative items in `docs/SUBMISSION_LOG.md` §6:

- [ ] Deploy MCP server to a public HTTPS URL (Render / GCP / etc.)
- [ ] Deploy A2A agent to a public HTTPS URL with the AgentCard at `/.well-known/agent-card.json`
- [ ] In `app.promptopinion.ai` Workspace Hub: add MCP, check "pass token", run Test
- [ ] In Workspace Hub: Connect external agent, paste API key, toggle FHIR context
- [ ] In Marketplace Studio: publish MCP server (one entry)
- [ ] In Marketplace Studio: publish A2A agent (second entry)
- [ ] Capture both Marketplace URLs → paste into Devpost submission
- [ ] Confirm judges can hit both via the public dashboard test panel

---

*Original research notes preserved above for the historical record. Treat the **Confirmed Publishing Flow** section as the canonical reference for any submission-day work.*
