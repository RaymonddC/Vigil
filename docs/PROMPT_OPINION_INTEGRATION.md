# Prompt Opinion Integration — Vigil

> **Purpose.** Copy-this-code reference for wiring Vigil's backend into the Prompt Opinion platform. Every pattern below is lifted line-for-line from the two canonical reference repos. Do not re-research — translate directly.

**Canonical sources**
- MCP (Path A): https://github.com/prompt-opinion/po-community-mcp (Python under `python/`)
- A2A (Path B): https://github.com/prompt-opinion/po-adk-python
- SHARP spec: https://www.sharponmcp.com/

---

## 1. Repo Inventory

### 1a. `po-community-mcp` (we care about the `python/` subtree)

```
po-community-mcp/
├── docker-compose-local.yml        # ts:55000, dotnet:55001, python:55002
├── dotnet/                         # reference C# impl (ignore)
├── typescript/                     # reference TS impl (ignore)
└── python/
    ├── Dockerfile                  # python:3.13-alpine, uvicorn main:app :5001
    ├── requirements.txt
    ├── main.py                     # FastAPI + lifespan + mount mcp.streamable_http_app()
    ├── mcp_instance.py             # FastMCP + get_capabilities patch + tool registration
    ├── mcp_constants.py            # SHARP header names
    ├── mcp_utilities.py            # create_text_response helper
    ├── fhir_context.py             # FhirContext dataclass
    ├── fhir_client.py              # httpx-based FHIR client (read / search)
    ├── fhir_utilities.py           # get_fhir_context(ctx), get_patient_id_if_context_exists(ctx)
    └── tools/
        ├── patient_age_tool.py
        ├── patient_allergies_tool.py
        └── patient_id_tool.py
```

