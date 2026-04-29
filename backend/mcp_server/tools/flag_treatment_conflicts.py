"""B-tx-conflicts — flag_treatment_conflicts implementation.

Physiology-aware drug safety scanner. Pulls observations + medication
administrations + medication requests + conditions from FHIR, then runs
the 5-rule engine in ``backend/criteria/treatment_conflicts.py``:

  1. NSAID + AKI
  2. β-blocker + bradycardia / hypotension
  3. ACE-I/ARB + hyperkalemia
  4. Opioid + respiratory depression
  5. Anticoagulant + Hgb drop / active-bleeding suspicion

Returns a structured ``TreatmentConflictsOutput`` shape — list of
conflict rows with severity, citation anchor, and verbatim mitigation
text. The chat-friendly prose is layered downstream (in the A2A skill
handler); this tool is deterministic — no LLM.

References (full citations in ``docs/CLINICAL_EVIDENCE.md`` "Treatment
Conflict Rules"):
- KDIGO 2012 §4.4.1; AGS Beers 2023.
- 2017 ACC/AHA hypertension guideline (Whelton 2018).
- KDIGO 2024 BP-in-CKD §4.3.
- ASPMN 2020 (Jungquist).
- ASH 2018 VTE Anticoagulation guideline (Witt).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from backend.criteria.kdigo import evaluate_kdigo
from backend.criteria.treatment_conflicts import (
    evaluate_treatment_conflicts,
)
from backend.fhir.client import FhirClient, FhirClientError, is_fhir_auth_error
from backend.fhir.models import (
    MedicationAdministration,
    MedicationRequest,
    Observation,
)
from backend.mcp_server.synthetic_fallback import (
    LIVE_DATA_SOURCE,
    SYNTHETIC_DATA_SOURCE,
    get_synthetic_medication_administrations,
    get_synthetic_medication_requests,
    get_synthetic_observations,
    is_fallback_enabled,
)
from backend.obs.metrics import tool_call_timer
from backend.schemas import (
    FhirContext,
    ToolStatus,
    TreatmentConflict,
    TreatmentConflictsOutput,
)

logger = logging.getLogger("vigil.mcp.tools.flag_treatment_conflicts")

_LOINC_CREATININE = "2160-0"
_LOOKBACK_HOURS = 24


def _resolve_kdigo_stage(observations: list[Observation]) -> int:
    """Run KDIGO staging on the same observation set the engine sees.

    Mirrors the baseline-imputation pattern used by ``assess_postop_aki``
    but in collapsed form — we only need the stage integer, not the
    rationale, baseline source, or time-to-intervention recommendation.
    """
    creats = [
        o for o in observations
        if o.loinc_code == _LOINC_CREATININE
        and o.valueQuantity
        and o.valueQuantity.value is not None
        and o.effectiveDateTime
    ]
    if not creats:
        return 0
    creats.sort(key=lambda o: o.effectiveDateTime)  # type: ignore[arg-type]
    current = float(creats[-1].valueQuantity.value)  # type: ignore[union-attr]
    if len(creats) == 1:
        return 0
    # Use lowest-in-7d as imputed baseline (KDIGO 2012 §3.1.2).
    historical = creats[:-1]
    historical.sort(
        key=lambda o: float(o.valueQuantity.value)  # type: ignore[union-attr]
    )
    baseline = float(historical[0].valueQuantity.value)  # type: ignore[union-attr]
    result = evaluate_kdigo(
        creatinine_current=current,
        creatinine_baseline=baseline,
    )
    return result.stage


async def run(
    patient_id: str,
    sharp: FhirContext,
    lookback_hours: int = _LOOKBACK_HOURS,
) -> str:
    """Execute flag_treatment_conflicts and return JSON string."""
    now = datetime.now(UTC)
    since_iso = (now - timedelta(hours=lookback_hours)).isoformat()
    # Hgb-drop rule needs a 7-day window for baseline; widen the lab pull.
    labs_since_iso = (now - timedelta(days=7)).isoformat()

    async with tool_call_timer(
        "flag_treatment_conflicts", patient_id,
    ) as ctx:
        data_source = LIVE_DATA_SOURCE
        observations: list[Observation]
        med_admins: list[MedicationAdministration]
        med_requests: list[MedicationRequest]

        try:
            async with FhirClient(sharp) as fhir:
                vitals = await fhir.get_observations(
                    patient_id, category="vital-signs", since=since_iso,
                )
                labs = await fhir.get_observations(
                    patient_id, category="laboratory", since=labs_since_iso,
                )
                med_admins = await fhir.get_medication_administrations(
                    patient_id,
                )
                med_requests = await fhir.get_medication_requests(
                    patient_id,
                )
            observations = vitals + labs
        except FhirClientError as exc:
            if is_fhir_auth_error(exc) and is_fallback_enabled():
                logger.warning(
                    "FHIR auth denied; using synthetic trajectory",
                    extra={
                        "_vigil_patient_id": patient_id,
                        "_vigil_status_code": getattr(
                            exc, "status_code", None,
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
                observations = vitals + labs
                med_admins = get_synthetic_medication_administrations(
                    patient_id=patient_id,
                )
                med_requests = get_synthetic_medication_requests(
                    patient_id=patient_id,
                )
                data_source = SYNTHETIC_DATA_SOURCE
            else:
                logger.error(
                    "FHIR fetch failed for flag_treatment_conflicts",
                    extra={
                        "_vigil_patient_id": patient_id,
                        "_vigil_status_code": getattr(
                            exc, "status_code", None,
                        ),
                        "_vigil_error": str(exc),
                    },
                )
                ctx["status"] = ToolStatus.FHIR_UNAVAILABLE
                output = TreatmentConflictsOutput(
                    status=ToolStatus.FHIR_UNAVAILABLE,
                    patient_id=patient_id,
                    conflicts=[],
                    safe_alternatives=[],
                    evidence={"error": str(exc)},
                )
                return output.model_dump_json()

        kdigo_stage = _resolve_kdigo_stage(observations)
        report = evaluate_treatment_conflicts(
            observations=observations,
            medication_administrations=med_admins,
            medication_requests=med_requests,
            kdigo_stage=kdigo_stage,
            now=now,
        )

        conflicts = [
            TreatmentConflict(
                rule_id=c.rule_id,  # type: ignore[arg-type]
                severity=c.severity,  # type: ignore[arg-type]
                drug_class=c.drug_class,
                drug_display=c.drug_display,
                physiology_summary=c.physiology_summary,
                citation_anchor=c.citation_anchor,
                mitigation=c.mitigation,
                safe_alternatives=c.safe_alternatives,
            )
            for c in report.conflicts
        ]

        status = (
            ToolStatus.TRIGGERED if conflicts else ToolStatus.OK
        )
        ctx["status"] = status

        logger.info(
            "flag_treatment_conflicts complete",
            extra={
                "_vigil_patient_id": patient_id,
                "_vigil_conflict_count": len(conflicts),
                "_vigil_kdigo_stage": kdigo_stage,
                "_vigil_data_source": data_source,
            },
        )

        output = TreatmentConflictsOutput(
            status=status,
            patient_id=patient_id,
            conflicts=conflicts,
            safe_alternatives=report.safe_alternatives,
            evidence=report.evidence,
            data_source=data_source,
        )
        return output.model_dump_json()
