"""B-pph — assess_pph_severity implementation.

CMQCC OB Hemorrhage Toolkit v3.0 staging for postpartum hemorrhage.
Fetches cumulative EBL (LOINC 55758-7), latest hemoglobin (LOINC 718-7),
fibrinogen (LOINC 3255-7), HR + SBP from FHIR; calls the deterministic
engine in ``backend/criteria/pph.py``.

References:
- CMQCC OB Hemorrhage Toolkit v3.0 (2022).
  https://www.cmqcc.org/resources-tool-kits/toolkits/ob-hemorrhage-toolkit
- ACOG Practice Bulletin No. 183: *Postpartum Hemorrhage*. Obstet
  Gynecol 2017;130(4):e168–e186. PubMed 28937571.
- ACOG Committee Opinion 794: *Quantitative Blood Loss in Obstetric
  Hemorrhage* (Dec 2019). Visual EBL inflates ~30% — surfaced as
  caveat when EBL is unmeasured.

Why a separate tool: postpartum hemorrhage stages are not a subset of
MEWT or qSOFA. The shock-index threshold + EBL-vs-route logic + verbatim
CMQCC action ladder all live here so the postpartum cameo (PT-010) can
reuse the same agent without ward-branching code paths.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Literal

from backend.criteria.pph import evaluate_pph
from backend.fhir.client import FhirClient, FhirClientError, is_fhir_auth_error
from backend.fhir.models import Observation
from backend.mcp_server.synthetic_fallback import (
    LIVE_DATA_SOURCE,
    SYNTHETIC_DATA_SOURCE,
    get_synthetic_observations,
    is_fallback_enabled,
)
from backend.obs.metrics import tool_call_timer
from backend.schemas import AssessPphOutput, FhirContext, ToolStatus

logger = logging.getLogger("vigil.mcp.tools.assess_pph_severity")

# LOINC codes
_LOINC_EBL = "55758-7"          # Estimated blood loss
_LOINC_HGB = "718-7"            # Hemoglobin
_LOINC_FIBRINOGEN = "3255-7"    # Fibrinogen [Mass/Vol] in PPP
_LOINC_HR = "8867-4"
_LOINC_SBP = "8480-6"

# 24h is ACOG's PPH definition window; we don't look further back.
_PPH_LOOKBACK_HOURS = 24


def _latest_value(
    obs: list[Observation], loinc: str,
) -> tuple[float | None, datetime | None]:
    """Return (value, timestamp) of the most recent matching observation."""
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
    return (
        float(candidates[0].valueQuantity.value),  # type: ignore[union-attr]
        candidates[0].effectiveDateTime,
    )


def _max_value(
    obs: list[Observation], loinc: str,
) -> float | None:
    """Return the maximum value across observations of a given LOINC.

    Cumulative EBL is monotonically non-decreasing so taking the max is
    equivalent to "latest" for a well-formed trajectory; using max
    instead is defensive against out-of-order ingestion.
    """
    vals = [
        float(o.valueQuantity.value)  # type: ignore[union-attr]
        for o in obs
        if o.loinc_code == loinc
        and o.valueQuantity
        and o.valueQuantity.value is not None
    ]
    return max(vals) if vals else None


async def run(
    patient_id: str,
    sharp: FhirContext,
    delivery_route: Literal["vaginal", "cesarean", "unknown"] = "vaginal",
    uterotonics_given: int = 0,
    clinical_instability: bool = False,
) -> str:
    """Execute assess_pph_severity and return JSON string.

    Args:
        patient_id: FHIR Patient.id (required).
        sharp: SHARP-derived FHIR connection context.
        delivery_route: Vaginal vs cesarean affects the Stage-1 cutoff.
            ``"unknown"`` reverts to the vaginal cutoff (more sensitive).
        uterotonics_given: Number of uterotonic agents administered.
            Bedside-supplied — Vigil does NOT auto-detect this.
        clinical_instability: Bedside team flag for hemodynamic
            instability that bypasses absolute thresholds.
    """
    since_iso = (
        datetime.now(UTC) - timedelta(hours=_PPH_LOOKBACK_HOURS)
    ).isoformat()

    async with tool_call_timer("assess_pph_severity", patient_id) as ctx:
        data_source = LIVE_DATA_SOURCE
        try:
            async with FhirClient(sharp) as fhir:
                vitals = await fhir.get_observations(
                    patient_id, category="vital-signs", since=since_iso,
                )
                labs = await fhir.get_observations(
                    patient_id, category="laboratory", since=since_iso,
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
                labs = get_synthetic_observations(
                    category="laboratory", patient_id=patient_id,
                )
                data_source = SYNTHETIC_DATA_SOURCE
            else:
                logger.error(
                    "FHIR fetch failed for assess_pph_severity",
                    extra={
                        "_vigil_patient_id": patient_id,
                        "_vigil_status_code": getattr(
                            exc, "status_code", None
                        ),
                        "_vigil_error": str(exc),
                    },
                )
                ctx["status"] = ToolStatus.FHIR_UNAVAILABLE
                output = AssessPphOutput(
                    status=ToolStatus.FHIR_UNAVAILABLE,
                    patient_id=patient_id,
                    stage=0,
                    cumulative_ebl_ml=None,
                    ebl_route=delivery_route,
                    shock_index=None,
                    hemoglobin_g_dl=None,
                    fibrinogen_mg_dl=None,
                    triggers=[],
                    recommended_actions=[],
                    ebl_caveat=None,
                    rationale=f"FHIR unavailable: {exc}",
                )
                return output.model_dump_json()

        all_obs = labs + vitals

        # Cumulative EBL — bundled labels EBL Observations under the
        # vital-signs category in the synthetic fixtures, so we look in
        # both. ``_max_value`` is robust to either category placement.
        cumulative_ebl_ml = _max_value(all_obs, _LOINC_EBL)
        hgb, _ = _latest_value(all_obs, _LOINC_HGB)
        fibrinogen, _ = _latest_value(all_obs, _LOINC_FIBRINOGEN)
        hr, _ = _latest_value(all_obs, _LOINC_HR)
        sbp, _ = _latest_value(all_obs, _LOINC_SBP)

        result = evaluate_pph(
            cumulative_ebl_ml=cumulative_ebl_ml,
            delivery_route=delivery_route,
            hr=hr,
            sbp=sbp,
            fibrinogen_mg_dl=fibrinogen,
            uterotonics_given=uterotonics_given,
            clinical_instability=clinical_instability,
        )

        status = (
            ToolStatus.TRIGGERED if result.stage >= 1 else ToolStatus.OK
        )
        ctx["status"] = status

        logger.info(
            "assess_pph_severity complete",
            extra={
                "_vigil_patient_id": patient_id,
                "_vigil_pph_stage": result.stage,
                "_vigil_ebl_ml": cumulative_ebl_ml,
                "_vigil_shock_index": result.shock_index,
                "_vigil_data_source": data_source,
            },
        )

        output = AssessPphOutput(
            status=status,
            patient_id=patient_id,
            stage=result.stage,
            cumulative_ebl_ml=cumulative_ebl_ml,
            ebl_route=delivery_route,
            shock_index=result.shock_index,
            hemoglobin_g_dl=hgb,
            fibrinogen_mg_dl=fibrinogen,
            triggers=result.triggers,
            recommended_actions=result.recommended_actions,
            ebl_caveat=result.ebl_caveat,
            rationale=result.rationale,
            data_source=data_source,
        )
        return output.model_dump_json()
