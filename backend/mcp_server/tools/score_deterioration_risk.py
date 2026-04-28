"""B3 — score_deterioration_risk implementation.

Fetches recent vitals and active Conditions from FHIR, runs qSOFA scoring,
computes a composite trend-based risk score, and returns a RiskScoreOutput.

Composite risk formula (Vigil operational, not externally validated):
  base = qsofa_score / 3
  breach_weight = min(mewt_breach_count * 0.15, 0.3)
  condition_weight = min(active_condition_count * 0.05, 0.15)
  composite = clamp(base + breach_weight + condition_weight, 0.0, 1.0)

Risk bands: low < 0.3, moderate 0.3–0.6, high > 0.6.

Reference: API_CONTRACTS.md §1.2, BUILD_PLAN.md B3
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from backend.criteria.mewt import VitalReading, evaluate_mewt
from backend.criteria.qsofa import evaluate_qsofa
from backend.fhir.client import FhirClient, FhirClientError, is_fhir_auth_error
from backend.mcp_server.synthetic_fallback import (
    LIVE_DATA_SOURCE,
    SYNTHETIC_DATA_SOURCE,
    get_synthetic_conditions,
    get_synthetic_observations,
    is_fallback_enabled,
)
from backend.obs.metrics import tool_call_timer
from backend.schemas import FhirContext, RiskScoreOutput, ToolStatus

logger = logging.getLogger("vigil.mcp.tools.score_deterioration_risk")

# LOINC codes for qSOFA extraction
_LOINC_SBP = "8480-6"
_LOINC_RR = "9279-1"
_LOINC_GCS = "9269-2"


def _latest_value(readings: list[VitalReading], loinc: str) -> float | None:
    """Return the most recent value for a given LOINC code."""
    candidates = [r for r in readings if r.loinc == loinc]
    if not candidates:
        return None
    candidates.sort(key=lambda r: r.timestamp, reverse=True)
    return candidates[0].value


def _compute_composite(
    qsofa_score: int,
    mewt_breach_count: int,
    condition_count: int,
) -> float:
    """Compute composite risk score (0.0–1.0)."""
    base = qsofa_score / 3.0
    breach_weight = min(mewt_breach_count * 0.15, 0.3)
    condition_weight = min(condition_count * 0.05, 0.15)
    return min(base + breach_weight + condition_weight, 1.0)


def _risk_band(composite: float) -> str:
    if composite >= 0.6:
        return "high"
    if composite >= 0.3:
        return "moderate"
    return "low"


def _format_conditions(conditions: list) -> list[str]:
    """Extract SNOMED code + display from Condition resources."""
    result: list[str] = []
    for cond in conditions:
        if cond.code:
            for coding in cond.code.coding:
                if coding.code and coding.display:
                    result.append(f"{coding.code} {coding.display}")
                    break
            else:
                if cond.code.text:
                    result.append(cond.code.text)
    return result


async def run(
    patient_id: str,
    window_hours: int,
    trajectory: str,
    sharp: FhirContext,
) -> str:
    """Execute score_deterioration_risk and return JSON string."""
    now = datetime.now(UTC)
    since_iso = (now - timedelta(hours=window_hours)).isoformat()

    async with tool_call_timer("score_deterioration_risk", patient_id) as ctx:
        data_source = LIVE_DATA_SOURCE
        try:
            async with FhirClient(sharp) as fhir:
                observations = await fhir.get_observations(
                    patient_id,
                    category="vital-signs",
                    since=since_iso,
                )
                conditions = await fhir.get_conditions(patient_id)
        except FhirClientError as exc:
            # Auth-shaped failure → opt-in fallback to PT-007 trajectory.
            # See backend/mcp_server/synthetic_fallback.py docstring.
            if is_fhir_auth_error(exc) and is_fallback_enabled():
                logger.warning(
                    "FHIR auth denied; using synthetic PT-007 trajectory",
                    extra={
                        "_vigil_patient_id": patient_id,
                        "_vigil_status_code": getattr(exc, "status_code", None),
                        "_vigil_error": str(exc),
                    },
                )
                observations = get_synthetic_observations(
                    category="vital-signs"
                )
                conditions = get_synthetic_conditions()
                data_source = SYNTHETIC_DATA_SOURCE
            else:
                logger.error(
                    "FHIR fetch failed for score_deterioration_risk",
                    extra={
                        "_vigil_patient_id": patient_id,
                        "_vigil_status_code": getattr(exc, "status_code", None),
                        "_vigil_error": str(exc),
                    },
                )
                ctx["status"] = ToolStatus.FHIR_UNAVAILABLE
                output = RiskScoreOutput(
                    status=ToolStatus.FHIR_UNAVAILABLE,
                    patient_id=patient_id,
                    qsofa_score=0,
                    qsofa_components={
                        "rr_ge_22": False,
                        "sbp_le_100": False,
                        "altered_mental": False,
                    },
                    composite_risk=0.0,
                    risk_band="low",
                    rationale=f"FHIR unavailable: {exc}",
                    contributing_conditions=[],
                )
                return output.model_dump_json()

        # Convert observations to VitalReading
        vitals: list[VitalReading] = []
        for obs in observations:
            loinc = obs.loinc_code
            if (
                loinc
                and obs.valueQuantity
                and obs.valueQuantity.value is not None
                and obs.effectiveDateTime
            ):
                vitals.append(
                    VitalReading(
                        loinc=loinc,
                        value=obs.valueQuantity.value,
                        unit=obs.valueQuantity.unit or "",
                        timestamp=obs.effectiveDateTime,
                    )
                )

        # qSOFA from latest vitals
        sbp = _latest_value(vitals, _LOINC_SBP)
        rr = _latest_value(vitals, _LOINC_RR)
        gcs_val = _latest_value(vitals, _LOINC_GCS)
        gcs = int(gcs_val) if gcs_val is not None else None

        qsofa = evaluate_qsofa(sbp=sbp, rr=rr, gcs=gcs)

        # MEWT for breach count
        mewt = evaluate_mewt(vitals, trajectory)

        # Active conditions
        active_conditions = [
            c for c in conditions
            if c.clinicalStatus and any(
                coding.code == "active"
                for coding in c.clinicalStatus.coding
            )
        ]
        condition_labels = _format_conditions(active_conditions)

        # Composite score
        composite = _compute_composite(
            qsofa.score,
            mewt.score,
            len(active_conditions),
        )
        composite = round(composite, 2)
        band = _risk_band(composite)

        status = ToolStatus.OK if band == "low" else ToolStatus.TRIGGERED
        ctx["status"] = status

        # Rationale
        parts = [qsofa.rationale]
        if mewt.triggered:
            parts.append(f"MEWT: {mewt.score} breach(es)")
        if active_conditions:
            parts.append(f"{len(active_conditions)} active condition(s)")
        rationale = "; ".join(parts)

        logger.info(
            "score_deterioration_risk complete",
            extra={
                "_vigil_patient_id": patient_id,
                "_vigil_qsofa_score": qsofa.score,
                "_vigil_composite_risk": composite,
                "_vigil_risk_band": band,
                "_vigil_data_source": data_source,
            },
        )

        output = RiskScoreOutput(
            status=status,
            patient_id=patient_id,
            qsofa_score=qsofa.score,
            qsofa_components=qsofa.components,
            composite_risk=composite,
            risk_band=band,
            rationale=rationale,
            contributing_conditions=condition_labels,
            data_source=data_source,
        )
        return output.model_dump_json()
