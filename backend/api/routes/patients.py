"""Patient business logic for the Vigil FastAPI frontend proxy.

These are pure async helper functions — NOT FastAPI route handlers.
FastAPI routes are defined in backend/api/main.py; they call into here.

All FHIR reads use FhirClient. The ONLY FHIR writes are in approve_alert_action,
which writes Communication (status=completed) + AuditEvent. See API_CONTRACTS.md §6.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from backend.api.review_queue import (
    approve_alert,
    claim_alert_for_writing,
    count_unread_alerts,
    get_alert,
    get_latest_alert,
    get_latest_alert_at,
    revert_alert_to_in_progress,
)
from backend.fhir.client import FhirClient, FhirClientError
from backend.obs.logging import get_logger
from backend.obs.metrics import append_event
from backend.schemas import ApproveRequest, ApproveResponse, FhirContext

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_fhir_context(fhir_base_url: str) -> FhirContext:
    """Construct FhirContext from the server-side FHIR URL (no user input)."""
    return FhirContext(url=fhir_base_url, token=None)


def _patient_display_name(patient: Any) -> str:
    if patient.name:
        n = patient.name[0]
        given = " ".join(n.given) if n.given else ""
        family = n.family or ""
        full = f"{family}, {given}".strip(", ")
        return full if full else (patient.id or "Unknown")
    return patient.id or "Unknown"


def _patient_age(birth_date: str | None) -> int | None:
    if not birth_date:
        return None
    try:
        bd = datetime.fromisoformat(birth_date)
        today = datetime.now(UTC)
        return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    except ValueError:
        return None


def _severity_to_risk_band(severity: str | None) -> str:
    return {"critical": "high", "urgent": "moderate", "info": "low"}.get(severity or "", "low")


def _mrn(patient: Any) -> str:
    for ident in patient.identifier:
        if ident.value:
            return ident.value
    return patient.id or ""


# ---------------------------------------------------------------------------
# list_patients
# ---------------------------------------------------------------------------


async def list_patients_action(fhir_base_url: str) -> dict[str, Any]:
    """Return all patients with status summary. API_CONTRACTS.md §6.1"""
    ctx = _make_fhir_context(fhir_base_url)
    async with FhirClient(ctx) as client:
        patients = await client.get_all_patients()

    rows = []
    for p in patients:
        pid = p.id or ""
        latest_alert = await asyncio.to_thread(get_latest_alert, pid)
        unread = await asyncio.to_thread(count_unread_alerts, pid)
        latest_at = await asyncio.to_thread(get_latest_alert_at, pid)
        severity = latest_alert.get("severity") if latest_alert else None
        rows.append(
            {
                "id": pid,
                "mrn": _mrn(p),
                "name": _patient_display_name(p),
                "age": _patient_age(p.birthDate),
                "trajectory": "postop",
                "latest_risk_band": _severity_to_risk_band(severity),
                "latest_alert_at": latest_at,
                "unread_alerts": unread,
            }
        )
    return {"patients": rows}


# ---------------------------------------------------------------------------
# get_patient_detail
# ---------------------------------------------------------------------------

VITAL_LABELS: dict[str, str] = {
    "8480-6": "SBP",
    "8462-4": "DBP",
    "8867-4": "HR",
    "9279-1": "RR",
    "59408-5": "SpO2",
    "8310-5": "Temp",
    "9192-6": "UO",
}


async def get_patient_detail_action(
    patient_id: str, fhir_base_url: str
) -> dict[str, Any]:
    """Full dashboard payload for patient detail page. API_CONTRACTS.md §6.2"""
    ctx = _make_fhir_context(fhir_base_url)
    async with FhirClient(ctx) as client:
        patient, encounter, observations, conditions = await asyncio.gather(
            client.get_patient(patient_id),
            client.get_encounter(patient_id),
            client.get_observations(patient_id, category="vital-signs", count=200),
            client.get_conditions(patient_id),
        )

    # Vitals time series: group observations by LOINC code
    series: dict[str, dict[str, Any]] = {}
    for obs in observations:
        loinc = obs.loinc_code
        if not loinc or loinc not in VITAL_LABELS:
            continue
        if obs.valueQuantity is None or obs.valueQuantity.value is None:
            continue
        if loinc not in series:
            series[loinc] = {
                "loinc": loinc,
                "label": VITAL_LABELS[loinc],
                "unit": obs.valueQuantity.unit or "",
                "points": [],
            }
        if obs.effectiveDateTime:
            series[loinc]["points"].append(
                {"t": obs.effectiveDateTime.isoformat(), "v": obs.valueQuantity.value}
            )

    # Comorbidities
    comorbidities = []
    for cond in conditions:
        if cond.code:
            for coding in cond.code.coding:
                if coding.code:
                    comorbidities.append(
                        {"code": coding.code, "display": coding.display or ""}
                    )

    # Latest risk from review queue
    latest_alert = await asyncio.to_thread(get_latest_alert, patient_id)
    risk: dict[str, Any] = {
        "qsofa_score": None,
        "composite_risk": None,
        "band": "low",
        "rationale": "No agent run yet.",
    }
    recent_alerts_list = []
    if latest_alert:
        risk["band"] = _severity_to_risk_band(latest_alert.get("severity"))
        recent_alerts_list = [
            {
                "id": latest_alert["id"],
                "severity": latest_alert.get("severity"),
                "sent": latest_alert.get("created_at"),
                "status": latest_alert.get("status"),
            }
        ]

    encounter_out: dict[str, Any] | None = None
    if encounter:
        encounter_out = {
            "id": encounter.id,
            "start": (
                encounter.period.start.isoformat()
                if encounter.period and encounter.period.start
                else None
            ),
            "status": encounter.status,
        }

    return {
        "patient": {
            "id": patient.id,
            "mrn": _mrn(patient),
            "name": _patient_display_name(patient),
            "age": _patient_age(patient.birthDate),
            "birth_date": patient.birthDate,
            "gender": patient.gender,
        },
        "encounter": encounter_out,
        "vitals_timeseries": list(series.values()),
        "comorbidities": comorbidities,
        "risk": risk,
        "recent_alerts": recent_alerts_list,
    }


# ---------------------------------------------------------------------------
# get_latest_patient_alert
# ---------------------------------------------------------------------------


async def get_latest_patient_alert_action(patient_id: str) -> dict[str, Any] | None:
    """Return the most recent SBAR draft for a patient. API_CONTRACTS.md §6.3"""
    alert = await asyncio.to_thread(get_latest_alert, patient_id)
    if not alert:
        return None
    return {
        "alert_id": alert["id"],
        "severity": alert.get("severity"),
        "sent": alert.get("created_at"),
        "recipient_role": alert.get("recipient_role"),
        "sbar": alert.get("sbar", {}),
        "narrative": alert.get("narrative", ""),
        "model_used": alert.get("model_used", ""),
        "status": alert.get("status"),
    }


# ---------------------------------------------------------------------------
# approve_alert_action  — THE ONLY FHIR WRITE IN THE STACK
# ---------------------------------------------------------------------------


async def approve_alert_action(
    patient_id: str,
    alert_id: str,
    body: ApproveRequest,
    fhir_base_url: str,
) -> ApproveResponse:
    """Clinician approval: writes Communication + AuditEvent to HAPI.

    API_CONTRACTS.md §6.4.

    HACKATHON NOTE (SEC-08): clinician_id is accepted on trust. Production
    deployment requires OIDC-based identity verification. See SEC-08 in
    SECURITY_REVIEW.md.
    """
    # Atomic claim: transition 'in-progress' → 'in-progress-writing'.
    # If another coroutine already claimed the row, rows_affected = 0 → None → 409.
    alert = await asyncio.to_thread(claim_alert_for_writing, alert_id)
    if alert is None:
        raise HTTPException(
            status_code=409,
            detail="Concurrent approve in progress or alert already approved",
        )

    ctx = _make_fhir_context(fhir_base_url)
    now = datetime.now(UTC)

    # Build Communication with status flipped to completed
    comm_draft: dict[str, Any] = dict(alert["communication_draft"])
    comm_draft["status"] = "completed"
    comm_draft["sent"] = now.isoformat()
    comm_draft.pop("id", None)  # HAPI assigns the id

    # POST Communication → HAPI; revert lock on failure so a retry can proceed
    try:
        async with FhirClient(ctx) as client:
            comm_response = await client.post_resource("Communication", comm_draft)
    except FhirClientError:
        await asyncio.to_thread(revert_alert_to_in_progress, alert_id)
        raise

    comm_id = comm_response.get("id", f"comm-{uuid.uuid4().hex[:8]}")

    # Build AuditEvent (API_CONTRACTS.md §5.7)
    audit_event: dict[str, Any] = {
        "resourceType": "AuditEvent",
        "type": {
            "system": "http://dicom.nema.org/resources/ontology/DCM",
            "code": "110100",
            "display": "Application Activity",
        },
        "subtype": [{"system": "http://vigil.local/audit", "code": "clinician.approve_alert"}],
        "action": "E",
        "recorded": now.isoformat(),
        "outcome": "0",
        "agent": [
            {
                "who": {"reference": f"Practitioner/{body.clinician_id}"},
                "requestor": True,
                "type": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/extra-security-role-type",
                            "code": "AGNT",
                        }
                    ]
                },
            }
        ],
        "source": {"observer": {"reference": "Device/vigil-postop-sentinel"}},
        "entity": [
            {
                "what": {"reference": f"Patient/{patient_id}"},
                "type": {
                    "system": "http://terminology.hl7.org/CodeSystem/audit-entity-type",
                    "code": "1",
                },
            },
            {
                "what": {"reference": f"Communication/{comm_id}"},
                "detail": [{"type": "clinician_note", "valueString": body.note}],
            },
        ],
    }

    # POST AuditEvent → HAPI (soft failure — don't roll back Communication)
    try:
        async with FhirClient(ctx) as client:
            audit_response = await client.post_resource("AuditEvent", audit_event)
        audit_id = audit_response.get("id", f"audit-{uuid.uuid4().hex[:8]}")
    except FhirClientError as exc:
        logger.error(
            "AuditEvent POST failed",
            extra={"_vigil_error": str(exc), "_vigil_comm_id": comm_id},
        )
        audit_id = f"audit-{uuid.uuid4().hex[:8]}-failed"

    # Update SQLite review queue
    await asyncio.to_thread(
        approve_alert, alert_id, body.clinician_id, body.note, audit_id
    )

    await append_event(
        "alert_approved",
        {"alert_id": alert_id, "comm_id": comm_id, "audit_id": audit_id},
        patient_id=patient_id,
    )
    logger.info(
        "alert approved",
        extra={
            "_vigil_alert_id": alert_id,
            "_vigil_comm_id": comm_id,
            "_vigil_audit_id": audit_id,
            "_vigil_patient_id": patient_id,
        },
    )

    return ApproveResponse(
        alert_id=alert_id,
        status="completed",
        acknowledged_at=now,
        audit_id=audit_id,
    )
