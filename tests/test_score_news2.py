"""Tool-level integration tests for score_news2.

Mocks the FHIR client; asserts output shape, RCP banding, red-flag
detection, and ``data_source`` field.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from backend.fhir.models import CategoryItem, CodeableConcept, Coding, Observation, Quantity
from backend.mcp_server.tools.score_news2 import run
from backend.schemas import FhirContext, ToolStatus

NOW = datetime.now(UTC)
SHARP = FhirContext(url="http://localhost:8080/fhir", token=None, patient_id=None)


def _vital(loinc: str, value: float, unit: str, t: datetime) -> Observation:
    return Observation(
        resourceType="Observation",
        category=[CategoryItem(coding=[Coding(code="vital-signs")])],
        code=CodeableConcept(
            coding=[Coding(system="http://loinc.org", code=loinc)]
        ),
        valueQuantity=Quantity(value=value, unit=unit),
        effectiveDateTime=t,
    )


def _vital_set(
    sbp: float = 120, hr: float = 70, rr: float = 16, spo2: float = 98,
    temp: float = 37.0, gcs: float | None = 15,
) -> list[Observation]:
    t = NOW - timedelta(minutes=2)
    obs = [
        _vital("8480-6", sbp, "mm[Hg]", t),
        _vital("8867-4", hr, "/min", t),
        _vital("9279-1", rr, "/min", t),
        _vital("59408-5", spo2, "%", t),
        _vital("8310-5", temp, "Cel", t),
    ]
    if gcs is not None:
        obs.append(_vital("9269-2", gcs, "{score}", t))
    return obs


@pytest.mark.asyncio
class TestNews2Shape:
    async def test_low_band_status_ok(self) -> None:
        with patch(
            "backend.mcp_server.tools.score_news2.FhirClient"
        ) as M:
            client = M.return_value.__aenter__.return_value
            client.get_observations = AsyncMock(return_value=_vital_set())

            raw = await run("PT-001", 240, SHARP)

        out = json.loads(raw)
        assert out["status"] == ToolStatus.OK
        assert out["aggregate_score"] == 0
        assert out["band"] == "low"
        assert out["red_flag"] is False
        assert out["data_source"] == "fhir"
        # Per-parameter rows must be present and complete.
        params = {p["parameter"] for p in out["parameter_contributions"]}
        assert {"RR", "SpO2", "Temp", "SBP", "HR", "Consciousness"} <= params

    async def test_high_band_red_flag_triggered(self) -> None:
        with patch(
            "backend.mcp_server.tools.score_news2.FhirClient"
        ) as M:
            client = M.return_value.__aenter__.return_value
            client.get_observations = AsyncMock(
                return_value=_vital_set(
                    sbp=88,    # 3
                    hr=132,    # 3
                    rr=26,     # 3
                    spo2=92,   # 2
                    temp=38.5, # 1
                    gcs=14,    # altered → 3
                )
            )

            raw = await run("PT-007", 240, SHARP)

        out = json.loads(raw)
        assert out["status"] == ToolStatus.TRIGGERED
        assert out["band"] == "high"
        assert out["red_flag"] is True
        assert out["aggregate_score"] >= 7

    async def test_data_source_synthetic_on_auth_fallback(
        self, monkeypatch
    ) -> None:
        """Auth-shape FHIR error + fallback enabled → synthetic_demo."""
        monkeypatch.setenv("VIGIL_SYNTHETIC_FALLBACK", "true")
        from backend.fhir.client import FhirClientError

        with patch(
            "backend.mcp_server.tools.score_news2.FhirClient"
        ) as M:
            client = M.return_value.__aenter__.return_value
            client.get_observations = AsyncMock(
                side_effect=FhirClientError("401 Unauthorized", status_code=401)
            )
            raw = await run("PT-007", 240, SHARP)

        out = json.loads(raw)
        assert out["data_source"] == "synthetic_demo"
