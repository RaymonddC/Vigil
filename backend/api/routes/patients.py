"""Patient business logic for the Vigil FastAPI frontend proxy.

These are pure async helper functions — NOT FastAPI route handlers.
FastAPI routes are defined in backend/api/main.py; they call into here.

All FHIR reads use FhirClient. The ONLY FHIR writes are in approve_alert_action,
which writes Communication (status=completed) + AuditEvent. See API_CONTRACTS.md §6.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.api.review_queue import (
    approve_alert,
    claim_alert_for_writing,
    count_unread_alerts,
    get_latest_alert,
    get_latest_alert_at,
    revert_alert_to_in_progress,
)
from backend.fhir.client import FhirClient, FhirClientError
from backend.obs.logging import get_logger
from backend.obs.metrics import append_event
from backend.schemas import ApproveRequest, ApproveResponse, FhirContext

logger = get_logger(__name__)


# Vigil agent identity — version + AgentCard hash carried into every
# FHIR write so AI authorship is verifiable for hospital procurement
# and FDA SaMD review. Computed once at import time; the AgentCard
# JSON is part of the deployed image so the hash is stable per build.
_AGENT_CARD_PATH = (
    Path(__file__).resolve().parents[2] / "a2a_agent" / "agent_card.json"
)
try:
    _agent_card_bytes = _AGENT_CARD_PATH.read_bytes()
    _VIGIL_AGENT_CARD_HASH = hashlib.sha256(_agent_card_bytes).hexdigest()
    _VIGIL_VERSION = json.loads(_agent_card_bytes).get("version", "0.0.0")
except (OSError, ValueError):
    # Image without the AgentCard (test fixture, partial build) — fall
    # back to known-bad markers so this surfaces if it ever ships.
    _VIGIL_AGENT_CARD_HASH = "0" * 64
    _VIGIL_VERSION = "0.0.0-unknown"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_fhir_context(
    fhir_base_url: str, token: str | None = None
) -> FhirContext:
    """Construct FhirContext from the server-side FHIR URL.

    ``token`` is forwarded as ``Authorization: Bearer …`` by ``FhirClient`` and
    is only set when the request is overridden to a non-HAPI source (resolved
    upstream by ``backend.api.main.resolve_fhir_source``). Default callers pass
    no token (HAPI mode).
    """
    return FhirContext(url=fhir_base_url, token=token)


# Display labels for the 4 recipient roles the SBAR can target.
_PRACTITIONER_ROLE_DISPLAY = {
    "charge_nurse":   "Charge Nurse",
    "resident":       "Resident on call",
    "attending":      "Attending physician",
    "rapid_response": "Rapid Response Team",
}


async def _ensure_vigil_referenced_resources(
    client: FhirClient, communication: dict[str, Any]
) -> None:
    """Idempotently PUT every resource the Communication references.

    HAPI enforces referential integrity by default — Communication.sender,
    Communication.recipient[*], and the AuditEvent.source.observer all need
    their target resources to exist or the POST fails with HAPI-1094.

    This helper PUTs the Vigil Device once and any PractitionerRole referenced
    in Communication.recipient. Patient and Encounter come from synthetic seed
    so they always exist. Same ids every call → safe to invoke per request.
    """
    # Vigil agent Device — referenced by sender + AuditEvent.source.observer.
    # Beefed up with US Core profile, software-version, and a content
    # hash so AI-authored writes carry verifiable provenance for hospital
    # procurement and FDA SaMD review (real deployment posture).
    await client.put_resource(
        "Device",
        "vigil-postop-sentinel",
        {
            "meta": {
                "profile": [
                    "http://hl7.org/fhir/us/core/StructureDefinition/us-core-implantable-device"
                ],
            },
            "identifier": [
                {
                    "system": "http://vigil.local/agent-id",
                    "value": "vigil-postop-sentinel",
                }
            ],
            "deviceName": [
                {"name": "Vigil Postop & Postpartum Sentinel", "type": "user-friendly-name"}
            ],
            "manufacturer": "Vigil (Agents Assemble 2026)",
            "modelNumber": _VIGIL_VERSION,
            "version": [
                {
                    "type": {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/device-version-type",
                                "code": "software",
                            }
                        ]
                    },
                    "value": _VIGIL_VERSION,
                }
            ],
            "property": [
                {
                    "type": {
                        "coding": [
                            {
                                "system": "http://vigil.local/device-property",
                                "code": "agent-card-hash",
                                "display": "AgentCard SHA-256",
                            }
                        ]
                    },
                    "valueCode": [{"code": _VIGIL_AGENT_CARD_HASH[:16]}],
                },
                {
                    "type": {
                        "coding": [
                            {
                                "system": "http://vigil.local/device-property",
                                "code": "deterministic-rule-pack",
                                "display": "Deterministic rule pack version",
                            }
                        ]
                    },
                    "valueCode": [
                        {
                            "code": (
                                "MEWS-2001 / qSOFA-2016 / NEWS2-2017 / "
                                "KDIGO-2012 / CMQCC-3.0 / CDC-ASE"
                            )
                        }
                    ],
                },
            ],
            "type": {
                "coding": [
                    {
                        "system": "http://snomed.info/sct",
                        "code": "706689003",
                        "display": "Application program software",
                    }
                ]
            },
        },
    )

    # PractitionerRole(s) referenced in Communication.recipient.
    # HAPI-0521: FHIR logical IDs allow letters, digits, '-', '.' only (no
    # underscores). Draft-side references like "PractitionerRole/charge_nurse"
    # — leftover from older drafts or any other emitter — get normalized to
    # "charge-nurse" here in-place so the POST Communication won't bounce.
    for ref in communication.get("recipient", []) or []:
        if not isinstance(ref, dict):
            continue
        target = ref.get("reference") or ""
        if not target.startswith("PractitionerRole/"):
            continue
        raw_id = target.split("/", 1)[1]
        role_id = raw_id.replace("_", "-")
        if role_id != raw_id:
            ref["reference"] = f"PractitionerRole/{role_id}"
        display_key = raw_id  # enum lookup still uses the snake-case variant
        await client.put_resource(
            "PractitionerRole",
            role_id,
            {
                "active": True,
                "code": [
                    {
                        "coding": [
                            {
                                "system": "http://vigil.local/practitioner-role",
                                "code": display_key,
                                "display": _PRACTITIONER_ROLE_DISPLAY.get(
                                    display_key, role_id.replace("-", " ").title()
                                ),
                            }
                        ]
                    }
                ],
            },
        )


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


# Obstetric SNOMED codes that mark a patient as postpartum.
# Cesarean section (11466000), normal delivery (3950001),
# pre-eclampsia (398254007), chorioamnionitis (11612004),
# placenta accreta (58532003), previous cesarean (200737006).
_POSTPARTUM_SNOMED: frozenset[str] = frozenset(
    {
        "11466000",
        "3950001",
        "398254007",
        "11612004",
        "58532003",
        "200737006",
    }
)


def _derive_trajectory(conditions: list[Any]) -> str:
    """Return ``postpartum`` if any condition carries an obstetric code,
    otherwise ``postop``. Per FRONTEND_SPEC §3.1 and PROJECT_BRIEF §2.
    """
    for cond in conditions:
        if not cond.code:
            continue
        for coding in cond.code.coding:
            if coding.code and coding.code in _POSTPARTUM_SNOMED:
                return "postpartum"
    return "postop"


# ---------------------------------------------------------------------------
# list_patients
# ---------------------------------------------------------------------------


async def list_patients_action(
    fhir_base_url: str, fhir_token: str | None = None
) -> dict[str, Any]:
    """Return all patients with status summary. API_CONTRACTS.md §6.1"""
    ctx = _make_fhir_context(fhir_base_url, token=fhir_token)
    async with FhirClient(ctx) as client:
        patients = await client.get_all_patients()
        condition_lists = await asyncio.gather(
            *(client.get_conditions(p.id or "") for p in patients),
            return_exceptions=True,
        )

    rows = []
    for p, conds in zip(patients, condition_lists, strict=True):
        pid = p.id or ""
        latest_alert = await asyncio.to_thread(get_latest_alert, pid)
        unread = await asyncio.to_thread(count_unread_alerts, pid)
        latest_at = await asyncio.to_thread(get_latest_alert_at, pid)
        severity = latest_alert.get("severity") if latest_alert else None
        trajectory = (
            _derive_trajectory(conds) if isinstance(conds, list) else "postop"
        )
        rows.append(
            {
                "id": pid,
                "mrn": _mrn(p),
                "name": _patient_display_name(p),
                "age": _patient_age(p.birthDate),
                "trajectory": trajectory,
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
    patient_id: str, fhir_base_url: str, fhir_token: str | None = None
) -> dict[str, Any]:
    """Full dashboard payload for patient detail page. API_CONTRACTS.md §6.2"""
    ctx = _make_fhir_context(fhir_base_url, token=fhir_token)
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
            "trajectory": _derive_trajectory(conditions),
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
    fhir_token: str | None = None,
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

    ctx = _make_fhir_context(fhir_base_url, token=fhir_token)
    now = datetime.now(UTC)

    # Build Communication with status flipped to completed. Stamp
    # meta.profile so HAPI / downstream validators recognise this as
    # a US Core Communication (rather than a free-form one).
    comm_draft: dict[str, Any] = dict(alert["communication_draft"])
    comm_draft["status"] = "completed"
    comm_draft["sent"] = now.isoformat()
    comm_draft.pop("id", None)  # HAPI assigns the id
    comm_meta = dict(comm_draft.get("meta") or {})
    comm_meta.setdefault("profile", []).append(
        "http://hl7.org/fhir/us/core/StructureDefinition/us-core-communication"
    )
    # Dedupe — repeat approve calls would otherwise stack the URL.
    comm_meta["profile"] = list(dict.fromkeys(comm_meta["profile"]))
    comm_draft["meta"] = comm_meta

    # POST Communication → HAPI; revert lock on failure so a retry can proceed
    try:
        async with FhirClient(ctx) as client:
            # Ensure HAPI referential integrity: Communication.sender,
            # Communication.recipient, and AuditEvent.source.observer all
            # reference resources HAPI rejects with HAPI-1094 if missing.
            # Idempotent PUTs — same id every call, safe per request.
            await _ensure_vigil_referenced_resources(client, comm_draft)
            comm_response = await client.post_resource("Communication", comm_draft)
    except FhirClientError:
        await asyncio.to_thread(revert_alert_to_in_progress, alert_id)
        raise

    comm_id = comm_response.get("id", f"comm-{uuid.uuid4().hex[:8]}")

    # Provenance — FHIR R4 attestation that the Communication was
    # AI-authored (Vigil agent) and clinician-approved. Tells any
    # downstream EHR consumer the provenance chain explicitly. Hash
    # of the AgentCard is stamped via signature.data so a regulator
    # can audit which model version produced this alert.
    provenance: dict[str, Any] = {
        "resourceType": "Provenance",
        "meta": {
            "profile": [
                "http://hl7.org/fhir/us/core/StructureDefinition/us-core-provenance"
            ]
        },
        "target": [{"reference": f"Communication/{comm_id}"}],
        "recorded": now.isoformat(),
        "occurredDateTime": now.isoformat(),
        "agent": [
            {
                "type": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
                            "code": "author",
                            "display": "Author",
                        }
                    ]
                },
                "who": {"reference": "Device/vigil-postop-sentinel"},
                "onBehalfOf": {"reference": f"Practitioner/{body.clinician_id}"},
            },
            {
                "type": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
                            "code": "verifier",
                            "display": "Verifier",
                        }
                    ]
                },
                "who": {"reference": f"Practitioner/{body.clinician_id}"},
            },
        ],
        "signature": [
            {
                "type": [
                    {
                        "system": "urn:iso-astm:E1762-95:2013",
                        "code": "1.2.840.10065.1.12.1.1",
                        "display": "Author's Signature",
                    }
                ],
                "when": now.isoformat(),
                "who": {"reference": "Device/vigil-postop-sentinel"},
                "targetFormat": "application/fhir+json",
                "sigFormat": "application/x-vigil-agent-card-sha256",
                "data": _VIGIL_AGENT_CARD_HASH,
            }
        ],
    }

    # POST Provenance — soft failure (don't roll back Communication).
    # The Communication itself is the regulatory artifact; Provenance
    # is enrichment for hospital procurement / audit pipelines.
    try:
        async with FhirClient(ctx) as client:
            await client.post_resource("Provenance", provenance)
    except FhirClientError as exc:
        logger.warning(
            "Provenance POST failed (non-fatal)",
            extra={"_vigil_error": str(exc), "_vigil_comm_id": comm_id},
        )

    # Build AuditEvent (API_CONTRACTS.md §5.7). meta.profile stamps
    # the FHIR R4 AuditEvent profile so downstream audit pipelines
    # recognise it as a standard event, not a custom one.
    audit_event: dict[str, Any] = {
        "resourceType": "AuditEvent",
        "meta": {
            "profile": [
                "http://hl7.org/fhir/StructureDefinition/AuditEvent"
            ]
        },
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
