"""Vigil FastAPI frontend proxy — binds to 127.0.0.1:8000.

Powers the Next.js dashboard with read routes + the approve endpoint.
The approve endpoint is the ONLY FHIR write path in the entire stack.

Security controls (see SECURITY_REVIEW.md):
  SEC-05: X-API-Key enforcement via VIGIL_API_KEY env var
  SEC-06: CORS restricted to CORS_ORIGINS env var, not wildcard
  SEC-19: binds to 127.0.0.1 only

Run:
    uv run uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import asyncio
import os
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.review_queue import init_db, list_pending_alerts
from backend.api.routes.patients import (
    approve_alert_action,
    get_latest_patient_alert_action,
    get_patient_detail_action,
    list_patients_action,
)
from backend.cache import get_cache_stats
from backend.fhir.client import FhirClientError
from backend.obs.logging import configure_logging, get_logger, set_request_id
from backend.obs.metrics import append_event, get_events_since, get_token_totals
from backend.schemas import ApproveRequest

# ---------------------------------------------------------------------------
# Environment configuration
# ---------------------------------------------------------------------------

FHIR_BASE_URL: str = os.environ.get("FHIR_BASE_URL", "http://localhost:8080/fhir")
LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "ollama")
CORS_ORIGINS: list[str] = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
VIGIL_API_KEY: str | None = os.environ.get("VIGIL_API_KEY")
A2A_AGENT_URL: str = os.environ.get("A2A_AGENT_URL", "http://localhost:9000")

configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Vigil Frontend Proxy",
    description=(
        "Aggregates HAPI FHIR data for the Next.js dashboard. "
        "The /approve endpoint is the only FHIR write path."
    ),
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# CORS — restricted origins, not wildcard (SEC-06)
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request ID propagation
# ---------------------------------------------------------------------------

_AUTH_SKIP_PREFIXES = ("/docs", "/openapi.json", "/redoc")


@app.middleware("http")
async def request_id_middleware(request: Request, call_next: Any) -> Response:
    rid = request.headers.get("X-Request-Id") or str(uuid.uuid4())[:8]
    set_request_id(rid)
    response = await call_next(request)
    response.headers["X-Request-Id"] = rid
    return response


# ---------------------------------------------------------------------------
# API Key enforcement (SEC-05)
# ---------------------------------------------------------------------------


@app.middleware("http")
async def api_key_middleware(request: Request, call_next: Any) -> Response:
    """Reject requests missing a valid X-API-Key when VIGIL_API_KEY is set.

    Dev mode: if VIGIL_API_KEY is unset, all requests are allowed through
    (a warning is logged at startup).  Never run without the key when
    a tunnel (ngrok / cloudflared) is open — SEC-05.
    """
    path = request.url.path
    if any(path.startswith(p) for p in _AUTH_SKIP_PREFIXES):
        return await call_next(request)

    if VIGIL_API_KEY:
        provided = request.headers.get("X-API-Key", "")
        if not secrets.compare_digest(provided, VIGIL_API_KEY):
            return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    return await call_next(request)


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    if not VIGIL_API_KEY:
        logger.warning(
            "VIGIL_API_KEY not configured — API key enforcement disabled. "
            "Set VIGIL_API_KEY before opening any tunnel (SEC-05)."
        )
    logger.info(
        "Vigil proxy started",
        extra={
            "_vigil_fhir_url": FHIR_BASE_URL,
            "_vigil_llm_provider": LLM_PROVIDER,
            "_vigil_cors": ",".join(CORS_ORIGINS),
        },
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "ts": datetime.now(UTC).isoformat()}


@app.get("/api/patients")
async def list_patients() -> dict[str, Any]:
    """List all monitored patients with status summary. API_CONTRACTS.md §6.1"""
    try:
        return await list_patients_action(fhir_base_url=FHIR_BASE_URL)
    except FhirClientError as exc:
        logger.error("list_patients FHIR error", extra={"_vigil_error": str(exc)})
        raise HTTPException(status_code=502, detail=f"FHIR error: {exc}") from exc


@app.get("/api/patients/{patient_id}")
async def get_patient(patient_id: str) -> dict[str, Any]:
    """Full dashboard payload for a patient. API_CONTRACTS.md §6.2"""
    try:
        return await get_patient_detail_action(
            patient_id=patient_id, fhir_base_url=FHIR_BASE_URL
        )
    except FhirClientError as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="Patient not found") from exc
        raise HTTPException(status_code=502, detail=f"FHIR error: {exc}") from exc


@app.get("/api/patients/{patient_id}/alerts/latest")
async def get_latest_alert(patient_id: str) -> dict[str, Any]:
    """Latest SBAR draft for a patient. API_CONTRACTS.md §6.3"""
    result = await get_latest_patient_alert_action(patient_id=patient_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No alert found for patient")
    return result


@app.post("/api/patients/{patient_id}/alerts/{alert_id}/approve")
async def approve_alert(
    patient_id: str,
    alert_id: str,
    body: ApproveRequest,
) -> Any:
    """Clinician approval — the ONLY FHIR write in the stack.

    Writes Communication (status=completed) + AuditEvent to HAPI.
    API_CONTRACTS.md §6.4.
    """
    from backend.api.review_queue import get_alert

    # Pre-flight checks
    alert = await asyncio.to_thread(get_alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    if alert.get("patient_id") != patient_id:
        raise HTTPException(status_code=404, detail="Alert not found for this patient")
    if alert.get("status") == "completed":
        raise HTTPException(status_code=409, detail="Alert already approved")

    try:
        return await approve_alert_action(
            patient_id=patient_id,
            alert_id=alert_id,
            body=body,
            fhir_base_url=FHIR_BASE_URL,
        )
    except FhirClientError as exc:
        logger.error("approve FHIR error", extra={"_vigil_error": str(exc)})
        raise HTTPException(status_code=502, detail=f"FHIR write failed: {exc}") from exc


@app.get("/api/alerts")
async def list_alerts() -> dict[str, Any]:
    """All in-progress alerts across all patients (for Alerts view FE4)."""
    alerts = await asyncio.to_thread(list_pending_alerts)
    return {"alerts": alerts}


# ---------------------------------------------------------------------------
# B9 — events tail endpoint (polling, not SSE)
# ---------------------------------------------------------------------------


@app.get("/api/events/tail")
async def events_tail(since: str | None = None) -> dict[str, Any]:
    """Return VigilEvents newer than *since* (ISO timestamp string).

    Frontend Timeline view (FE3) polls this at 2s intervals.
    Not SSE — simpler polling per BUILD_PLAN.md B9.

    Query param: since=<ISO8601 timestamp>
    Returns: { events: [...], server_ts: "..." }
    """
    events = await get_events_since(since)
    return {
        "events": events,
        "server_ts": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# POST /api/agent/tick — trigger immediate A2A polling cycle
# ---------------------------------------------------------------------------


@app.post("/api/agent/tick")
async def agent_tick() -> dict[str, Any]:
    """Trigger an immediate A2A agent polling cycle.

    Called by the frontend "Tick Now" button (FE3) and demo scripts.
    Makes a POST to the A2A agent's /tick endpoint. Returns 202-style
    response whether or not the agent is currently available.
    """
    tick_url = f"{A2A_AGENT_URL.rstrip('/')}/tick"
    success = False
    detail = "agent not reachable"
    # Full 10-patient cycle takes ~60-120s (4 MCP tool calls × 10 patients
    # + LLM per patient that fires). Give the agent room to finish.
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=5.0)) as client:
            headers: dict[str, str] = {}
            if VIGIL_API_KEY:
                headers["X-API-Key"] = VIGIL_API_KEY
            resp = await client.post(tick_url, headers=headers)
        success = resp.status_code < 300
        detail = resp.text[:200] if not success else "ok"
    except httpx.RequestError as exc:
        detail = str(exc)

    await append_event("agent_tick", {"success": success, "detail": detail})
    return {
        "triggered": success,
        "detail": detail,
        "ts": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# GET /api/status — LLM provider, FHIR URL, connection health
# ---------------------------------------------------------------------------


@app.get("/api/status")
async def get_status() -> dict[str, Any]:
    """Current LLM provider, FHIR URL, and connection health. FE6."""
    fhir_healthy = False
    fhir_error: str | None = None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{FHIR_BASE_URL}/metadata")
        fhir_healthy = r.status_code == 200
        if not fhir_healthy:
            fhir_error = f"HTTP {r.status_code}"
    except httpx.RequestError as exc:
        fhir_error = str(exc)

    agent_healthy = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(
                f"{A2A_AGENT_URL.rstrip('/')}/.well-known/agent-card.json"
            )
        agent_healthy = r.status_code == 200
    except httpx.RequestError:
        pass

    return {
        "llm_provider": LLM_PROVIDER,
        "fhir_url": FHIR_BASE_URL,
        "fhir_healthy": fhir_healthy,
        "fhir_error": fhir_error,
        "agent_healthy": agent_healthy,
        "a2a_agent_url": A2A_AGENT_URL,
        "token_usage": get_token_totals(),
        "cache": await get_cache_stats(),
        "ts": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------


@app.exception_handler(404)
async def not_found(_req: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "Not found", "detail": ""})


@app.exception_handler(500)
async def server_error(_req: Request, _exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server error")
    return JSONResponse(
        status_code=500, content={"error": "Internal server error", "detail": ""}
    )
