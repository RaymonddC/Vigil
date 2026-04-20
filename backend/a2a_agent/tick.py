"""Reusable sentinel-cycle runner shared by the A2A executor and the HTTP
`/tick` endpoint.

The executor in ``sentinel.py`` runs one full state-machine cycle for a
single patient driven by an incoming A2A message.  The demo "Tick Now"
button and the optional polling loop both need to run that same cycle
across every seeded patient without assembling a synthetic A2A
``RequestContext``, so the core decision logic lives here.

Reference: BUILD_PLAN.md B8, docs/REVIEW_PLAN_VS_CODE.md C2.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.a2a_agent.mcp_client import McpClientError, VigilMcpClient
from backend.a2a_agent.sentinel import _unwrap_tool_result
from backend.api.review_queue import enqueue_alert
from backend.fhir.client import FhirClient, FhirClientError
from backend.obs.metrics import append_event
from backend.schemas import FhirContext

logger = logging.getLogger("vigil.a2a.tick")


def _sharp_headers(fhir_url: str, patient_id: str) -> dict[str, str]:
    return {
        "x-fhir-server-url": fhir_url,
        "x-patient-id": patient_id,
    }


async def run_cycle_for_patient(
    mcp: VigilMcpClient,
    patient_id: str,
    fhir_url: str,
) -> dict[str, Any]:
    """Run one screening cycle for a single patient.

    Returns ``{triggered, alert_id, severity}``.  On any MCP error, returns
    ``{triggered: False, error: "..."}``.
    """
    sharp = _sharp_headers(fhir_url, patient_id)
    try:
        screen_raw = await mcp.call_tool(
            "screen_vital_thresholds",
            arguments={"patient_id": patient_id},
            sharp_headers=sharp,
        )
        risk_raw = await mcp.call_tool(
            "score_deterioration_risk",
            arguments={"patient_id": patient_id},
            sharp_headers=sharp,
        )
        sepsis_raw = await mcp.call_tool(
            "flag_sepsis_onset",
            arguments={"patient_id": patient_id},
            sharp_headers=sharp,
        )
    except McpClientError as exc:
        logger.error(
            "tick cycle mcp error",
            extra={"patient_id": patient_id, "error": str(exc)},
        )
        return {"triggered": False, "error": str(exc), "patient_id": patient_id}

    screen = _unwrap_tool_result(screen_raw)
    risk = _unwrap_tool_result(risk_raw)
    sepsis = _unwrap_tool_result(sepsis_raw)

    screen_triggered = screen.get("status") == "triggered"
    sepsis_triggered = sepsis.get("sepsis_suspected") is True
    risk_high = risk.get("risk_band") in ("moderate", "high")

    if not (screen_triggered or sepsis_triggered or risk_high):
        return {"triggered": False, "patient_id": patient_id}

    try:
        escalation_raw = await mcp.call_tool(
            "generate_escalation_note",
            arguments={
                "patient_id": patient_id,
                "vitals_result": screen,
                "risk_result": risk,
                "sepsis_result": sepsis,
                "recipient_role": (
                    "rapid_response" if sepsis_triggered else "charge_nurse"
                ),
            },
            sharp_headers=sharp,
        )
    except McpClientError as exc:
        logger.error(
            "escalation mcp error",
            extra={"patient_id": patient_id, "error": str(exc)},
        )
        return {"triggered": False, "error": str(exc), "patient_id": patient_id}

    escalation = _unwrap_tool_result(escalation_raw)
    severity = escalation.get("severity") or "info"
    narrative = escalation.get("narrative") or ""
    sbar = escalation.get("sbar") or {}
    communication_draft = escalation.get("communication_draft") or {}
    model_used = escalation.get("model_used") or "unknown"
    recipient = escalation.get("recipient_role") or (
        "rapid_response" if sepsis_triggered else "charge_nurse"
    )

    alert_id = await asyncio.to_thread(
        enqueue_alert,
        patient_id,
        severity,
        sbar,
        narrative,
        recipient,
        model_used,
        communication_draft,
    )

    logger.info(
        "tick enqueued alert",
        extra={
            "patient_id": patient_id,
            "alert_id": alert_id,
            "severity": severity,
        },
    )

    await append_event(
        "alert_drafted",
        {"alert_id": alert_id, "severity": severity},
        patient_id=patient_id,
    )

    return {
        "triggered": True,
        "patient_id": patient_id,
        "alert_id": alert_id,
        "severity": severity,
    }


async def _list_patient_ids(fhir_url: str) -> list[str]:
    """List patient IDs in HAPI.  Returns an empty list on FHIR failure."""
    try:
        async with FhirClient(FhirContext(url=fhir_url, token=None)) as client:
            patients = await client.get_all_patients()
        return [p.id for p in patients if p.id]
    except FhirClientError as exc:
        logger.error("tick: list patients failed", extra={"error": str(exc)})
        return []


async def run_cycle_for_all_patients(
    mcp: VigilMcpClient,
    fhir_url: str,
) -> dict[str, Any]:
    """Run one cycle for every patient in HAPI.  Sequential — small N (10)."""
    patient_ids = await _list_patient_ids(fhir_url)
    alerts_generated = 0
    per_patient: list[dict[str, Any]] = []
    for pid in patient_ids:
        result = await run_cycle_for_patient(mcp, pid, fhir_url)
        per_patient.append(result)
        if result.get("triggered"):
            alerts_generated += 1

    return {
        "triggered": True,
        "patients_ticked": len(patient_ids),
        "alerts_generated": alerts_generated,
        "per_patient": per_patient,
    }
