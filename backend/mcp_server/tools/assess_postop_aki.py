"""B-aki — assess_postop_aki implementation.

KDIGO-staged AKI verdict using serial creatinine (LOINC 2160-0) and
24-hour urine output (LOINC 9192-6). The deterministic engine in
``backend/criteria/kdigo.py`` does the staging; this tool is mostly
plumbing — it fetches the right Observations from FHIR, imputes a
baseline creatinine when one isn't supplied (lowest in the past 7
days, per KDIGO 2012 §3.1.2), and layers an SCCM-2017 time-to-
intervention recommendation on top of the stage.

References:
- KDIGO Acute Kidney Injury Work Group. *KDIGO Clinical Practice
  Guideline for Acute Kidney Injury.* Kidney Int Suppl 2012;2(1):1–138.
  (CLINICAL_EVIDENCE §5.1)
- Joannidis M, Druml W, Forni LG, et al. *Prevention of acute kidney
  injury and protection of renal function in the intensive care unit:
  update 2017.* Intensive Care Med 2017;43:730–749.
  https://pubmed.ncbi.nlm.nih.gov/28577069/

Time-to-intervention map (Joannidis 2017):
  Stage 0 → no urgent intervention
  Stage 1 → reassess + KDIGO-bundle within 12h
  Stage 2 → KDIGO-bundle + nephrology consult within 6h
  Stage 3 → immediate (RRT readiness, hemodynamic optimisation)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from backend.criteria.kdigo import evaluate_kdigo
from backend.fhir.client import FhirClient, FhirClientError, is_fhir_auth_error
from backend.fhir.models import Observation
from backend.mcp_server.synthetic_fallback import (
    LIVE_DATA_SOURCE,
    SYNTHETIC_DATA_SOURCE,
    get_synthetic_observations,
    is_fallback_enabled,
)
from backend.obs.metrics import tool_call_timer
from backend.schemas import AssessAkiOutput, FhirContext, ToolStatus

logger = logging.getLogger("vigil.mcp.tools.assess_postop_aki")

# LOINC codes
_LOINC_CREATININE = "2160-0"
_LOINC_URINE_OUTPUT = "9192-6"

# KDIGO 2012 §3.1.2 — when no historical baseline is available, impute
# from the lowest creatinine in the past 7 days. We surface this fact
# in the response so reviewers can challenge the assumption.
_BASELINE_LOOKBACK_DAYS = 7

# SCCM 2017 (Joannidis et al, ICM 2017;43:730) intervention windows.
_TIME_TO_INTERVENTION_HOURS: dict[int, int | None] = {
    0: None,
    1: 12,
    2: 6,
    3: 0,
}


def _creatinine_obs(obs: list[Observation]) -> list[Observation]:
    """Filter to creatinine observations with a value + timestamp."""
    return [
        o for o in obs
        if o.loinc_code == _LOINC_CREATININE
        and o.valueQuantity
        and o.valueQuantity.value is not None
        and o.effectiveDateTime
    ]


def _resolve_creatinine(
    obs: list[Observation],
) -> tuple[float | None, float | None, bool, str]:
    """Return (current, baseline, baseline_imputed, baseline_source).

    "Current" is the most recent creatinine. Baseline is, in order of
    preference:
      - the earliest creatinine more than 48h before "current" but
        within the 7-day lookback (best proxy for pre-AKI baseline), OR
      - the lowest creatinine in the 7-day window (KDIGO 2012 §3.1.2
        imputation), OR
      - None if no historical samples are available.
    """
    creats = _creatinine_obs(obs)
    if not creats:
        return None, None, False, "no creatinine observations available"

    creats.sort(key=lambda o: o.effectiveDateTime)  # type: ignore[arg-type]
    current_obs = creats[-1]
    current = float(current_obs.valueQuantity.value)  # type: ignore[union-attr]

    if len(creats) == 1:
        return current, None, False, "no historical creatinine for baseline"

    current_ts = current_obs.effectiveDateTime
    cutoff = current_ts - timedelta(days=_BASELINE_LOOKBACK_DAYS)  # type: ignore[operator]
    historical = [
        o for o in creats[:-1]
        if o.effectiveDateTime is not None
        and o.effectiveDateTime >= cutoff
    ]
    if not historical:
        return current, None, False, "no creatinine within 7-day baseline window"

    # Prefer a sample >48h before current (true pre-AKI baseline).
    pre_aki_window = current_ts - timedelta(hours=48)  # type: ignore[operator]
    pre_aki = [
        o for o in historical
        if o.effectiveDateTime is not None
        and o.effectiveDateTime <= pre_aki_window
    ]
    if pre_aki:
        # True historical baseline — earliest available.
        pre_aki.sort(key=lambda o: o.effectiveDateTime)  # type: ignore[arg-type]
        baseline = float(pre_aki[0].valueQuantity.value)  # type: ignore[union-attr]
        return (
            current,
            baseline,
            False,
            "earliest creatinine >48h before current (KDIGO 2012)",
        )

    # No pre-AKI sample; impute as the lowest in the 7-day window.
    historical.sort(
        key=lambda o: float(o.valueQuantity.value)  # type: ignore[union-attr]
    )
    baseline = float(historical[0].valueQuantity.value)  # type: ignore[union-attr]
    return (
        current,
        baseline,
        True,
        "imputed: lowest creatinine in past 7 days (KDIGO 2012 §3.1.2)",
    )


def _latest_urine_output(
    obs: list[Observation],
) -> tuple[float | None, float | None]:
    """Return (urine_output_ml_kg_h, oliguria_hours) from LOINC 9192-6.

    LOINC 9192-6 is "Urine output 24 hour"; we approximate hourly
    mL/kg/h by dividing by 24h × patient mass. Without patient mass we
    return mL/kg/h=None and only use the rise-in-creatinine criterion.
    The CLINICAL_EVIDENCE doc flags this as a known limitation
    (§11.2 note on 9192-6 vs 9187-6).
    """
    uo = [
        o for o in obs
        if o.loinc_code == _LOINC_URINE_OUTPUT
        and o.valueQuantity
        and o.valueQuantity.value is not None
    ]
    if not uo:
        return None, None
    uo.sort(
        key=lambda o: o.effectiveDateTime
        or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    latest = uo[0]
    val = float(latest.valueQuantity.value)  # type: ignore[union-attr]
    unit = (latest.valueQuantity.unit or "").lower()  # type: ignore[union-attr]

    # Heuristic: if unit looks like mL/kg/h or mL/h and we already have
    # a per-hour value, surface it directly. Otherwise we cannot reliably
    # reduce a 24h volume to mL/kg/h without patient mass — return None
    # and let the engine fall back to creatinine-only staging.
    if "ml/kg/h" in unit or "ml/(kg.h)" in unit:
        return val, 0.0  # caller treats oliguria_hours=0 as not-yet-counted
    return None, None


async def run(
    patient_id: str,
    sharp: FhirContext,
    creatinine_baseline_override: float | None = None,
) -> str:
    """Execute assess_postop_aki and return JSON string.

    Args:
        patient_id: FHIR Patient.id (required).
        sharp: SHARP-derived FHIR connection context.
        creatinine_baseline_override: If provided, used verbatim (no
            imputation). Tests / clinicians who know the true baseline
            should pass it explicitly so the verdict cites a real value.
    """
    # 7-day lookback window covers KDIGO's baseline rule and gives us
    # serial samples for the 1.5x-rise check.
    since_iso = (
        datetime.now(UTC) - timedelta(days=_BASELINE_LOOKBACK_DAYS)
    ).isoformat()

    async with tool_call_timer("assess_postop_aki", patient_id) as ctx:
        data_source = LIVE_DATA_SOURCE
        try:
            async with FhirClient(sharp) as fhir:
                labs = await fhir.get_observations(
                    patient_id, category="laboratory", since=since_iso,
                )
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
                labs = get_synthetic_observations(
                    category="laboratory", patient_id=patient_id,
                )
                vitals = get_synthetic_observations(
                    category="vital-signs", patient_id=patient_id,
                )
                data_source = SYNTHETIC_DATA_SOURCE
            else:
                logger.error(
                    "FHIR fetch failed for assess_postop_aki",
                    extra={
                        "_vigil_patient_id": patient_id,
                        "_vigil_status_code": getattr(
                            exc, "status_code", None
                        ),
                        "_vigil_error": str(exc),
                    },
                )
                ctx["status"] = ToolStatus.FHIR_UNAVAILABLE
                output = AssessAkiOutput(
                    status=ToolStatus.FHIR_UNAVAILABLE,
                    patient_id=patient_id,
                    kdigo_stage=0,
                    criteria_met=[],
                    creatinine_current=None,
                    creatinine_baseline=None,
                    baseline_imputed=False,
                    baseline_source=f"FHIR unavailable: {exc}",
                    urine_output_ml_kg_h=None,
                    oliguria_hours=None,
                    time_to_intervention_hours=None,
                    rationale=f"FHIR unavailable: {exc}",
                )
                return output.model_dump_json()

        all_obs = labs + vitals

        if creatinine_baseline_override is not None:
            creats = _creatinine_obs(all_obs)
            current = (
                float(creats[-1].valueQuantity.value)  # type: ignore[union-attr]
                if creats
                else None
            )
            baseline = creatinine_baseline_override
            baseline_imputed = False
            baseline_source = "explicit override (clinician-supplied)"
        else:
            (
                current,
                baseline,
                baseline_imputed,
                baseline_source,
            ) = _resolve_creatinine(all_obs)

        urine_output_ml_kg_h, oliguria_hours = _latest_urine_output(
            all_obs,
        )

        kdigo = evaluate_kdigo(
            creatinine_current=current,
            creatinine_baseline=baseline,
            urine_output_ml_kg_h=urine_output_ml_kg_h,
            oliguria_hours=oliguria_hours,
        )

        ttf = _TIME_TO_INTERVENTION_HOURS[kdigo.stage]
        status = (
            ToolStatus.TRIGGERED if kdigo.triggered else ToolStatus.OK
        )
        ctx["status"] = status

        # Append baseline-source caveat to the rationale so a downstream
        # reader can tell whether the verdict rests on a real historical
        # baseline or an imputed one.
        rationale = kdigo.rationale
        if baseline_imputed:
            rationale = (
                f"{rationale} — baseline imputed: {baseline_source}"
            )

        logger.info(
            "assess_postop_aki complete",
            extra={
                "_vigil_patient_id": patient_id,
                "_vigil_kdigo_stage": kdigo.stage,
                "_vigil_baseline_imputed": baseline_imputed,
                "_vigil_data_source": data_source,
            },
        )

        output = AssessAkiOutput(
            status=status,
            patient_id=patient_id,
            kdigo_stage=kdigo.stage,
            criteria_met=kdigo.criteria_met,
            creatinine_current=current,
            creatinine_baseline=baseline,
            baseline_imputed=baseline_imputed,
            baseline_source=baseline_source,
            urine_output_ml_kg_h=urine_output_ml_kg_h,
            oliguria_hours=oliguria_hours,
            time_to_intervention_hours=ttf,
            rationale=rationale,
            data_source=data_source,
        )
        return output.model_dump_json()
