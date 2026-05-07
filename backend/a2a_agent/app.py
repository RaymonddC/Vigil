"""Vigil A2A agent application bootstrap.

Builds the A2A FastAPI application serving:
- AgentCard at GET /.well-known/agent-card.json
- JSON-RPC endpoint at POST /a2a
- POST /tick — runs one sentinel cycle across every seeded patient
- Optional polling loop (POLL_INTERVAL_SEC env, default 900s, demo 30s)

Reference: PROMPT_OPINION_INTEGRATION.md §3.3, BUILD_PLAN.md B7–B8
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

from backend.a2a_agent.agent_card_v1 import AgentCardV1
from backend.a2a_agent.mcp_client import VigilMcpClient
from backend.a2a_agent.po_compat import PoCompatMiddleware
from backend.a2a_agent.sentinel import PostopSentinelExecutor
from backend.a2a_agent.tick import run_cycle_for_all_patients
from backend.obs.logging import configure_logging, get_logger
from backend.security.api_key import build_api_key_middleware, warn_if_unset

# ---------------------------------------------------------------------------
# Logging — shared JSON formatter + bearer token filter (H3)
# ---------------------------------------------------------------------------

configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
logger = get_logger("vigil.a2a.app")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

A2A_PORT = int(os.environ.get("A2A_PORT", "9000"))
POLL_INTERVAL_SEC = int(os.environ.get("POLL_INTERVAL_SEC", "900"))
FHIR_BASE_URL = os.environ.get("FHIR_BASE_URL", "http://localhost:8080/fhir")

# ---------------------------------------------------------------------------
# AgentCard — load from JSON file
# ---------------------------------------------------------------------------

_card_path = Path(__file__).parent / "agent_card.json"
_card_data = json.loads(_card_path.read_text(encoding="utf-8"))

# Override URL from env if deploying publicly. A2A v1 has both the legacy
# top-level `url` (still required by the installed v0.3 SDK) and the canonical
# `supportedInterfaces[].url`. Both must point at the public URL or Prompt
# Opinion will read the latter and call back at localhost.
if os.environ.get("A2A_PUBLIC_URL"):
    _public_url = os.environ["A2A_PUBLIC_URL"].rstrip("/")
    # The JSON-RPC handler is mounted at POST /a2a (see app_builder.build below).
    # Tolerate operators setting A2A_PUBLIC_URL to either the host root or the
    # full RPC URL — Prompt Opinion will POST to whatever the AgentCard advertises,
    # so the path suffix must match the mount or every call 405s.
    if not _public_url.endswith("/a2a"):
        _public_url = f"{_public_url}/a2a"
    _card_data["url"] = _public_url
    for _iface in _card_data.get("supportedInterfaces", []):
        _iface["url"] = _public_url

agent_card = AgentCardV1.model_validate(_card_data)

# ---------------------------------------------------------------------------
# Wire up executor → handler → application
# ---------------------------------------------------------------------------

mcp_client = VigilMcpClient()
executor = PostopSentinelExecutor(mcp=mcp_client)
task_store = InMemoryTaskStore()
request_handler = DefaultRequestHandler(
    agent_executor=executor,
    task_store=task_store,
)

app_builder = A2AFastAPIApplication(
    agent_card=agent_card,
    http_handler=request_handler,
)

app = app_builder.build(rpc_url="/a2a")

# Prompt Opinion ships gRPC-flavor JSON-RPC (PascalCase methods, ROLE_USER
# enums) on POST /a2a — normalise to spec form so the a2a-sdk handler
# dispatches correctly. Registered BEFORE the API-key middleware so that
# api-key (last added → outermost in Starlette's stack) runs first and
# rejects unauth'd requests cheaply, then PoCompat rewrites the body, then
# the SDK dispatches.
app.add_middleware(PoCompatMiddleware)

# SEC-05: API key enforcement — exempt AgentCard (public per A2A spec) (H1).
_A2A_SKIP_PREFIXES = ("/.well-known/agent-card.json", "/docs", "/openapi.json", "/redoc")
app.middleware("http")(build_api_key_middleware(skip_prefixes=_A2A_SKIP_PREFIXES))

warn_if_unset()

logger.info(
    "Vigil A2A agent configured",
    extra={
        "port": A2A_PORT,
        "poll_interval_sec": POLL_INTERVAL_SEC,
        "mcp_url": mcp_client._base_url,
    },
)

# ---------------------------------------------------------------------------
# POST /tick — run a sentinel cycle across every patient in HAPI
# ---------------------------------------------------------------------------


@app.post("/tick")
async def tick() -> dict[str, Any]:
    """Run one sentinel cycle across every seeded patient.

    Invoked by the proxy's ``POST /api/agent/tick`` (the "Tick Now" button
    in FE3) and by the internal poll loop.  Triggered alerts are written to
    the SQLite review queue via ``enqueue_alert``.
    """
    result = await run_cycle_for_all_patients(mcp_client, FHIR_BASE_URL)
    result["ts"] = datetime.now(UTC).isoformat()
    return result


# ---------------------------------------------------------------------------
# Background poll loop — B8
# ---------------------------------------------------------------------------

_poll_task: asyncio.Task[None] | None = None


async def _poll_loop(interval_sec: int) -> None:
    """Invoke the tick cycle every ``interval_sec`` seconds until cancelled."""
    logger.info(
        "sentinel poll loop started",
        extra={"interval_sec": interval_sec},
    )
    try:
        while True:
            await asyncio.sleep(interval_sec)
            try:
                summary = await run_cycle_for_all_patients(
                    mcp_client, FHIR_BASE_URL
                )
                logger.info(
                    "poll tick complete",
                    extra={
                        "patients_ticked": summary.get("patients_ticked"),
                        "alerts_generated": summary.get("alerts_generated"),
                    },
                )
            except Exception:  # noqa: BLE001 — keep the loop alive
                logger.exception("poll tick failed")
    except asyncio.CancelledError:
        logger.info("sentinel poll loop stopping")
        raise


@app.on_event("startup")
async def _start_poll_loop() -> None:
    global _poll_task
    if POLL_INTERVAL_SEC <= 0:
        logger.info("poll loop disabled (POLL_INTERVAL_SEC<=0)")
        return
    _poll_task = asyncio.create_task(_poll_loop(POLL_INTERVAL_SEC))


@app.on_event("shutdown")
async def _stop_poll_loop() -> None:
    global _poll_task
    if _poll_task is None:
        return
    _poll_task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await _poll_task
    _poll_task = None


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.a2a_agent.app:app",
        host="0.0.0.0",
        port=A2A_PORT,
        log_level="info",
    )
