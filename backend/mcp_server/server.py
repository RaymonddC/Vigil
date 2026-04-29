"""Vigil MCP Server — FastMCP with streamable HTTP transport.

Single FastMCP server exposing 4 clinical tools for postop/postpartum
patient monitoring. Mounted inside a FastAPI app with CORS, health
endpoint, and structured JSON logging.

Reference: po-community-mcp/python/main.py, mcp_instance.py
           API_CONTRACTS.md §1–§2
           BUILD_PLAN.md B1
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from backend.mcp_server.context import get_sharp_context, resolve_patient_id
from backend.mcp_server.middleware import SharpHeaderMiddleware
from backend.mcp_server.tools import assess_postop_aki as _b_aki
from backend.mcp_server.tools import assess_pph_severity as _b_pph
from backend.mcp_server.tools import flag_sepsis_onset as _b4
from backend.mcp_server.tools import flag_treatment_conflicts as _b_tx
from backend.mcp_server.tools import generate_escalation_note as _b5
from backend.mcp_server.tools import score_deterioration_risk as _b3
from backend.mcp_server.tools import score_news2 as _b_news2
from backend.mcp_server.tools import screen_vital_thresholds as _b2
from backend.obs.logging import configure_logging, get_logger
from backend.security.api_key import build_api_key_middleware, warn_if_unset

# ---------------------------------------------------------------------------
# Logging — shared JSON formatter + bearer token filter (H3)
# ---------------------------------------------------------------------------

configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
logger = get_logger("vigil.mcp.server")

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
    """Run CDC ASE surveillance logic with SIRS fallback."""
    sharp = get_sharp_context(ctx)
    pid = resolve_patient_id(patient_id, sharp)
    logger.info("tool called", extra={"tool": "flag_sepsis_onset", "patient_id": pid})
    return await _b4.run(pid, evaluation_window_hours, sharp)


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
    """Generate SBAR escalation note via LLM from screening outputs."""
    sharp = get_sharp_context(ctx)
    pid = resolve_patient_id(patient_id, sharp)
    logger.info("tool called", extra={"tool": "generate_escalation_note", "patient_id": pid})
    return await _b5.run(
        pid, vitals_result, risk_result, sepsis_result, recipient_role, sharp,
    )


@mcp.tool(
    name="assess_postop_aki",
    description=(
        "KDIGO-staged AKI verdict (stages 0–3) using serial creatinine "
        "and 24h urine output. Imputes baseline creatinine as the lowest "
        "value in the past 7 days when no historical baseline is supplied "
        "(KDIGO 2012 §3.1.2) and surfaces the imputation explicitly. "
        "Layers an SCCM-2017 (Joannidis ICM 2017;43:730) time-to-"
        "intervention recommendation on top. Deterministic — no LLM."
    ),
)
async def assess_postop_aki(
    patient_id: Annotated[
        str | None,
        Field(
            default=None,
            description="FHIR Patient.id. Optional if SHARP header set.",
        ),
    ] = None,
    creatinine_baseline_override: Annotated[
        float | None,
        Field(
            default=None,
            ge=0.1,
            le=20.0,
            description=(
                "Override the imputed baseline with a clinician-supplied "
                "value (mg/dL). Skips imputation entirely."
            ),
        ),
    ] = None,
    ctx: Context | None = None,
) -> str:
    """KDIGO AKI staging via deterministic engine."""
    sharp = get_sharp_context(ctx)
    pid = resolve_patient_id(patient_id, sharp)
    logger.info(
        "tool called",
        extra={"tool": "assess_postop_aki", "patient_id": pid},
    )
    return await _b_aki.run(
        pid, sharp, creatinine_baseline_override=creatinine_baseline_override,
    )


@mcp.tool(
    name="score_news2",
    description=(
        "NEWS2 (Royal College of Physicians 2017) deterioration score — a "
        "second opinion to qSOFA. Returns aggregate 0–20, banded "
        "{low, low-medium, medium, high}, red_flag boolean (any single "
        "parameter scoring 3), and the per-parameter contribution table. "
        "Deterministic — no LLM."
    ),
)
async def score_news2(
    patient_id: Annotated[
        str | None,
        Field(
            default=None,
            description="FHIR Patient.id. Optional if SHARP header set.",
        ),
    ] = None,
    lookback_minutes: Annotated[
        int,
        Field(
            default=240,
            ge=15,
            le=1440,
            description="Minutes to scan vitals for the latest set.",
        ),
    ] = 240,
    ctx: Context | None = None,
) -> str:
    """NEWS2 score from the most recent vital set."""
    sharp = get_sharp_context(ctx)
    pid = resolve_patient_id(patient_id, sharp)
    logger.info(
        "tool called", extra={"tool": "score_news2", "patient_id": pid},
    )
    return await _b_news2.run(pid, lookback_minutes, sharp)


@mcp.tool(
    name="assess_pph_severity",
    description=(
        "CMQCC OB Hemorrhage Toolkit v3.0 staging for postpartum "
        "hemorrhage. Inputs: cumulative EBL (LOINC 55758-7), HR, SBP, "
        "fibrinogen, hemoglobin trend; optional uterotonic count. "
        "Returns stage 0–3, shock index, triggers, and the verbatim "
        "CMQCC action ladder (NOT LLM-generated). Falls back to shock-"
        "index-only with explicit caveat when EBL is unmeasured."
    ),
)
async def assess_pph_severity(
    patient_id: Annotated[
        str | None,
        Field(
            default=None,
            description="FHIR Patient.id. Optional if SHARP header set.",
        ),
    ] = None,
    delivery_route: Annotated[
        Literal["vaginal", "cesarean", "unknown"],
        Field(
            default="vaginal",
            description="Affects Stage-1 EBL cutoff (500 vs 1000 mL).",
        ),
    ] = "vaginal",
    uterotonics_given: Annotated[
        int,
        Field(
            default=0,
            ge=0,
            le=10,
            description=(
                "Bedside-supplied count of uterotonics administered. "
                "≥2 contributes to Stage 2."
            ),
        ),
    ] = 0,
    clinical_instability: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "Bedside flag for hemodynamic instability beyond "
                "absolute thresholds. Triggers Stage 3 escalation."
            ),
        ),
    ] = False,
    ctx: Context | None = None,
) -> str:
    """CMQCC v3.0 PPH staging."""
    sharp = get_sharp_context(ctx)
    pid = resolve_patient_id(patient_id, sharp)
    logger.info(
        "tool called",
        extra={"tool": "assess_pph_severity", "patient_id": pid},
    )
    return await _b_pph.run(
        pid, sharp,
        delivery_route=delivery_route,
        uterotonics_given=uterotonics_given,
        clinical_instability=clinical_instability,
    )


@mcp.tool(
    name="flag_treatment_conflicts",
    description=(
        "Physiology-aware drug safety scanner. Flags drug-vs-vitals/"
        "labs/conditions conflicts across 5 deterministic rules: "
        "(1) NSAID + AKI [KDIGO 2012, Beers 2023]; "
        "(2) β-blocker + bradycardia/hypotension [ACC/AHA 2017]; "
        "(3) ACE-I/ARB + hyperkalemia [KDIGO 2024 BP-in-CKD]; "
        "(4) opioid + respiratory depression [ASPMN 2020]; "
        "(5) anticoagulant + Hgb drop / bleeding [ASH 2018]. "
        "Cites guideline per rule; deterministic — no LLM."
    ),
)
async def flag_treatment_conflicts(
    patient_id: Annotated[
        str | None,
        Field(
            default=None,
            description="FHIR Patient.id. Optional if SHARP header set.",
        ),
    ] = None,
    lookback_hours: Annotated[
        int,
        Field(
            default=24,
            ge=1,
            le=72,
            description=(
                "How far back to scan vitals + medication "
                "administrations, in hours. Labs use a 7-day window "
                "regardless (needed for the Hgb-drop rule)."
            ),
        ),
    ] = 24,
    ctx: Context | None = None,
) -> str:
    """Scan for drug-vs-physiology conflicts via the deterministic engine."""
    sharp = get_sharp_context(ctx)
    pid = resolve_patient_id(patient_id, sharp)
    logger.info(
        "tool called",
        extra={"tool": "flag_treatment_conflicts", "patient_id": pid},
    )
    return await _b_tx.run(pid, sharp, lookback_hours=lookback_hours)


# ---------------------------------------------------------------------------
# FastAPI app wrapping the MCP server
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastMCP requires its session manager running for streamable HTTP."""
    warn_if_unset()
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
# SEC-06: CORS restricted to env-var origins. Default to localhost frontend in dev.
# Before opening any tunnel, set CORS_ORIGINS to the deployed frontend origin(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
# SEC-05: API key enforcement — outermost layer, runs before CORS + SHARP (H1).
_MCP_SKIP_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc")
app.middleware("http")(build_api_key_middleware(skip_prefixes=_MCP_SKIP_PREFIXES))


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
