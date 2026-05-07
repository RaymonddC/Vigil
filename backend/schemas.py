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
    data_source: Literal["fhir", "synthetic_demo"] = "fhir"
    # Per-LOINC observation history, sorted oldest → newest. Lets the
    # chat layer compute trend direction (↑/↓/↔) for each breached
    # vital — clinicians scan direction-of-travel before the absolute
    # number when triaging postop deterioration.
    vitals_history: dict[str, list[VitalSample]] = Field(
        default_factory=dict
    )


class VitalSample(BaseModel):
    """One vital-sign reading as returned in ``ScreenVitalsOutput.vitals_history``.

    Slimmer than ``VitalBreach`` because it carries no severity / threshold
    metadata — just enough to compute trend direction and render in the
    chat handler.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "value": 88.0,
                    "unit": "mm[Hg]",
                    "observed_at": "2026-04-15T11:48:00Z",
                }
            ]
        },
    )

    value: float
    unit: str
    observed_at: datetime


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
    data_source: Literal["fhir", "synthetic_demo"] = "fhir"


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
    data_source: Literal["fhir", "synthetic_demo"] = "fhir"


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
    data_source: Literal["fhir", "synthetic_demo"] = "fhir"


# ---------------------------------------------------------------------------
# 1.5  assess_postop_aki  — KDIGO-staged AKI verdict
# ---------------------------------------------------------------------------


class AssessAkiOutput(BaseModel):
    """Output for ``assess_postop_aki``.

    KDIGO-staged AKI verdict using serial creatinine (LOINC 2160-0) and
    24-hour urine output (LOINC 9192-6). Cites SCCM 2017 (Joannidis
    et al, ICM 2017;43:730) for the time-to-intervention recommendation.

    When no explicit ``creatinine_baseline`` is available, the tool
    imputes baseline as the lowest creatinine in the past 7 days
    (KDIGO 2012 §3.1.2 imputation rule). ``baseline_imputed=True``
    surfaces this so reviewers can probe — never fudge silently.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "status": "triggered",
                    "patient_id": "PT-007",
                    "kdigo_stage": 2,
                    "criteria_met": [
                        "SCr 2.1 is 2.3x baseline 0.9 (2.0-2.9x)",
                    ],
                    "creatinine_current": 2.1,
                    "creatinine_baseline": 0.9,
                    "baseline_imputed": True,
                    "baseline_source": (
                        "lowest creatinine in past 7d (KDIGO 2012 §3.1.2)"
                    ),
                    "urine_output_ml_kg_h": None,
                    "oliguria_hours": None,
                    "time_to_intervention_hours": 6,
                    "rationale": (
                        "KDIGO Stage 2; SCr 2.1 is 2.3x baseline 0.9."
                    ),
                    "data_source": "fhir",
                }
            ]
        },
    )

    status: ToolStatus
    patient_id: str
    kdigo_stage: int = Field(ge=0, le=3)
    criteria_met: list[str]
    creatinine_current: float | None
    creatinine_baseline: float | None
    baseline_imputed: bool
    baseline_source: str
    urine_output_ml_kg_h: float | None
    oliguria_hours: float | None
    time_to_intervention_hours: int | None = Field(
        default=None,
        description=(
            "Recommended time-to-intervention per SCCM 2017 (Joannidis "
            "et al, ICM 2017): None for stage 0, 12h for stage 1, 6h for "
            "stage 2, immediate (0h) for stage 3."
        ),
    )
    rationale: str
    data_source: Literal["fhir", "synthetic_demo"] = "fhir"


# ---------------------------------------------------------------------------
# 1.6  score_news2  — NEWS2 second-opinion deterioration score
# ---------------------------------------------------------------------------


class News2ParameterContribution(BaseModel):
    """Single-parameter NEWS2 contribution row.

    Per RCP 2017 NEWS2 chart: each parameter contributes 0–3 points.
    A single parameter scoring 3 is the ``red_flag`` per RCP guidance.
    """

    model_config = ConfigDict(extra="forbid")

    parameter: str
    value: float | None
    score: int = Field(ge=0, le=3)


