"""B2 — screen_vital_thresholds implementation.

Fetches recent vital-signs Observations from FHIR, converts them to
VitalReading instances, and runs the MEWT engine. Returns a
ScreenVitalsOutput JSON string.

Reference: API_CONTRACTS.md §1.1, BUILD_PLAN.md B2
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from backend.criteria.mewt import VitalReading, evaluate_mewt
from backend.fhir.client import FhirClient, FhirClientError
from backend.obs.metrics import tool_call_timer
from backend.schemas import FhirContext, ScreenVitalsOutput, ToolStatus

logger = logging.getLogger("vigil.mcp.tools.screen_vital_thresholds")


def _obs_to_readings(observations: list) -> list[VitalReading]:
    """Convert FHIR Observations to VitalReading list."""
    readings: list[VitalReading] = []
    for obs in observations:
        loinc = obs.loinc_code
        if (
            loinc
            and obs.valueQuantity
            and obs.valueQuantity.value is not None
            and obs.effectiveDateTime
        ):
            readings.append(
                VitalReading(
                    loinc=loinc,
                    value=obs.valueQuantity.value,
                    unit=obs.valueQuantity.unit or "",
                    timestamp=obs.effectiveDateTime,
                )
            )
    return readings


async def run(
    patient_id: str,
    lookback_minutes: int,
    trajectory: str,
    sharp: FhirContext,
) -> str:
    """Execute screen_vital_thresholds and return JSON string."""
    now = datetime.now(UTC)
    window_start = now - timedelta(minutes=lookback_minutes)
    since_iso = window_start.isoformat()

    async with tool_call_timer("screen_vital_thresholds", patient_id) as ctx:
        try:
            async with FhirClient(sharp) as fhir:
                observations = await fhir.get_observations(
                    patient_id,
                    category="vital-signs",
                    since=since_iso,
                )
        except FhirClientError as exc:
            logger.error(
                "FHIR fetch failed for screen_vital_thresholds",
                extra={"patient_id": patient_id, "error": str(exc)},
            )
            ctx["status"] = ToolStatus.FHIR_UNAVAILABLE
            output = ScreenVitalsOutput(
                status=ToolStatus.FHIR_UNAVAILABLE,
                patient_id=patient_id,
                trajectory=trajectory,
                breaches=[],
                scanned_count=0,
                window_start=window_start,
                window_end=now,
            )
            return output.model_dump_json()

        vitals = _obs_to_readings(observations)
        result = evaluate_mewt(vitals, trajectory)

        status = ToolStatus.TRIGGERED if result.triggered else ToolStatus.OK
        ctx["status"] = status

        logger.info(
            "screen_vital_thresholds complete",
            extra={
                "patient_id": patient_id,
                "scanned": len(vitals),
                "breaches": len(result.breaches),
                "triggered": result.triggered,
            },
        )

        output = ScreenVitalsOutput(
            status=status,
            patient_id=patient_id,
            trajectory=trajectory,
            breaches=result.breaches,
            scanned_count=len(vitals),
            window_start=window_start,
            window_end=now,
        )
        return output.model_dump_json()
