"""B-news2 — score_news2 implementation.

NEWS2 (National Early Warning Score 2, Royal College of Physicians
2017) — a second-opinion deterioration score that runs alongside qSOFA.
Same FHIR fetch path as ``screen_vital_thresholds``; calls the
deterministic engine in ``backend/criteria/news2.py``.

Reference: RCP 2017,
https://www.rcplondon.ac.uk/projects/outputs/national-early-warning-score-news-2

Why a second opinion: qSOFA was tuned for sepsis specificity and
under-flags non-septic deterioration (haemorrhage, post-op respiratory
compromise, etc.). NEWS2 is the NHS standard for ward-level
deterioration screening — combining the two gives clinicians a more
complete view than either alone.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from backend.criteria.news2 import evaluate_news2
from backend.fhir.client import FhirClient, FhirClientError, is_fhir_auth_error
from backend.fhir.models import Observation
from backend.mcp_server.synthetic_fallback import (
    LIVE_DATA_SOURCE,
    SYNTHETIC_DATA_SOURCE,
    get_synthetic_observations,
    is_fallback_enabled,
)
from backend.obs.metrics import tool_call_timer
from backend.schemas import (
    FhirContext,
    News2ParameterContribution,
    ScoreNews2Output,
    ToolStatus,
)

logger = logging.getLogger("vigil.mcp.tools.score_news2")

# LOINC codes used for NEWS2.
_LOINC_RR = "9279-1"
_LOINC_SPO2 = "59408-5"
_LOINC_TEMP = "8310-5"
_LOINC_SBP = "8480-6"
_LOINC_HR = "8867-4"
_LOINC_GCS = "9269-2"
# Supplemental-O2 flag isn't a single LOINC; clinicians sometimes record
# an "Oxygen therapy" Observation under LOINC 3151-8 (Inhaled oxygen
# flow rate). Default to ``False`` (room air) when no signal is present.
_LOINC_O2_FLOW = "3151-8"


def _latest(
    obs: list[Observation], loinc: str,
) -> tuple[float | None, datetime | None]:
    """Return (value, ts) of the most recent observation matching LOINC."""
    candidates = [
        o for o in obs
        if o.loinc_code == loinc
        and o.valueQuantity
        and o.valueQuantity.value is not None
    ]
    if not candidates:
        return None, None
    candidates.sort(
        key=lambda o: o.effectiveDateTime
        or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return float(candidates[0].valueQuantity.value), candidates[0].effectiveDateTime  # type: ignore[union-attr]


async def run(
    patient_id: str,
    lookback_minutes: int,
    sharp: FhirContext,
) -> str:
    """Execute score_news2 and return JSON string."""
    now = datetime.now(UTC)
    since_iso = (now - timedelta(minutes=lookback_minutes)).isoformat()

    async with tool_call_timer("score_news2", patient_id) as ctx:
        data_source = LIVE_DATA_SOURCE
        try:
            async with FhirClient(sharp) as fhir:
                vitals = await fhir.get_observations(
                    patient_id, category="vital-signs", since=since_iso,
                )
        except FhirClientError as exc:
            if is_fhir_auth_error(exc) and is_fallback_enabled():
                logger.warning(
                    "FHIR auth denied; using synthetic trajectory",
                    extra={
                        "_vigil_patient_id": patient_id,
                        "_vigil_status_code": getattr(
                            exc, "status_code", None
                        ),
                        "_vigil_error": str(exc),
                    },
                )
                vitals = get_synthetic_observations(
                    category="vital-signs", patient_id=patient_id,
                )
                data_source = SYNTHETIC_DATA_SOURCE
            else:
                logger.error(
                    "FHIR fetch failed for score_news2",
                    extra={
                        "_vigil_patient_id": patient_id,
                        "_vigil_status_code": getattr(
                            exc, "status_code", None
                        ),
                        "_vigil_error": str(exc),
                    },
                )
                ctx["status"] = ToolStatus.FHIR_UNAVAILABLE
                output = ScoreNews2Output(
                    status=ToolStatus.FHIR_UNAVAILABLE,
                    patient_id=patient_id,
                    aggregate_score=0,
                    band="low",
                    red_flag=False,
                    parameter_contributions=[],
                    supplemental_o2=False,
                    rationale=f"FHIR unavailable: {exc}",
                )
                return output.model_dump_json()

        rr, _ = _latest(vitals, _LOINC_RR)
        spo2, _ = _latest(vitals, _LOINC_SPO2)
        temp, _ = _latest(vitals, _LOINC_TEMP)
        sbp, _ = _latest(vitals, _LOINC_SBP)
        hr, _ = _latest(vitals, _LOINC_HR)
        gcs, _ = _latest(vitals, _LOINC_GCS)
        o2_flow, _ = _latest(vitals, _LOINC_O2_FLOW)

        # Supplemental O2 = any non-zero recent flow rate. Conservative —
        # ward "nasal cannula at 2 L" still scores 2 per RCP. Patients
        # not on therapy default to room air (0 score).
        supplemental_o2 = bool(o2_flow and o2_flow > 0)
        # ACVPU: GCS<15 collapses to "Confusion" → red-flag scoring 3.
        alert = gcs is None or gcs >= 15

        result = evaluate_news2(
            rr=rr,
            spo2=spo2,
            supplemental_o2=supplemental_o2,
            temp_c=temp,
            sbp=sbp,
            hr=hr,
            alert=alert,
        )

        contributions = [
            News2ParameterContribution(
                parameter=row.parameter,
                value=row.value,
                score=row.score,
            )
            for row in result.contributions
        ]

        # Treat "low" as ok; anything else is at-least-low-medium and
        # worth surfacing as ``triggered`` so the dashboard / chat
        # reflects "we noticed something".
        status = (
            ToolStatus.OK if result.band == "low" else ToolStatus.TRIGGERED
        )
        ctx["status"] = status

        logger.info(
            "score_news2 complete",
            extra={
                "_vigil_patient_id": patient_id,
                "_vigil_news2": result.aggregate,
                "_vigil_band": result.band,
                "_vigil_red_flag": result.red_flag,
                "_vigil_data_source": data_source,
            },
        )

        output = ScoreNews2Output(
            status=status,
            patient_id=patient_id,
            aggregate_score=result.aggregate,
            band=result.band,  # type: ignore[arg-type]
            red_flag=result.red_flag,
            parameter_contributions=contributions,
            supplemental_o2=supplemental_o2,
            rationale=result.rationale,
            data_source=data_source,
        )
        return output.model_dump_json()
