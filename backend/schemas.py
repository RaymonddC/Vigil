"""Vigil API contract models — pydantic v2.

Single source of truth for every I/O shape crossing a component boundary.
All models reference their governing section in docs/API_CONTRACTS.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------


class ToolStatus(StrEnum):
    """Discriminator returned in the ``status`` field of every tool output.

    API_CONTRACTS.md §1 — Common error envelope.
    """

    OK = "ok"
    TRIGGERED = "triggered"
    BAD_INPUT = "bad_input"
    FHIR_UNAVAILABLE = "fhir_error"
    FHIR_NOT_FOUND = "fhir_not_found"
    LLM_UNAVAILABLE = "llm_error"


class AgentState(StrEnum):
    """A2A Postop Sentinel state-machine states.

    API_CONTRACTS.md §3 / BUILD_PLAN.md B7.
    """

    IDLE = "IDLE"
    POLLING = "POLLING"
    SCREENING = "SCREENING"
    RISK_SCORING = "RISK_SCORING"
    SEPSIS_CHECK = "SEPSIS_CHECK"
    ESCALATING = "ESCALATING"
    AWAITING_REVIEW = "AWAITING_REVIEW"


# ---------------------------------------------------------------------------
# Common error model
# ---------------------------------------------------------------------------


class ToolError(BaseModel):
    """Structured error payload shared by all tools.

    API_CONTRACTS.md §1 — Common error envelope.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "status": "fhir_error",
                    "message": "HAPI FHIR server unreachable",
                    "detail": {"http_status": 503},
                }
            ]
        },
    )

    status: ToolStatus
    message: str
    detail: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# SHARP / FHIR context
# ---------------------------------------------------------------------------


@dataclass
class FhirContext:
    """FHIR connection context extracted from SHARP headers.

    API_CONTRACTS.md §2.  Three HTTP headers (``x-fhir-server-url``,
    ``x-fhir-access-token``, ``x-patient-id``) are decoded into this
    dataclass inside the FastMCP tool handler.
    """

    url: str
    token: str | None = None
    patient_id: str | None = None


# ---------------------------------------------------------------------------
# 1.1  screen_vital_thresholds
# ---------------------------------------------------------------------------


class ScreenVitalsInput(BaseModel):
    """Input for ``screen_vital_thresholds``.

    API_CONTRACTS.md §1.1.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "patient_id": "patient-42",
                    "lookback_minutes": 240,
                    "trajectory": "postop",
                }
            ]
        },
    )

    patient_id: Annotated[
        str | None,
        Field(
            default=None,
            description="FHIR Patient.id. Optional if SHARP x-patient-id header is set.",
        ),
    ] = None
    lookback_minutes: Annotated[
        int,
        Field(
            default=240,
            ge=15,
            le=1440,
            description="How far back to scan vitals, in minutes. Default 4 hours.",
        ),
    ] = 240
    trajectory: Annotated[
        Literal["postop", "postpartum"],
        Field(
            default="postop",
            description="Selects which MEWT threshold table to use.",
        ),
    ] = "postop"


class VitalBreach(BaseModel):
    """One vital that violated a MEWT threshold.

    API_CONTRACTS.md §1.1 — nested inside ``ScreenVitalsOutput.breaches``.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "loinc": "8480-6",
                    "label": "SBP",
                    "value": 86.0,
                    "unit": "mm[Hg]",
                    "threshold": "<90",
                    "severity": "red",
                    "observed_at": "2026-04-15T11:48:00Z",
                }
            ]
        },
    )

    loinc: str
    label: str
    value: float
    unit: str
    threshold: str
    severity: Literal["yellow", "red"]
    observed_at: datetime


class ScreenVitalsOutput(BaseModel):
    """Output for ``screen_vital_thresholds``.

    API_CONTRACTS.md §1.1.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "patient_id": "patient-42",
                    "trajectory": "postop",
                    "breaches": [],
                    "scanned_count": 18,
                    "window_start": "2026-04-15T08:00:00Z",
                    "window_end": "2026-04-15T12:00:00Z",
                },
                {
                    "status": "triggered",
                    "patient_id": "patient-42",
                    "trajectory": "postop",
                    "breaches": [
                        {
                            "loinc": "8480-6",
                            "label": "SBP",
                            "value": 86.0,
                            "unit": "mm[Hg]",
                            "threshold": "<90",
                            "severity": "red",
                            "observed_at": "2026-04-15T11:48:00Z",
                        },
                        {
                            "loinc": "8867-4",
                            "label": "HR",
                            "value": 126.0,
                            "unit": "/min",
                            "threshold": ">=120",
                            "severity": "yellow",
                            "observed_at": "2026-04-15T11:48:00Z",
                        },
                    ],
                    "scanned_count": 18,
                    "window_start": "2026-04-15T08:00:00Z",
                    "window_end": "2026-04-15T12:00:00Z",
                },
            ]
        },
    )

    status: ToolStatus
    patient_id: str
    trajectory: str
    breaches: list[VitalBreach]
    scanned_count: int
    window_start: datetime
    window_end: datetime


# ---------------------------------------------------------------------------
# 1.2  score_deterioration_risk
# ---------------------------------------------------------------------------


class ScoreRiskInput(BaseModel):
    """Input for ``score_deterioration_risk``.

    API_CONTRACTS.md §1.2.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "patient_id": "patient-42",
                    "window_hours": 6,
                    "trajectory": "postop",
                }
            ]
        },
    )

    patient_id: Annotated[
        str | None,
        Field(
            default=None,
            description="FHIR Patient.id. Optional if SHARP header set.",
        ),
    ] = None
    window_hours: Annotated[
        int,
        Field(
            default=6,
            ge=1,
            le=48,
            description="Trend window for slope computation, in hours.",
        ),
    ] = 6
    trajectory: Annotated[
        Literal["postop", "postpartum"],
        Field(
            default="postop",
            description="Selects comorbidity weighting profile.",
        ),
    ] = "postop"