- **Python:** 3.13 (see `python/Dockerfile`).
- **Deps** (https://github.com/prompt-opinion/po-community-mcp/blob/main/python/requirements.txt):
  ```
  fastapi>=0.115.0
  uvicorn>=0.32.0
  mcp>=1.9.0
  httpx>=0.28.0
  PyJWT>=2.10.0
  ```
- **Entry point:** `python/main.py`, run with `uvicorn main:app --host 0.0.0.0 --port 5001`.
- **Docker Compose** (https://github.com/prompt-opinion/po-community-mcp/blob/main/docker-compose-local.yml): service `python` exposes `55002:5001`. TS on `55000`, .NET on `55001`.
- **Env vars:** none at build/run time. All per-request context comes from HTTP headers (SHARP).

### 1b. `po-adk-python` (A2A via Google ADK)

> **Historical reference only — we no longer clone this 1:1.** Vigil adopts the raw `a2a-sdk` path (see §3 and the decision in §5.2). The inventory below is preserved because we still copy its FHIR metadata wire format, its AgentCard JSON shape, and its `ApiKeyMiddleware` port. Anywhere this section mentions `google-adk`, `before_model_callback`, or `GOOGLE_API_KEY`, it is describing upstream code, not Vigil's target state.


```
po-adk-python/
├── Dockerfile                        # python:3.12 base; uvicorn $AGENT_MODULE
├── Procfile                          # honcho: 3 agents on 8001/8002/8003
├── docker-compose.yml                # healthcare:8001, general:8002, orchestrator:8003
├── requirements.txt
├── .env.example
├── scripts/test_fhir_hook.sh
├── shared/
│   ├── app_factory.py                # create_a2a_app() — AgentCard + to_a2a + middleware
│   ├── fhir_hook.py                  # extract_fhir_context (ADK before_model_callback)
│   ├── middleware.py                 # ApiKeyMiddleware + message.metadata -> params.metadata bridging
│   ├── logging_utils.py
│   └── tools/fhir.py                 # get_patient_demographics, get_active_medications, ...
├── healthcare_agent/                 # FHIR-connected, port 8001
│   ├── agent.py                      # root_agent = Agent(..., before_model_callback=extract_fhir_context)
│   └── app.py                        # a2a_app = create_a2a_app(..., fhir_extension_uri=...)
├── general_agent/                    # no FHIR, port 8002
│   ├── agent.py
│   ├── app.py
│   └── tools/general.py
└── orchestrator/                     # AgentTool sub-agent routing, port 8003
    ├── agent.py
    └── app.py
```

- **Python:** 3.12+ (Google ADK requirement).
- **Deps** (https://github.com/prompt-opinion/po-adk-python/blob/main/requirements.txt):
  ```
  google-adk>=1.25.0
  a2a-sdk[http-server]>=0.3.0
  httpx>=0.28.0
  uvicorn>=0.41.0
  ```
  Dev extras (`requirements-dev.txt`): `honcho` for multi-process dev.
- **Entry points** (https://github.com/prompt-opinion/po-adk-python/blob/main/Procfile):
  ```
  healthcare:   uvicorn healthcare_agent.app:a2a_app   --host 0.0.0.0 --port 8001
  general:      uvicorn general_agent.app:a2a_app      --host 0.0.0.0 --port 8002
  orchestrator: uvicorn orchestrator.app:a2a_app       --host 0.0.0.0 --port 8003
  ```
- **Docker Compose** (https://github.com/prompt-opinion/po-adk-python/blob/main/docker-compose.yml): one image, three services keyed by `AGENT_MODULE` env var.
- **Env vars** (from `.env.example`):
  - `GOOGLE_API_KEY` — for Gemini via google-adk (required)
  - `GOOGLE_GENAI_USE_VERTEXAI=FALSE`
  - `AGENT_MODULE` — which agent to serve in a given container
  - `PORT`, `HEALTHCARE_AGENT_URL`, `VALID_API_KEYS` (comma-separated for middleware)
  - `LOG_FULL_PAYLOAD`, `LOG_HOOK_RAW_OBJECTS` — debug toggles
  - `PO_PLATFORM_BASE_URL` — used by healthcare_agent/app.py (printed on startup)

---

## 2. MCP Server Integration Pattern (po-community-mcp / python)

### 2.1 FastAPI mounts the MCP streamable HTTP app
`python/main.py` (https://github.com/prompt-opinion/po-community-mcp/blob/main/python/main.py):
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mcp_instance import mcp  # FastMCP instance

@asynccontextmanager
async def lifespan(app: FastAPI):
    # FastMCP requires its session manager to be running for the
    # streamable_http transport to accept requests.
    async with mcp.session_manager.run():
        yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Mount at root — so the MCP endpoint is GET/POST /
app.mount("/", mcp.streamable_http_app())
```
Key takeaway: **mount at `/`, not `/mcp`**. The production URL `https://dotnet.fhir-mcp.promptopinion.ai/mcp` is a reverse-proxy path, not a code-level mount point — but clients hit whatever URL is registered.

### 2.2 Tool registration + `get_capabilities` patch
`python/mcp_instance.py` (https://github.com/prompt-opinion/po-community-mcp/blob/main/python/mcp_instance.py):
```python
from mcp.server.fastmcp import FastMCP
from tools.patient_age_tool import get_patient_age
from tools.patient_allergies_tool import get_patient_allergies
from tools.patient_id_tool import find_patient_id

# stateless_http=True is REQUIRED for Prompt Opinion — SHARP is per-request.
mcp = FastMCP("Python Template", stateless_http=True, host="0.0.0.0")

# ── Patch get_capabilities to advertise the SHARP extension ────────────────
# Prompt Opinion's router inspects server capabilities to decide whether to
# inject FHIR headers. Without this patch, SHARP context is never sent.
_original_get_capabilities = mcp._mcp_server.get_capabilities

def _patched_get_capabilities(notification_options, experimental_capabilities):
    caps = _original_get_capabilities(notification_options, experimental_capabilities)
    # pydantic model_extra is where the MCP SDK stashes unknown fields.
    caps.model_extra["extensions"] = {"ai.promptopinion/fhir-context": {}}
    return caps

mcp._mcp_server.get_capabilities = _patched_get_capabilities

# ── Tool registration — explicit, not decorator-based ──────────────────────
# Tool functions live in tools/*.py as plain async functions.
# FastMCP.tool(...) is called as a function here, not as @mcp.tool.
mcp.tool(name="GetPatientAge",       description="Gets the age of a patient.")(get_patient_age)
mcp.tool(name="GetPatientAllergies", description="Gets the known allergies of a patient.")(get_patient_allergies)
mcp.tool(name="FindPatientId",       description="Finds a patient id given a first name and last name")(find_patient_id)
```

### 2.3 SHARP headers & `FhirContext`
`python/mcp_constants.py` (https://github.com/prompt-opinion/po-community-mcp/blob/main/python/mcp_constants.py):
```python
FHIR_SERVER_URL_HEADER   = "x-fhir-server-url"
FHIR_ACCESS_TOKEN_HEADER = "x-fhir-access-token"
PATIENT_ID_HEADER        = "x-patient-id"
```
`python/fhir_context.py` (https://github.com/prompt-opinion/po-community-mcp/blob/main/python/fhir_context.py):
```python
from dataclasses import dataclass

@dataclass
class FhirContext:
    url: str
    token: str | None = None
```
`python/fhir_utilities.py` (https://github.com/prompt-opinion/po-community-mcp/blob/main/python/fhir_utilities.py):
```python
import jwt
from mcp.server.fastmcp import Context
from fhir_context import FhirContext
from mcp_constants import FHIR_ACCESS_TOKEN_HEADER, FHIR_SERVER_URL_HEADER, PATIENT_ID_HEADER

def get_fhir_context(ctx: Context) -> FhirContext | None:
    # ctx.request_context.request is the Starlette Request.
    req = ctx.request_context.request
    url = req.headers.get(FHIR_SERVER_URL_HEADER)
    if not url:
        return None
    token = req.headers.get(FHIR_ACCESS_TOKEN_HEADER)
    return FhirContext(url=url, token=token)

def get_patient_id_if_context_exists(ctx: Context) -> str | None:
    req = ctx.request_context.request
    fhir_token = req.headers.get(FHIR_ACCESS_TOKEN_HEADER)
    if fhir_token:
        # Prompt Opinion embeds the patient id in the SMART JWT's "patient" claim.
        # Signature is NOT verified here — verification happens at the FHIR server.
        claims = jwt.decode(fhir_token, options={"verify_signature": False})
        if claims.get("patient"):
            return str(claims["patient"])
    # Fall back to explicit x-patient-id header.
    return req.headers.get(PATIENT_ID_HEADER)
```

### 2.4 Example tool (annotated)
`python/tools/patient_age_tool.py` (https://github.com/prompt-opinion/po-community-mcp/blob/main/python/tools/patient_age_tool.py):
```python
from datetime import date
from typing import Annotated
from mcp.server.fastmcp import Context
from pydantic import Field

from fhir_client import FhirClient
from fhir_utilities import get_fhir_context, get_patient_id_if_context_exists
from mcp_utilities import create_text_response

async def get_patient_age(
    patientId: Annotated[  # noqa: N803 — camelCase is intentional for MCP schema
        str | None,
        Field(description="The id of the patient. Optional if patient context already exists"),
    ] = None,
    ctx: Context = None,  # FastMCP injects Context automatically when the param is typed
) -> str:
    # 1. Resolve patient id — explicit arg wins, else from SHARP header / JWT claim.
    if not patientId:
        patientId = get_patient_id_if_context_exists(ctx)
        if not patientId:
            raise ValueError("No patient context found")

    # 2. Resolve FHIR server URL + token from SHARP headers.
    fhir_context = get_fhir_context(ctx)
    if not fhir_context:
        raise ValueError("The fhir context could not be retrieved")

    # 3. Query FHIR.
    fhir_client = FhirClient(base_url=fhir_context.url, token=fhir_context.token)
    patient = await fhir_client.read(f"Patient/{patientId}")
    if not patient:
        return create_text_response("The patient could not be found.", is_error=True)

    birth_date_str = patient.get("birthDate")
    if not birth_date_str:
        return create_text_response("No birth date found.", is_error=True)
    birth_date = date.fromisoformat(birth_date_str)
    today = date.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return create_text_response(f"The patient's age is: {age}")
```

### 2.5 The tiny FHIR client
`python/fhir_client.py` (https://github.com/prompt-opinion/po-community-mcp/blob/main/python/fhir_client.py) — plain `httpx.AsyncClient`, `Authorization: Bearer <token>`, `.read(path)` and `.search(resource_type, params)`. **40 lines total. Copy verbatim into Vigil unless we need a richer wrapper.**

---

## 3. A2A Agent Integration Pattern (raw `a2a-sdk`)

> **Reference repo is still `po-adk-python`** — we copy its FHIR metadata wire format, its AgentCard shape, and its middleware bridging. We do NOT copy its `google-adk` dependency, its `Agent(...)` constructor, or its `to_a2a()` bootstrap. See §5.2 for the decision rationale.

### 3.1 The Agent (raw `a2a-sdk`)

Vigil's A2A agent subclasses `a2a.server.AgentExecutor` (the raw-sdk handler class) instead of ADK's `Agent`. The constructor takes the four Vigil MCP tools as plain async callables and runs the screen → score → sepsis → escalate state machine inside `execute()`. Session state (last-tool-call, accumulated context) lives on the `RequestContext` object the sdk passes on every tick.

```python
# backend/a2a_agent/sentinel.py
from a2a.server import AgentExecutor, RequestContext, EventQueue
from a2a.types import Task, TaskState, TextPart
from backend.a2a_agent.fhir_hook import extract_fhir_from_payload
from backend.a2a_agent.mcp_client import VigilMcpClient   # thin httpx wrapper around our MCP server

class PostopSentinelExecutor(AgentExecutor):
    def __init__(self, mcp: VigilMcpClient):
        self._mcp = mcp

    async def execute(self, ctx: RequestContext, events: EventQueue) -> None:
        # 1. Read FHIR credentials out of the incoming JSON-RPC payload.
        _, fhir = extract_fhir_from_payload(ctx.raw_request)
        if not fhir:
            await events.emit_task(Task.failed("missing FHIR context"))
            return

        # 2. Forward the 3 SHARP headers onto every downstream MCP call.
        headers = {
            "x-fhir-server-url":   fhir["fhirUrl"],
            "x-fhir-access-token": fhir.get("fhirToken", ""),
            "x-patient-id":        fhir["patientId"],
        }

        # 3. Run the state machine — each call is an MCP tool invocation.
        screen = await self._mcp.call("screen_vital_thresholds", headers=headers)
        risk   = await self._mcp.call("score_deterioration_risk", headers=headers)
        sepsis = await self._mcp.call("flag_sepsis_onset",        headers=headers)
        if screen["status"] != "triggered":
            await events.emit_task(Task.completed(parts=[TextPart(text="NORMAL")]))
            return
        escalation = await self._mcp.call("generate_escalation_note",
                                          headers=headers,
                                          body={"vitals_result": screen, "risk_result": risk, "sepsis_result": sepsis})

        # 4. Emit the SBAR + communication_draft back to the caller. The
        #    agent does NOT write to FHIR — the proxy's approve endpoint does.
        await events.emit_task(Task.completed(parts=[TextPart(text=escalation["narrative"])]))
```

*Exact class names (`A2AServer`, `AgentExecutor.execute` signature, `Task.completed(parts=[...])` constructor) to be verified against a2a-sdk 0.3.x during backend task B7; the shape above is schematic.*

The raw-sdk counterpart to ADK's `before_model_callback=extract_fhir_context` is to call `extract_fhir_from_payload()` once at the top of `execute()`. There is no "before LLM" hook because the state machine, not the LLM, is the orchestration layer — the LLM only runs inside individual MCP tools.

### 3.2 The `extract_fhir_from_payload` middleware

With raw `a2a-sdk` there is no ADK callback lifecycle, so the hook becomes a plain pure function we call explicitly. It matches `po-adk-python/shared/fhir_hook.py::extract_fhir_context` behaviorally — same substring match on the metadata key, same `fhirUrl/fhirToken/patientId` field shape — but it takes the raw JSON-RPC payload dict and returns `(key, fhir_dict)` instead of mutating ADK state.

**Canonical implementation lives at `API_CONTRACTS.md:620-657`** — we do not re-state it here. Wire it into `PostopSentinelExecutor.execute()` as shown in §3.1, step 1. For requests where the Prompt Opinion runtime places the metadata at `params.metadata` vs. `params.message.metadata`, the helper's two-candidate probe handles both locations (same fallback order as `po-adk-python/shared/middleware.py::ApiKeyMiddleware`'s bridging behavior).

**Why this is safer than ADK's callback.** ADK's `before_model_callback` fires only when the LLM is about to be invoked — if your agent short-circuits on rule-engine output (which Vigil does on the NORMAL path), the callback may never run and the FHIR headers go unread. The raw-sdk approach runs the extraction unconditionally at request entry, which matches Vigil's "rule engine first, LLM last" control flow.

Metadata wire format is unchanged from the original ADK write-up — same substring match, same field names. The wire payload format shown in `shared/fhir_hook.py` docstring still applies:

```json
{
  "params": {
    "message": {
      "metadata": {
        "https://vigil.local/schemas/a2a/v1/fhir-context": {
          "fhirUrl":   "https://fhir.example.org/r4",
          "fhirToken": "<bearer-token>",
          "patientId": "patient-42"
        }
      }
    }
  }
}
```

### 3.3 AgentCard + A2A app bootstrap (raw `a2a-sdk`)

`a2a.types.AgentCard` is a pydantic v2 model with a camelCase alias generator. Construct it directly; do not go through `google.adk.a2a.utils.agent_to_a2a.to_a2a()`. **The exact JSON shape Vigil serves is already written at `API_CONTRACTS.md:522-580`** — feed that dict through `AgentCard.model_validate(data)` and serve it at `GET /.well-known/agent-card.json`.

Bootstrap pattern (one file, ~30 lines):

```python
# backend/a2a_agent/app.py
import json
from pathlib import Path
from a2a.server import A2AServer
from a2a.types import AgentCard
from backend.a2a_agent.sentinel import PostopSentinelExecutor
from backend.a2a_agent.mcp_client import VigilMcpClient

agent_card_json = json.loads(Path("backend/a2a_agent/agent_card.json").read_text())
agent_card = AgentCard.model_validate(agent_card_json)

mcp = VigilMcpClient(base_url="http://localhost:7001")
executor = PostopSentinelExecutor(mcp)

a2a_app = A2AServer(agent_card=agent_card, executor=executor).build()
```

Run with `uvicorn backend.a2a_agent.app:a2a_app --host 0.0.0.0 --port 9000`. The `a2a-sdk` `A2AServer` handles `/.well-known/agent-card.json`, `message/send`, and `tasks/get` automatically — no FastAPI wrapper needed.

**API key auth.** `po-adk-python/shared/middleware.py::ApiKeyMiddleware` is a Starlette middleware that reads `X-API-Key` from request headers. Port it verbatim (~20 LOC) and attach via `a2a_app.add_middleware(ApiKeyMiddleware)`. No dependency on ADK.

### 3.4 How agents call MCP tools
Short answer: **they don't, in this repo.** The ADK agents bundle their own FHIR tools in `shared/tools/fhir.py` (plain async httpx calls) rather than going back through an MCP server. So in Prompt Opinion's world, Path A (MCP) and Path B (A2A) are **parallel** — an A2A agent either has its tools inline or can chain through another MCP server as an HTTP client. Not demonstrated here.

### 3.5 Running locally (raw `a2a-sdk`)
```bash
uv sync  # pulls a2a-sdk[http-server], httpx, pydantic — NO google-adk
export LLM_PROVIDER=ollama           # or groq | claude | stub
export VIGIL_MCP_URL=http://localhost:7001

# Single-process dev
uvicorn backend.a2a_agent.app:a2a_app --host 0.0.0.0 --port 9000

# Inspect the agent card
curl -sS http://localhost:9000/.well-known/agent-card.json | jq

# Invoke the sentinel end-to-end with inline FHIR metadata
curl -sS -X POST http://localhost:9000/ \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":"req-1","method":"message/send",
    "params":{"message":{"role":"user","parts":[{"kind":"text","text":"Screen PT-007"}],
    "metadata":{"https://vigil.local/schemas/a2a/v1/fhir-context":{"fhirUrl":"http://localhost:8080/fhir","fhirToken":"","patientId":"PT-007"}}}}
  }'
```

No `GOOGLE_API_KEY` is required. No `honcho` multi-agent Procfile. No ADK web UI. One process, one port, one LLM provider selected by env var. **This is the whole stack.**

---

## 4. SHARP Headers + Capability Extension — Copy-Paste Block

Single self-contained snippet for a Vigil MCP tool that reads all three headers, constructs a `FhirContext`, and passes it to logic. **Paste this into `backend/vigil_mcp/` as the starting point.**

```python
# vigil_mcp/server.py
from dataclasses import dataclass
from mcp.server.fastmcp import FastMCP, Context

# ── SHARP header names ─────────────────────────────────────────────────────
FHIR_SERVER_URL_HEADER   = "x-fhir-server-url"
FHIR_ACCESS_TOKEN_HEADER = "x-fhir-access-token"
PATIENT_ID_HEADER        = "x-patient-id"

@dataclass
class FhirContext:
    url: str
    token: str | None
    patient_id: str | None

# ── FastMCP + capability patch ─────────────────────────────────────────────
mcp = FastMCP("vigil-mcp", stateless_http=True, host="0.0.0.0")

_orig = mcp._mcp_server.get_capabilities
def _patched(notification_options, experimental_capabilities):
    caps = _orig(notification_options, experimental_capabilities)
    caps.model_extra["extensions"] = {"ai.promptopinion/fhir-context": {}}
    return caps
mcp._mcp_server.get_capabilities = _patched

# ── Helper read on every tool invocation ───────────────────────────────────
def sharp_context(ctx: Context) -> FhirContext:
    req = ctx.request_context.request
    url = req.headers.get(FHIR_SERVER_URL_HEADER)
    if not url:
        raise ValueError("Missing SHARP header: x-fhir-server-url")
    return FhirContext(
        url=url,
        token=req.headers.get(FHIR_ACCESS_TOKEN_HEADER),
        patient_id=req.headers.get(PATIENT_ID_HEADER),
    )
```

---

## 5. Our Adaptation Plan — Vigil

### 5.1 MCP server (our 4 tools)
**Recommendation: clone `po-community-mcp/python/` layout 1:1.** It is ~200 lines total; rewriting from scratch adds risk. Keep FastMCP + streamable_http_app + capability patch + SHARP header helpers exactly as-is. Our tools become:
- `screen_vital_thresholds` — queries `Observation?patient=X&category=vital-signs`
- `score_deterioration_risk` — computes NEWS2 from the last vitals bundle
- `flag_sepsis_onset` — qSOFA over last 6h of observations + Conditions
- `generate_escalation_note` — composes SBAR text, no FHIR write

Suggested file map in Vigil repo:

```
backend/
└── vigil_mcp/
    ├── Dockerfile                 # mirrors po-community-mcp/python/Dockerfile
    ├── requirements.txt           # fastapi, uvicorn, mcp>=1.9, httpx, PyJWT
    ├── main.py                    # verbatim from po-community-mcp
    ├── mcp_instance.py            # FastMCP + capability patch + 4 tool registrations
    ├── mcp_constants.py           # SHARP headers
    ├── fhir_context.py            # dataclass
    ├── fhir_client.py             # verbatim + extend with .search helpers we need
    ├── fhir_utilities.py          # get_fhir_context, get_patient_id
    └── tools/
        ├── screen_vital_thresholds.py
        ├── score_deterioration_risk.py
        ├── flag_sepsis_onset.py
        └── generate_escalation_note.py
```

### 5.2 A2A agent — **use raw `a2a-sdk`, NOT `google-adk`**

Justification:
1. `google-adk` hard-wires Gemini (`model="gemini-2.5-flash"` + `GOOGLE_API_KEY` — see §3.1). That directly breaks the `LLM_PROVIDER=ollama|groq|claude|stub` abstraction locked in `PROJECT_BRIEF.md:56` and the `DEMO_SCRIPT.md:18` precondition `LLM_PROVIDER=claude`. Adapting Claude into ADK's "model-agnostic interface" is a 3-6h unbudgeted spike on top of the 1-2h copy claim.
2. Five of the six architecture docs already assume raw `a2a-sdk`: `PROJECT_BRIEF.md:53`, `ARCHITECTURE.md:206`, `API_CONTRACTS.md:5`, `BUILD_PLAN.md` (F1 + B7), `RISK_REGISTER.md:18`. Flipping one doc (this one) aligns all six; the inverse flip would break five.
3. The "hard parts" of the raw-sdk port already exist verbatim:
   - **AgentCard JSON** — `API_CONTRACTS.md:522-580` is written in the exact shape `a2a.types.AgentCard` (pydantic v2) consumes.
   - **FHIR metadata bridge** — `API_CONTRACTS.md:620-657` defines `extract_fhir_from_payload(payload) -> (metadata_key, fhir_dict)`, ported line-by-line from `po-adk-python/shared/fhir_hook.py::extract_fhir_context` but rewritten as a framework-agnostic pure function. It attaches to an a2a-sdk request handler as a request-intercept middleware (see §3.1 below) instead of as an ADK `before_model_callback`.
4. **Only real loss** vs. ADK: ~80 LOC of session-state plumbing between tool calls. The a2a-sdk `TaskHandler` pattern replaces this. Estimated delta: 6-8h for the full port (vs. the ADK path's 1-2h copy + 3-6h adapter spike = 4-8h). Net even, with zero model lock-in.
5. **Fallback (KS-4).** If the raw port bogs past 8h, `RISK_REGISTER.md:61` already endorses hand-rolled FastAPI A2A (~50 LOC covering `message/send`, `tasks/get`, and the agent-card GET) as the pre-committed pivot. Option B → Option C is a mechanical fallback, not a redesign.

Suggested file map:

```
backend/
└── a2a_agent/
    ├── Dockerfile                  # python:3.12-slim, uvicorn backend.a2a_agent.app:a2a_app
    ├── requirements.txt            # a2a-sdk[http-server]>=0.3.0, httpx>=0.28.0, pydantic>=2.8  (NO google-adk)
    ├── agent_card.json             # the JSON shape from API_CONTRACTS.md:522-580, served at /.well-known/agent-card.json
    ├── app.py                      # A2AServer(agent_card, executor).build() — see §3.3
    ├── sentinel.py                 # PostopSentinelExecutor(AgentExecutor) — see §3.1
    ├── fhir_hook.py                # extract_fhir_from_payload() — see API_CONTRACTS.md:620-657
    ├── middleware.py               # ApiKeyMiddleware (ported from po-adk-python, ~20 LOC)
    └── mcp_client.py               # thin httpx wrapper that forwards 3 SHARP headers onto every MCP call
```

**Tools are not defined in this tree.** They live in `backend/vigil_mcp/tools/` (MCP server, single source of clinical logic). The A2A executor calls them over HTTP via `mcp_client`, which injects the SHARP headers extracted from A2A metadata. This gives us the dual-path submission (MCP marketplace listing + A2A marketplace listing) without duplicating logic.

---

## 6. Publishing to Marketplace — Known / Unknown

**Confirmed from repo + homepage:**
- Agents register by providing the public agent-card URL (`https://<host>/.well-known/agent-card.json`) + an X-API-Key value to Prompt Opinion (`po-adk-python/README.md` §"Connecting to Prompt Opinion").
- Deployment target for the reference agents is **Google Cloud Run** via `gcloud run deploy --source .` — **not** an ADK-specific deployer. `adk deploy cloud_run` is documented as incompatible because it wraps the agent in ADK's FastAPI server rather than `to_a2a()`. (https://github.com/prompt-opinion/po-adk-python/blob/main/README.md)
- MCP servers under `po-community-mcp` appear to be pushed to `https://dotnet.fhir-mcp.promptopinion.ai/mcp` et al via GitHub Actions workflows (`deploy-dotnet-dev.yaml`, `deploy-dotnet-prod.yaml`, `deploy-ts-dev.yaml`, `deploy-ts-prod.yaml`). These are Prompt Opinion's **internal** deploy pipelines — not something external contributors trigger. **There is no `deploy-python-*.yaml`** in the repo, implying the Python variant is not currently published by them.
- No `prompt_opinion_config.json` / manifest file exists in either repo (searched both trees).

**Unknown:**
- Whether publishing for external builders is a web upload at app.promptopinion.ai, a CLI command, or a "paste your URL" form. **Assumption: for the hackathon, we self-host on Cloud Run / Railway / Fly, then paste our public URL into a Prompt Opinion form.**
- Whether there's an OAuth/client-id handshake, or just the X-API-Key we generate ourselves.
- Whether the platform ever calls an MCP server directly (Path A) — or whether MCP tools must be proxied through an A2A agent.

**Fallback if publishing is blocked at deadline:**
- Submit GitHub repo URL + 3-min demo video directly to Devpost.
- In the Devpost description, note: "Deployed to Cloud Run at `<url>`; agent card at `<url>/.well-known/agent-card.json`; Prompt Opinion registration pending per Discord guidance."
- Include a `curl` example in the README showing how to invoke the A2A agent end-to-end with FHIR metadata, so judges can reproduce without the platform.

---

## 7. Config File Drafts (**speculative — confirm on Discord**)

No file of this shape exists in either reference repo. Drafting optimistically from the Vigil tech concept doc:

**`backend/vigil_mcp/prompt_opinion_config.json`** (speculative):
```json
{
  "name": "vigil-mcp",
  "version": "1.0.0",
  "type": "mcp_server",
  "description": "Early-warning clinical deterioration detection for inpatients using FHIR vitals/observations.",
  "tools": [
    "screen_vital_thresholds",
    "score_deterioration_risk",
    "flag_sepsis_onset",
    "generate_escalation_note"
  ],
  "fhir_resources_required": ["Observation", "Encounter", "Procedure", "Condition", "Patient"],
  "sharp_context": true,
  "capabilities": { "extensions": { "ai.promptopinion/fhir-context": {} } }
}
```

**`backend/vigil_agent/prompt_opinion_config.json`** (speculative):
```json
{
  "name": "vigil-agent",
  "version": "1.0.0",
  "type": "a2a_agent",
  "description": "Orchestrates Vigil's deterioration-detection MCP tools into a single SBAR escalation workflow.",
  "agent_card_url": "https://<deploy>/.well-known/agent-card.json",
  "security": { "apiKey": { "header": "X-API-Key" } },
  "fhir_extension_uri": "https://<workspace>.promptopinion.ai/schemas/a2a/v1/fhir-context"
}
```

> **STATUS:** speculative, confirm on Discord. The real answer may be "no config file — just submit the URL." Do not block on this; ship the agent card + MCP capability extension (which are real and mandatory), and treat any config file as additive.

---

## 8. Discord Questions (ask on day 1)

1. **MCP publishing:** For a community-built Python MCP server (FastMCP + `streamable_http_app`), what is the exact flow to list it on the Prompt Opinion Marketplace? Is it a web form, a CLI, a GitHub app, or a PR against a registry repo?
2. **A2A publishing:** For an A2A agent built on raw `a2a-sdk` (Vigil's path — see §5.2) or on `google-adk` + `po-adk-python` (the reference path), do you need the agent card URL + API key only, or is there a manifest file we must include in the repo?
3. **Manifest / config file:** Does a `prompt_opinion_config.json` (or any named manifest) exist? If so, what's the schema? We couldn't find one in `po-community-mcp` or `po-adk-python`.
4. **CLI:** Is there an official `promptopinion` / `po` CLI for validation or deploy? We see GitHub Actions workflows deploying the reference C#/TS MCP servers internally — is any of that tooling public?
5. **Hackathon tier:** Is there a free workspace / participant credentials for Agents Assemble builders so we can register and test before the 2026-05-11 deadline? Also: is the `fhir_extension_uri` workspace-scoped, or can we use a shared hackathon one?

---

## Appendix: Pattern Checklist (printable)

- [ ] FastMCP with `stateless_http=True`
- [ ] Mount via `app.mount("/", mcp.streamable_http_app())`
- [ ] `async with mcp.session_manager.run()` inside FastAPI lifespan
- [ ] Patch `mcp._mcp_server.get_capabilities` to add `ai.promptopinion/fhir-context`
- [ ] Read `x-fhir-server-url` / `x-fhir-access-token` / `x-patient-id` from `ctx.request_context.request.headers` in every tool
- [ ] Tools are plain async functions, registered via `mcp.tool(name=..., description=...)(fn)` — not decorators
- [ ] A2A side: `PostopSentinelExecutor(AgentExecutor)` with `extract_fhir_from_payload()` called at `execute()` entry
- [ ] `A2AServer(agent_card=AgentCard.model_validate(agent_card_json), executor=executor).build()` with `AgentExtension` declared inside the agent-card JSON under `capabilities.extensions`
- [ ] Middleware bridges `message.metadata` → `params.metadata`
- [ ] Served with `uvicorn <pkg>.app:a2a_app` on 8001
- [ ] Agent card at `GET /.well-known/agent-card.json` (handled by `to_a2a()`)
