"""Vigil MCP Server — FastMCP with streamable HTTP transport.

Single FastMCP server exposing 4 clinical tools for postop/postpartum
patient monitoring. Mounted inside a FastAPI app with CORS, health
endpoint, and structured JSON logging.

Reference: po-community-mcp/python/main.py, mcp_instance.py
           API_CONTRACTS.md §1–§2
           BUILD_PLAN.md B1
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from backend.mcp_server.context import get_sharp_context, resolve_patient_id
from backend.mcp_server.middleware import SharpHeaderMiddleware
from backend.mcp_server.tools import score_deterioration_risk as _b3
from backend.mcp_server.tools import screen_vital_thresholds as _b2

# ---------------------------------------------------------------------------
# Structured JSON logging
# ---------------------------------------------------------------------------


def _setup_logging() -> None:
    """Configure structured JSON logging for the MCP server."""
    import json as _json

    class JSONFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            log_data: dict[str, Any] = {
                "timestamp": self.formatTime(record, self.datefmt),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            # Merge extra fields
            for key in ("fhir_server_url", "fhir_access_token", "patient_id",
                        "tool", "duration_ms", "request_id", "error"):
                val = getattr(record, key, None)
                if val is not None:
                    log_data[key] = val
            if record.exc_info and record.exc_info[1]:
                log_data["exception"] = str(record.exc_info[1])
            return _json.dumps(log_data)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger("vigil")
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    root.addHandler(handler)
    root.propagate = False


_setup_logging()
logger = logging.getLogger("vigil.mcp.server")

# ---------------------------------------------------------------------------
# FastMCP instance + capability patch
# ---------------------------------------------------------------------------

MCP_PORT = int(os.environ.get("MCP_PORT", "7001"))

mcp = FastMCP(
    "Vigil Postop Sentinel",
    stateless_http=True,
    host="0.0.0.0",
    port=MCP_PORT,
)

# Monkey-patch get_capabilities to advertise the SHARP extension.
# Prompt Opinion's router inspects this to decide whether to inject FHIR headers.
# Reference: po-community-mcp/python/mcp_instance.py
_original_get_capabilities = mcp._mcp_server.get_capabilities


def _patched_get_capabilities(notification_options, experimental_capabilities):
    caps = _original_get_capabilities(notification_options, experimental_capabilities)
    caps.model_extra["extensions"] = {"ai.promptopinion/fhir-context": {}}
    return caps


mcp._mcp_server.get_capabilities = _patched_get_capabilities

# ---------------------------------------------------------------------------
# Tool stubs — tool-builder-1 and tool-builder-2 will fill these in
# ---------------------------------------------------------------------------


@mcp.tool(
    name="screen_vital_thresholds",
    description=(
        "Deterministically screens the most recent vital signs against MEWT "
        "(Modified Early Warning / Trigger) criteria and flags threshold breaches. "
        "No LLM involved — pure Python rules."
    ),
)
async def screen_vital_thresholds(
    patient_id: Annotated[
        str | None,
        Field(
            default=None,
            description="FHIR Patient.id. Optional if SHARP x-patient-id header is set.",
        ),
    ] = None,
    lookback_minutes: Annotated[
        int,
        Field(
            default=240,
            ge=15,
            le=1440,
            description="How far back to scan vitals, in minutes. Default 4 hours.",
        ),
    ] = 240,
    trajectory: Annotated[
        Literal["postop", "postpartum"],
        Field(
            default="postop",
            description="Selects which MEWT threshold table to use.",
        ),
    ] = "postop",
    ctx: Context | None = None,
) -> str:
    """Screen vital signs against MEWT thresholds and flag breaches."""
    sharp = get_sharp_context(ctx)
    pid = resolve_patient_id(patient_id, sharp)
    logger.info("tool called", extra={"tool": "screen_vital_thresholds", "patient_id": pid})
    return await _b2.run(pid, lookback_minutes, trajectory, sharp)


@mcp.tool(
    name="score_deterioration_risk",
    description=(
        "Computes a qSOFA score plus a lightweight composite trend score over "
        "the last N hours to estimate short-horizon deterioration probability."
    ),
)
async def score_deterioration_risk(
    patient_id: Annotated[
        str | None,
        Field(
            default=None,
            description="FHIR Patient.id. Optional if SHARP header set.",
        ),
    ] = None,
    window_hours: Annotated[
        int,
        Field(
            default=6,
            ge=1,
            le=48,
            description="Trend window for slope computation, in hours.",
        ),
    ] = 6,
    trajectory: Annotated[
        Literal["postop", "postpartum"],
        Field(
            default="postop",
            description="Selects comorbidity weighting profile.",
        ),
    ] = "postop",
    ctx: Context | None = None,
) -> str:
    """Compute qSOFA + composite trend score for deterioration risk."""
    sharp = get_sharp_context(ctx)
    pid = resolve_patient_id(patient_id, sharp)
    logger.info("tool called", extra={"tool": "score_deterioration_risk", "patient_id": pid})
    return await _b3.run(pid, window_hours, trajectory, sharp)


@mcp.tool(
    name="flag_sepsis_onset",
    description=(
        "Runs CDC Adult Sepsis Event surveillance logic against labs + vitals + "
        "antibiotic administration to flag likely sepsis onset. Deterministic — no LLM."
    ),
)
async def flag_sepsis_onset(
    patient_id: Annotated[
        str | None,
        Field(
            default=None,
            description="FHIR Patient.id. Optional if SHARP header set.",
        ),
    ] = None,
    evaluation_window_hours: Annotated[
        int,
        Field(
            default=24,
            ge=1,
            le=72,
            description="How far back to scan for onset evidence.",
        ),
    ] = 24,
    ctx: Context | None = None,
) -> str:
    """Stub — will be implemented by tool-builder."""
    sharp = get_sharp_context(ctx)
    pid = resolve_patient_id(patient_id, sharp)
    logger.info("tool called", extra={"tool": "flag_sepsis_onset", "patient_id": pid})
    return json.dumps({
        "status": "ok", "patient_id": pid,
        "sepsis_suspected": False, "mode": "cdc_ase",
        "criteria_met": [], "onset_estimate": None, "evidence": {},
    })


@mcp.tool(
    name="generate_escalation_note",
    description=(
        "Produces a clinician-ready SBAR escalation note from the outputs of the "
        "three rule tools. Uses the LLM via the provider abstraction. "
        "Returns an unpersisted FHIR Communication draft — never writes to FHIR."
    ),
)
async def generate_escalation_note(
    vitals_result: Annotated[
        dict[str, Any],
        Field(description="Raw JSON from screen_vital_thresholds."),
    ],
    risk_result: Annotated[
        dict[str, Any],
        Field(description="Raw JSON from score_deterioration_risk."),
    ],
    sepsis_result: Annotated[
        dict[str, Any],
        Field(description="Raw JSON from flag_sepsis_onset."),
    ],
    patient_id: Annotated[
        str | None,
        Field(
            default=None,
            description="FHIR Patient.id. Optional if SHARP header set.",
        ),
    ] = None,
    recipient_role: Annotated[
        Literal["charge_nurse", "resident", "attending", "rapid_response"],
        Field(
            default="charge_nurse",
            description="Drives tone and urgency.",
        ),
    ] = "charge_nurse",
    ctx: Context | None = None,
) -> str:
    """Stub — will be implemented by tool-builder."""
    sharp = get_sharp_context(ctx)
    pid = resolve_patient_id(patient_id, sharp)
    logger.info("tool called", extra={"tool": "generate_escalation_note", "patient_id": pid})
    return json.dumps({
        "status": "ok", "patient_id": pid,
        "sbar": {
            "situation": "stub", "background": "stub",
            "assessment": "stub", "recommendation": "stub",
        },
        "narrative": "S: stub B: stub A: stub R: stub",
        "severity": "info", "recipient_role": recipient_role,
        "communication_draft": {},
        "generated_at": "2026-01-01T00:00:00Z",
        "model_used": "stub/template",
    })


# ---------------------------------------------------------------------------
# FastAPI app wrapping the MCP server
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastMCP requires its session manager running for streamable HTTP."""
    logger.info("Vigil MCP server starting", extra={"port": MCP_PORT})
    async with mcp.session_manager.run():
        logger.info("MCP session manager ready")
        yield
    logger.info("Vigil MCP server shutting down gracefully")


app = FastAPI(
    title="Vigil MCP Server",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(SharpHeaderMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({"status": "ok", "service": "vigil-mcp-server"})


# Mount MCP at root — matches po-community-mcp pattern.
# The MCP endpoint handles GET/POST at /mcp (streamable HTTP).
app.mount("/", mcp.streamable_http_app())

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.mcp_server.server:app",
        host="0.0.0.0",
        port=MCP_PORT,
        log_level="info",
    )
