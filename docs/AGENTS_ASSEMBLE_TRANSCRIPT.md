# Agents Assemble Challenge — Getting Started Video Transcript

**Source:** [YouTube — Darena Health, 2026-03-03](https://www.youtube.com/watch?v=Qvs_QK4meHc) (19m24s)
**Captured:** 2026-04-25 (~7 weeks before deadline)

This transcript covers the host walking through the three ways to submit
to the Agents Assemble Challenge. It is the canonical "what the platform
actually expects" reference and overrides any earlier project assumptions
about Prompt Opinion's submission model.

---

## Submission paths — three options the host walks through

### Option 1 — No-code A2A agent built inside Prompt Opinion

Configure an agent entirely inside the Prompt Opinion workspace. No
external code. Upload documents, set system prompt (optional — agents
default to using their grounding content), enable the A2A flag, define
a skill, save. Test by chatting with the general chat agent and asking
it to "consult my external agent." Suitable for content-grounded agents
(e.g. organizational policies).

### Option 2 — Custom MCP server (external)

Build an MCP server using `prompt-opinion/po-community-mcp` as starter.
Run it (the host uses ngrok to expose `localhost`). In Prompt Opinion's
**Workspace Hub**, add the MCP server by URL — choose *Streamable HTTP*,
optionally add an auth key, and **check the "pass FHIR token" box** so
Prompt Opinion forwards FHIR session context to your tools. Test by
attaching the tool to a custom agent and triggering it from the
launchpad chat.

### Option 3 — Independent A2A agent (external) — the path we're on

Build an A2A agent. The host's reference templates are
`prompt-opinion/po-adk-python` and `po-adk-typescript` (both
Google-ADK-based, "wipe-coded from Google ADK"). Use any A2A-compatible
stack — ADK is not required, the only requirement is "the agent can
support A2A".

Set the agent's public URL via env var (so the agent card it serves
knows its own location). Run it, expose via ngrok or a real public host,
restart so it picks up the new URL. In Prompt Opinion's Workspace Hub:

- Click **Add Connection** for an external agent
- Paste the public agent URL
- Click **Check** — Prompt Opinion fetches the agent card and shows the
  declared skills
- If the agent card declares `apiKey` security, paste the key
- If the agent card declares the FHIR-context extension, **toggle it on**
  (so Prompt Opinion injects FHIR URL + bearer token + patient ID into
  every call)
- Save

Test from the launchpad: pick a patient, use the general chat agent,
ask it to "consult [external-agent-name] about [thing]." General chat
calls our agent over A2A, our agent uses FHIR context to answer,
general chat summarizes the response.

---

## Publishing for the competition (Marketplace Studio)

> "Once you have built your agents or an MCP server and you have tested
> it, there will be one additional step that you will have to do — we
> will be building a detailed video on that too."

The host points to **Marketplace Studio** at the bottom of the Prompt
Opinion UI. Whether Path A (MCP) or Path B (A2A), publish there before
judging. *"This step will be needed before the judging starts."*

A separate, dedicated video on the publish flow is promised.

---

## Operational details called out

- **Workspace doubles as a FHIR server.** Anything you add to a Prompt
  Opinion workspace (synthetic patients, uploaded clinical notes,
  custom bundles) lives on a workspace-scoped FHIR server. MCP and A2A
  components query that server using the FHIR token Prompt Opinion
  forwards.
- **Three ways to load patients:** import synthetic patients from
  Prompt Opinion's catalog, upload your own FHIR bundle, or manually
  add a patient and attach documents. The host strongly recommends
  attaching clinical notes — most demo scenarios involve generative AI
  reasoning over notes.
- **Default model.** Use Google AI Studio for the model; the host
  recommends *Gemini 3.1 Flash Lite*. Get a free Gmail-auth API key,
  paste into Prompt Opinion's "Load Models" config.
- **Security.** External agents and MCP servers are unauthenticated by
  default. The community templates ship with an `X-API-Key` middleware
  example; the agent card declares the security scheme so Prompt
  Opinion knows to ask for the key when adding the connection.
- **FHIR context is opt-in per integration.** The "pass token" /
  "enable FHIR" checkbox at integration time is what unlocks SHARP
  context propagation. Without it, your tool/agent gets called without
  FHIR credentials.

---

## Implications for Vigil's submission

The host's demo invocation pattern is **request-response over chat**:
the user asks the general chat agent a question, general chat calls
our external agent for a specialized answer, our agent uses FHIR
context to fetch + reason + reply.

Our current A2A agent runs an autonomous polling loop (the 7-state
sentinel). That model does not fit the host's demo flow. To compete on
Path B, the agent needs to expose request-response skills that Prompt
Opinion's general chat can invoke per patient — e.g. "score this
patient for sepsis," "draft an SBAR," "screen for deterioration." The
autonomous loop can stay (it's a background mode), but the *value the
judges will see* lives in the on-demand skills surfaced by the agent
card.

See `STORYBOARD.md` and `BUILD_PLAN.md` for how this reframes the demo.