class RiskScoreOutput(BaseModel):
    """Output for ``score_deterioration_risk``.

    API_CONTRACTS.md §1.2.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "patient_id": "patient-42",
                    "qsofa_score": 0,
                    "qsofa_components": {
                        "rr_ge_22": False,
                        "sbp_le_100": False,
                        "altered_mental": False,
                    },
                    "composite_risk": 0.12,
                    "risk_band": "low",
                    "rationale": "qSOFA=0; SBP stable; HR stable; no trend breach.",
                    "contributing_conditions": [],
                },
                {
                    "status": "triggered",
                    "patient_id": "patient-42",
                    "qsofa_score": 2,
                    "qsofa_components": {
                        "rr_ge_22": True,
                        "sbp_le_100": True,
                        "altered_mental": False,
                    },
                    "composite_risk": 0.71,
                    "risk_band": "high",
                    "rationale": "qSOFA=2 meets sepsis screen; SBP trending down 18 mmHg over 4h.",
                    "contributing_conditions": ["44054006 Type 2 diabetes"],
                },
            ]
        },
    )

    status: ToolStatus
    patient_id: str
    qsofa_score: int = Field(ge=0, le=3)
    qsofa_components: dict[str, bool]
    composite_risk: float = Field(ge=0.0, le=1.0)
    risk_band: Literal["low", "moderate", "high"]
    rationale: str
    contributing_conditions: list[str]


# ---------------------------------------------------------------------------
# 1.3  flag_sepsis_onset
# ---------------------------------------------------------------------------


class FlagSepsisInput(BaseModel):
    """Input for ``flag_sepsis_onset``.

    API_CONTRACTS.md §1.3.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "patient_id": "patient-42",
                    "evaluation_window_hours": 24,
                }
            ]
        },
    )

    patient_id: Annotated[
        str | None,
        Field(
            default=None,
            description="FHIR Patient.id. Optional if SHARP header set.",
        ),
    ] = None
    evaluation_window_hours: Annotated[
        int,
        Field(
            default=24,
            ge=1,
            le=72,
            description="How far back to scan for onset evidence.",
        ),
    ] = 24


class SepsisFlagOutput(BaseModel):
    """Output for ``flag_sepsis_onset``.

    API_CONTRACTS.md §1.3.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "patient_id": "patient-42",
                    "sepsis_suspected": False,
                    "mode": "cdc_ase",
                    "criteria_met": [],
                    "onset_estimate": None,
                    "evidence": {"lactate_value": 1.1, "abx_code": None},
                },
                {
                    "status": "triggered",
                    "patient_id": "patient-42",
                    "sepsis_suspected": True,
                    "mode": "cdc_ase",
                    "criteria_met": [
                        "presumed infection (antibiotic started)",
                        "organ dysfunction: lactate 2.4 mmol/L",
                        "organ dysfunction: SBP 86 mmHg",
                    ],
                    "onset_estimate": "2026-04-15T10:30:00Z",
                    "evidence": {
                        "lactate_loinc": "2524-7",
                        "lactate_value": 2.4,
                        "abx_code": "J01DD04",
                        "sbp": 86,
                    },
                },
            ]
        },
    )

    status: ToolStatus
    patient_id: str
    sepsis_suspected: bool
    mode: Literal["cdc_ase", "sirs_fallback"]
    criteria_met: list[str]
    onset_estimate: datetime | None
    evidence: dict[str, Any]


# ---------------------------------------------------------------------------
# 1.4  generate_escalation_note
# ---------------------------------------------------------------------------


class SBAR(BaseModel):
    """Structured SBAR block (Situation, Background, Assessment, Recommendation).

    API_CONTRACTS.md §1.4 — nested inside ``EscalationOutput``.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "situation": (
                        "Post-op day 1 patient with SBP 86"
                        " and qSOFA 2; sepsis suspected."
                    ),
                    "background": (
                        "42yo s/p laparoscopic cholecystectomy"
                        " 18h ago; Hx T2DM."
                    ),
                    "assessment": (
                        "Meets CDC ASE: lactate 2.4, SBP 86,"
                        " abx started. High deterioration risk."
                    ),
                    "recommendation": (
                        "Activate rapid response, draw repeat"
                        " lactate, bolus 500ml NS, notify attending."
                    ),
                }
            ]
        },
    )

    situation: str
    background: str
    assessment: str
    recommendation: str