class ScoreNews2Output(BaseModel):
    """Output for ``score_news2``.

    NEWS2 (Royal College of Physicians 2017) — second-opinion to qSOFA.
    Aggregate 0–20, banded {low, low-medium, medium, high} per RCP.
    ``red_flag`` true iff any single parameter scores 3.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "status": "triggered",
                    "patient_id": "PT-007",
                    "aggregate_score": 7,
                    "band": "high",
                    "red_flag": True,
                    "parameter_contributions": [
                        {"parameter": "RR", "value": 24.0, "score": 3},
                        {"parameter": "SBP", "value": 88.0, "score": 3},
                    ],
                    "supplemental_o2": False,
                    "rationale": "NEWS2=7 (high). Red flag: RR=24, SBP=88.",
                    "data_source": "fhir",
                }
            ]
        },
    )

    status: ToolStatus
    patient_id: str
    aggregate_score: int = Field(ge=0, le=20)
    band: Literal["low", "low-medium", "medium", "high"]
    red_flag: bool
    parameter_contributions: list[News2ParameterContribution]
    supplemental_o2: bool
    rationale: str
    data_source: Literal["fhir", "synthetic_demo"] = "fhir"


# ---------------------------------------------------------------------------
# 1.7  assess_pph_severity  — CMQCC postpartum hemorrhage staging
# ---------------------------------------------------------------------------


class AssessPphOutput(BaseModel):
    """Output for ``assess_pph_severity``.

    CMQCC OB Hemorrhage Toolkit v3.0 staging plus ACOG Practice Bulletin
    183 (2017) cumulative-EBL definition. ``recommended_actions`` is the
    verbatim CMQCC ladder text (NOT LLM-generated) — keep it that way.

    When EBL is not measured, the tool degrades to shock-index-only with
    an explicit caveat — visual EBL inflates ~30% per ACOG Committee
    Opinion 794.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "status": "triggered",
                    "patient_id": "PT-010",
                    "stage": 3,
                    "cumulative_ebl_ml": 2050.0,
                    "ebl_route": "vaginal",
                    "shock_index": 1.61,
                    "hemoglobin_g_dl": 7.2,
                    "fibrinogen_mg_dl": 175.0,
                    "triggers": [
                        "EBL 2050 mL ≥1500 (Stage 3)",
                        "Shock index 1.61 ≥1.4 (Stage 3)",
                        "Fibrinogen 175 mg/dL <200 (Stage 3)",
                    ],
                    "recommended_actions": [
                        "Activate massive transfusion protocol",
                        "Mobilize OR/IR for surgical/embolization control",
                    ],
                    "ebl_caveat": None,
                    "rationale": "CMQCC Stage 3.",
                    "data_source": "fhir",
                }
            ]
        },
    )

    status: ToolStatus
    patient_id: str
    stage: int = Field(ge=0, le=3)
    cumulative_ebl_ml: float | None
    ebl_route: Literal["vaginal", "cesarean", "unknown"]
    shock_index: float | None
    hemoglobin_g_dl: float | None
    fibrinogen_mg_dl: float | None
    triggers: list[str]
    recommended_actions: list[str]
    ebl_caveat: str | None
    rationale: str
    data_source: Literal["fhir", "synthetic_demo"] = "fhir"


# ---------------------------------------------------------------------------
# 1.8  flag_treatment_conflicts  — physiology-aware drug safety scanner
# ---------------------------------------------------------------------------


class TreatmentConflict(BaseModel):
    """Single drug-vs-physiology conflict row.

    Each row carries the rule_id (so the chat layer can format
    consistently across rules), the severity, the offending drug, a
    short physiology summary explaining *why* the rule fired, the
    citation anchor (linked to ``docs/CLINICAL_EVIDENCE.md`` "Treatment
    Conflict Rules"), the verbatim mitigation string, and a short list
    of safe alternatives.
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: Literal[
        "nsaid_aki",
        "bblocker_brady_hypo",
        "ace_arb_hyperk",
        "opioid_resp_depression",
        "anticoag_hgb_drop",
    ]
    severity: Literal["warning", "critical"]
    drug_class: str
    drug_display: str
    physiology_summary: str
    citation_anchor: str
    mitigation: str
    safe_alternatives: list[str]


class TreatmentConflictsOutput(BaseModel):
    """Output for ``flag_treatment_conflicts``.

    Returns a list of ``TreatmentConflict`` rows (possibly empty), a
    de-duplicated ``safe_alternatives`` summary across rules, and an
    evidence block surfacing the inputs the engine used.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "status": "triggered",
                    "patient_id": "PT-008",
                    "conflicts": [
                        {
                            "rule_id": "nsaid_aki",
                            "severity": "critical",
                            "drug_class": "NSAID",
                            "drug_display": "ibuprofen 600 mg po",
                            "physiology_summary": (
                                "KDIGO stage 1 AKI present"
                            ),
                            "citation_anchor": (
                                "KDIGO 2012 §4.4.1; AGS Beers "
                                "Criteria 2023"
                            ),
                            "mitigation": (
                                "Consider acetaminophen, gabapentin, "
                                "or regional/local analgesia."
                            ),
                            "safe_alternatives": [
                                "acetaminophen",
                                "gabapentin",
                            ],
                        }
                    ],
                    "safe_alternatives": [
                        "acetaminophen", "gabapentin",
                    ],
                    "evidence": {
                        "kdigo_stage": 1,
                        "k": None,
                        "hr": 78,
                    },
                    "data_source": "fhir",
                }
            ]
        },
    )

    status: ToolStatus
    patient_id: str
    conflicts: list[TreatmentConflict]
    safe_alternatives: list[str]
    evidence: dict[str, Any]
    data_source: Literal["fhir", "synthetic_demo"] = "fhir"


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
