"""B4 — flag_sepsis_onset implementation.

CDC Adult Sepsis Event (ASE) surveillance logic:
  1. Presumed infection — NEW antibiotic administration detected within the
     empiric window (pre-operative prophylaxis excluded; see _ABX_EMPIRIC_WINDOW_HOURS)
  2. Organ dysfunction — any of:
     - Lactate >= 2.0 mmol/L (LOINC 2524-7)
     - SBP <= 100 mmHg (LOINC 8480-6)
     - Creatinine acute rise (KDIGO stage >= 1)
     - qSOFA >= 2

If lab data is too sparse for CDC ASE, falls back to SIRS (2-of-4).

Reference: API_CONTRACTS.md §1.3, BUILD_PLAN.md B4,
           CLINICAL_EVIDENCE.md §3–§5
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.criteria.kdigo import evaluate_kdigo
from backend.criteria.qsofa import evaluate_qsofa
from backend.criteria.sirs import evaluate_sirs
from backend.fhir.client import FhirClient, FhirClientError, is_fhir_auth_error
from backend.fhir.models import MedicationAdministration, Observation
from backend.mcp_server.synthetic_fallback import (
    LIVE_DATA_SOURCE,
    SYNTHETIC_DATA_SOURCE,
    get_synthetic_medication_administrations,
    get_synthetic_observations,
    is_fallback_enabled,
)
from backend.obs.metrics import tool_call_timer
from backend.schemas import FhirContext, SepsisFlagOutput, ToolStatus

logger = logging.getLogger("vigil.mcp.tools.flag_sepsis_onset")

# LOINC codes
_LOINC_LACTATE = "2524-7"
_LOINC_SBP = "8480-6"
_LOINC_RR = "9279-1"
_LOINC_HR = "8867-4"
_LOINC_TEMP = "8310-5"
_LOINC_WBC = "6690-2"
_LOINC_CREATININE = "2160-0"
_LOINC_GCS = "9269-2"

# Antibiotic ATC prefix (J01 = antibacterials for systemic use)
_ABX_ATC_PREFIX = "J01"

# Vigil operational: only antibiotics administered within the last N hours count
# as "new empirical therapy" for the CDC ASE presumed-infection criterion.
# Pre-operative single-dose prophylaxis (typically given 30–60 min before
# incision) is NOT a new treatment course — it does not constitute an infection
# signal for CDC ASE surveillance purposes.
# Derivation: CDC ASE requires "new administration of ≥1 qualifying antibiotic
# on ≥4 consecutive days" (CLINICAL_EVIDENCE §4.1). Our 6-hour window is a
# practical proxy: empirical / therapeutic ABX are started in response to
# clinical deterioration (post-onset), while prophylactic doses occur pre-op
# and are therefore >8h before the monitoring window for our seed dataset.
# (Vigil operational choice — not a published threshold; prospective validation
# required before clinical deployment.)
_ABX_EMPIRIC_WINDOW_HOURS = 6


def _latest_obs_value(
    observations: list[Observation], loinc: str,
) -> tuple[float | None, datetime | None]:
    """Return (value, timestamp) of the most recent observation for a LOINC code."""
    candidates = [
        o for o in observations
        if o.loinc_code == loinc
        and o.valueQuantity
        and o.valueQuantity.value is not None
    ]
    if not candidates:
        return None, None
    candidates.sort(
        key=lambda o: o.effectiveDateTime or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    obs = candidates[0]
    return obs.valueQuantity.value, obs.effectiveDateTime  # type: ignore[union-attr]


def _find_antibiotic(
    med_admins: list[MedicationAdministration],
    new_abx_since: datetime | None = None,
) -> str | None:
    """Return ATC/RxNorm code if a NEW antibiotic administration is found.

    Args:
        med_admins: All MedicationAdministration resources for the patient.
        new_abx_since: If set, only administrations on or after this datetime
            are considered. Antibiotics given before this cutoff (e.g., pre-op
            prophylaxis) are excluded from the presumed-infection signal.
            (Vigil operational, CLINICAL_EVIDENCE §4.1.)
    """
    for ma in med_admins:
        if ma.status not in ("completed", "in-progress", "active"):
            continue
        # Exclude antibiotics administered before the empiric-window cutoff.
        # Pre-op prophylaxis (e.g., cefazolin 30 min before incision) does not
        # constitute a new treatment course for CDC ASE purposes; only empirical
        # / therapeutic antibiotics started during or after clinical deterioration
        # count. (Vigil operational choice — CLINICAL_EVIDENCE §4.1.)
        if (
            new_abx_since is not None
            and ma.effectiveDateTime is not None
            and ma.effectiveDateTime < new_abx_since
        ):
            continue
        if ma.medicationCodeableConcept:
            for coding in ma.medicationCodeableConcept.coding:
                code = coding.code or ""
                # ATC J01* prefix for antibacterials
                if code.upper().startswith(_ABX_ATC_PREFIX):
                    return code
                # Also accept if display mentions common antibiotics
                display = (coding.display or "").lower()
                for abx_keyword in (
                    "ceftriaxone", "vancomycin", "piperacillin",
                    "meropenem", "ciprofloxacin", "metronidazole",
                    "amoxicillin", "azithromycin", "levofloxacin",
                    "cefazolin", "ampicillin", "gentamicin",
                ):
                    if abx_keyword in display:
                        return code or abx_keyword
    return None


def _find_creatinine_pair(
    observations: list[Observation],
) -> tuple[float | None, float | None]:
    """Return (current_creatinine, baseline_creatinine) from lab observations.

    Baseline is approximated as the earliest creatinine in the window.
    """
    creat_obs = [
        o for o in observations
        if o.loinc_code == _LOINC_CREATININE
        and o.valueQuantity
        and o.valueQuantity.value is not None
        and o.effectiveDateTime
    ]
    if len(creat_obs) < 1:
        return None, None
    creat_obs.sort(key=lambda o: o.effectiveDateTime or datetime.min.replace(tzinfo=UTC))
    current = creat_obs[-1].valueQuantity.value  # type: ignore[union-attr]
    baseline = creat_obs[0].valueQuantity.value if len(creat_obs) > 1 else None  # type: ignore[union-attr]
    return current, baseline


async def run(
    patient_id: str,
    evaluation_window_hours: int,
    sharp: FhirContext,
) -> str:
    """Execute flag_sepsis_onset and return JSON string."""
    since_iso = (
        datetime.now(UTC) - timedelta(hours=evaluation_window_hours)
    ).isoformat()

    async with tool_call_timer("flag_sepsis_onset", patient_id) as ctx:
        data_source = LIVE_DATA_SOURCE
        try:
            async with FhirClient(sharp) as fhir:
                vitals = await fhir.get_observations(
                    patient_id, category="vital-signs", since=since_iso,
                )
                labs = await fhir.get_observations(
                    patient_id, category="laboratory", since=since_iso,
                )
                med_admins = await fhir.get_medication_administrations(
                    patient_id,
                )
        except FhirClientError as exc:
            # Auth-shaped failure → opt-in fallback to PT-007 trajectory.
            # See backend/mcp_server/synthetic_fallback.py docstring.
            if is_fhir_auth_error(exc) and is_fallback_enabled():
                logger.warning(
                    "FHIR auth denied; using synthetic PT-007 trajectory",
                    extra={"patient_id": patient_id, "error": str(exc)},
                )
                vitals = get_synthetic_observations(category="vital-signs")
                labs = get_synthetic_observations(category="laboratory")
                med_admins = get_synthetic_medication_administrations()
                data_source = SYNTHETIC_DATA_SOURCE
            else:
                logger.error(
                    "FHIR fetch failed for flag_sepsis_onset",
                    extra={"patient_id": patient_id, "error": str(exc)},
                )
                ctx["status"] = ToolStatus.FHIR_UNAVAILABLE
                output = SepsisFlagOutput(
                    status=ToolStatus.FHIR_UNAVAILABLE,
                    patient_id=patient_id,
                    sepsis_suspected=False,
                    mode="cdc_ase",
                    criteria_met=[],
                    onset_estimate=None,
                    evidence={"error": str(exc)},
                )
                return output.model_dump_json()

        all_obs = vitals + labs
        evidence: dict[str, Any] = {}
        criteria_met: list[str] = []
        onset_estimate: datetime | None = None

        # --- Step 1: Presumed infection (new antibiotic administration) ---
        # Only antibiotics administered within _ABX_EMPIRIC_WINDOW_HOURS count
        # as "new empirical therapy". Pre-op prophylaxis given >8h ago is
        # excluded — a single dose does not satisfy CDC ASE infection criterion.
        # (Vigil operational, CLINICAL_EVIDENCE §4.1.)
        new_abx_since = datetime.now(UTC) - timedelta(hours=_ABX_EMPIRIC_WINDOW_HOURS)
        abx_code = _find_antibiotic(med_admins, new_abx_since=new_abx_since)
        has_presumed_infection = abx_code is not None
        evidence["abx_code"] = abx_code
        if has_presumed_infection:
            criteria_met.append("presumed infection (antibiotic started)")

        # --- Step 2: Organ dysfunction markers ---
        # Lactate
        lactate_val, lactate_ts = _latest_obs_value(all_obs, _LOINC_LACTATE)
        evidence["lactate_value"] = lactate_val
        if lactate_val is not None and lactate_val >= 2.0:
            criteria_met.append(
                f"organ dysfunction: lactate {lactate_val} mmol/L"
            )
            if onset_estimate is None and lactate_ts:
                onset_estimate = lactate_ts

        # SBP
        sbp_val, sbp_ts = _latest_obs_value(all_obs, _LOINC_SBP)
        evidence["sbp"] = sbp_val
        if sbp_val is not None and sbp_val <= 100:
            criteria_met.append(
                f"organ dysfunction: SBP {sbp_val} mmHg"
            )
            if onset_estimate is None and sbp_ts:
                onset_estimate = sbp_ts

        # Creatinine / KDIGO
        creat_current, creat_baseline = _find_creatinine_pair(all_obs)
        evidence["creatinine_current"] = creat_current
        evidence["creatinine_baseline"] = creat_baseline
        if creat_current is not None:
            kdigo = evaluate_kdigo(
                creatinine_current=creat_current,
                creatinine_baseline=creat_baseline,
            )
            if kdigo.triggered:
                criteria_met.append(
                    f"organ dysfunction: {kdigo.rationale}"
                )

        # qSOFA
        rr_val, _ = _latest_obs_value(all_obs, _LOINC_RR)
        gcs_val, _ = _latest_obs_value(all_obs, _LOINC_GCS)
        qsofa = evaluate_qsofa(
            sbp=sbp_val,
            rr=rr_val,
            gcs=int(gcs_val) if gcs_val is not None else None,
        )
        evidence["qsofa_score"] = qsofa.score
        if qsofa.triggered:
            criteria_met.append(
                f"organ dysfunction: qSOFA {qsofa.score} >= 2"
            )

        # --- CDC ASE decision ---
        # CDC ASE requires: presumed infection + >= 1 organ dysfunction
        organ_dysfunction_count = len(criteria_met) - (
            1 if has_presumed_infection else 0
        )
        has_enough_lab_data = (
            lactate_val is not None or creat_current is not None
        )

        if has_enough_lab_data:
            # CDC ASE mode
            sepsis_suspected = (
                has_presumed_infection and organ_dysfunction_count >= 1
            )
            mode = "cdc_ase"
        else:
            # SIRS fallback — not enough lab data for CDC ASE
            temp_val, _ = _latest_obs_value(all_obs, _LOINC_TEMP)
            hr_val, _ = _latest_obs_value(all_obs, _LOINC_HR)
            wbc_val, _ = _latest_obs_value(all_obs, _LOINC_WBC)

            sirs = evaluate_sirs(
                temp=temp_val, hr=hr_val, rr=rr_val, wbc=wbc_val,
            )
            evidence["sirs_score"] = sirs.score
            evidence["sirs_components"] = sirs.components

            if sirs.triggered:
                criteria_met.append(f"SIRS {sirs.score}/4 positive")

            sepsis_suspected = (
                has_presumed_infection and sirs.triggered
            )
            mode = "sirs_fallback"

        status = (
            ToolStatus.TRIGGERED if sepsis_suspected else ToolStatus.OK
        )
        ctx["status"] = status

        logger.info(
            "flag_sepsis_onset complete",
            extra={
                "patient_id": patient_id,
                "sepsis_suspected": sepsis_suspected,
                "mode": mode,
                "criteria_count": len(criteria_met),
            },
        )

        output = SepsisFlagOutput(
            status=status,
            patient_id=patient_id,
            sepsis_suspected=sepsis_suspected,
            mode=mode,
            criteria_met=criteria_met,
            onset_estimate=onset_estimate,
            evidence=evidence,
            data_source=data_source,
        )
        return output.model_dump_json()
