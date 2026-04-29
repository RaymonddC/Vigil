"""Tool-level integration tests for assess_postop_aki.

Mocks the FHIR client; asserts output shape, KDIGO stage, baseline-
imputation surfacing, and ``data_source`` field.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from backend.fhir.models import CategoryItem, CodeableConcept, Coding, Observation, Quantity
from backend.mcp_server.tools.assess_postop_aki import run
from backend.schemas import FhirContext, ToolStatus

NOW = datetime.now(UTC)
SHARP = FhirContext(url="http://localhost:8080/fhir", token=None, patient_id=None)


def _creat(value: float, ts: datetime) -> Observation:
    return Observation(
        resourceType="Observation",
        category=[CategoryItem(coding=[Coding(code="laboratory")])],
        code=CodeableConcept(
            coding=[Coding(system="http://loinc.org", code="2160-0")]
        ),
        valueQuantity=Quantity(value=value, unit="mg/dL"),
        effectiveDateTime=ts,
    )


@pytest.mark.asyncio
class TestAssessAkiShape:
    async def test_no_aki_status_ok(self) -> None:
        """SCr stable at 0.9 across 7d → stage 0, status ok."""
        labs = [
            _creat(0.9, NOW - timedelta(days=5)),
            _creat(0.95, NOW - timedelta(days=2)),
            _creat(0.9, NOW - timedelta(hours=1)),
        ]
        with patch(
            "backend.mcp_server.tools.assess_postop_aki.FhirClient"
        ) as M:
            client = M.return_value.__aenter__.return_value
            client.get_observations = AsyncMock(side_effect=[labs, []])

            raw = await run("PT-007", SHARP)

        out = json.loads(raw)
        assert out["status"] == ToolStatus.OK
        assert out["kdigo_stage"] == 0
        assert out["data_source"] == "fhir"
        assert out["time_to_intervention_hours"] is None
        assert "creatinine_current" in out
        assert "creatinine_baseline" in out

    async def test_stage_2_baseline_imputed_surfaced(self) -> None:
        """No pre-AKI sample (>48h before current) → baseline imputed
        from lowest in 7d, with the imputation surfaced explicitly."""
        labs = [
            _creat(0.9, NOW - timedelta(hours=10)),
            _creat(1.4, NOW - timedelta(hours=5)),
            _creat(2.0, NOW - timedelta(minutes=15)),
        ]
        with patch(
            "backend.mcp_server.tools.assess_postop_aki.FhirClient"
        ) as M:
            client = M.return_value.__aenter__.return_value
            client.get_observations = AsyncMock(side_effect=[labs, []])

            raw = await run("PT-007", SHARP)

        out = json.loads(raw)
        assert out["status"] == ToolStatus.TRIGGERED
        assert out["kdigo_stage"] == 2
        # Baseline imputed because no sample is >48h before current.
        assert out["baseline_imputed"] is True
        assert "lowest" in out["baseline_source"].lower()
        # Joannidis 2017 — Stage 2 → 6h.
        assert out["time_to_intervention_hours"] == 6
        # Imputation must be visible in rationale text — Zheng will probe.
        assert "imputed" in out["rationale"].lower()

    async def test_stage_3_immediate_intervention(self) -> None:
        """SCr ≥4.0 → Stage 3 absolute → 0h time-to-intervention."""
        labs = [
            _creat(0.9, NOW - timedelta(days=4)),
            _creat(4.5, NOW - timedelta(minutes=30)),
        ]
        with patch(
            "backend.mcp_server.tools.assess_postop_aki.FhirClient"
        ) as M:
            client = M.return_value.__aenter__.return_value
            client.get_observations = AsyncMock(side_effect=[labs, []])

            raw = await run("PT-007", SHARP)

        out = json.loads(raw)
        assert out["kdigo_stage"] == 3
        assert out["time_to_intervention_hours"] == 0

    async def test_baseline_override_skips_imputation(self) -> None:
        """When clinician supplies a baseline, no imputation flag set."""
        labs = [
            _creat(2.0, NOW - timedelta(minutes=15)),
        ]
        with patch(
            "backend.mcp_server.tools.assess_postop_aki.FhirClient"
        ) as M:
            client = M.return_value.__aenter__.return_value
            client.get_observations = AsyncMock(side_effect=[labs, []])

            raw = await run(
                "PT-007", SHARP, creatinine_baseline_override=0.9,
            )

        out = json.loads(raw)
        assert out["baseline_imputed"] is False
        assert out["creatinine_baseline"] == pytest.approx(0.9)
        assert out["kdigo_stage"] == 2  # 2.0 / 0.9 = 2.22x