class EscalationInput(BaseModel):
    """Input for ``generate_escalation_note``.

    API_CONTRACTS.md §1.4.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "patient_id": "patient-42",
                    "vitals_result": {
                        "status": "triggered",
                        "breaches": [{"label": "SBP", "value": 86.0}],
                    },
                    "risk_result": {
                        "status": "ok",
                        "qsofa_score": 2,
                        "risk_band": "high",
                    },
                    "sepsis_result": {
                        "status": "triggered",
                        "sepsis_suspected": True,
                        "mode": "cdc_ase",
                    },
                    "recipient_role": "rapid_response",
                }
            ]
        },
    )

    patient_id: Annotated[
        str | None,
        Field(
            default=None,
            description="FHIR Patient.id. Optional if SHARP header set.",
        ),
    ] = None
    vitals_result: Annotated[
        dict[str, Any],
        Field(description="Raw JSON from screen_vital_thresholds (ScreenVitalsOutput)."),
    ]
    risk_result: Annotated[
        dict[str, Any],
        Field(description="Raw JSON from score_deterioration_risk (RiskScoreOutput)."),
    ]
    sepsis_result: Annotated[
        dict[str, Any],
        Field(description="Raw JSON from flag_sepsis_onset (SepsisFlagOutput)."),
    ]
    recipient_role: Annotated[
        Literal["charge_nurse", "resident", "attending", "rapid_response"],
        Field(
            default="charge_nurse",
            description="Drives tone and urgency.",
        ),
    ] = "charge_nurse"


class EscalationOutput(BaseModel):
    """Output for ``generate_escalation_note``.

    API_CONTRACTS.md §1.4.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "patient_id": "patient-42",
                    "sbar": {
                        "situation": (
                            "Post-op day 1 patient with SBP 86"
                            " and qSOFA 2; sepsis suspected."
                        ),
                        "background": (
                            "42yo s/p laparoscopic"
                            " cholecystectomy 18h ago; Hx T2DM."
                        ),
                        "assessment": (
                            "Meets CDC ASE: lactate 2.4, SBP 86,"
                            " abx started. High deterioration risk."
                        ),
                        "recommendation": (
                            "Activate rapid response, draw repeat"
                            " lactate, bolus 500ml NS,"
                            " notify attending."
                        ),
                    },
                    "narrative": "S: ... B: ... A: ... R: ...",
                    "severity": "critical",
                    "recipient_role": "rapid_response",
                    "communication_draft": {
                        "resourceType": "Communication",
                        "status": "in-progress",
                        "category": [
                            {
                                "coding": [
                                    {
                                        "system": "http://terminology.hl7.org/CodeSystem/communication-category",
                                        "code": "alert",
                                    }
                                ]
                            }
                        ],
                        "priority": "urgent",
                        "subject": {"reference": "Patient/patient-42"},
                        "encounter": {"reference": "Encounter/enc-77"},
                        "sender": {
                            "reference": "Device/vigil-postop-sentinel",
                            "display": "Vigil Postop Sentinel",
                        },
                        "recipient": [
                            {
                                "reference": "PractitionerRole/rapid-response",
                                "display": "Rapid Response Team",
                            }
                        ],
                        "payload": [{"contentString": "S: ... B: ... A: ... R: ..."}],
                    },
                    "generated_at": "2026-04-15T12:01:10Z",
                    "model_used": "ollama/llama3.1",
                }
            ]
        },
    )

    status: ToolStatus
    patient_id: str
    sbar: SBAR
    narrative: str
    severity: Literal["info", "urgent", "critical"]
    recipient_role: str
    communication_draft: dict[str, Any]
    generated_at: datetime
    model_used: str


# ---------------------------------------------------------------------------
# 6.4  Approve endpoint
# ---------------------------------------------------------------------------


class ApproveRequest(BaseModel):
    """Request body for ``POST /api/patients/{id}/alerts/{alertId}/approve``.

    API_CONTRACTS.md §6.4.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "clinician_id": "prac-nurse-17",
                    "note": "Acknowledged, RRT dispatched.",
                }
            ]
        },
    )

    clinician_id: str
    note: str


class ApproveResponse(BaseModel):
    """Response for ``POST /api/patients/{id}/alerts/{alertId}/approve``.

    API_CONTRACTS.md §6.4.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "alert_id": "comm-884",
                    "status": "completed",
                    "acknowledged_at": "2026-04-15T12:03:44Z",
                    "audit_id": "audit-56",
                }
            ]
        },
    )

    alert_id: str
    status: str
    acknowledged_at: datetime
    audit_id: str
