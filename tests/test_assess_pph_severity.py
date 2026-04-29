"""Tool-level integration tests for assess_pph_severity.

Mocks the FHIR client; asserts CMQCC stage verdict, EBL caveat, the
verbatim action ladder, and the ``data_source`` field.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from backend.fhir.models import CategoryItem, CodeableConcept, Coding, Observation, Quantity
from backend.mcp_server.tools.assess_pph_severity import run
from backend.schemas import FhirContext, ToolStatus

NOW = datetime.now(UTC)
SHARP = FhirContext(url="http://localhost:8080/fhir", token=None, patient_id=None)


def _obs(
    loinc: str, value: float, unit: str, ts: datetime,
    category: str = "vital-signs",
) -> Observation:
    return Observation(
        resourceType="Observation",
        category=[CategoryItem(coding=[Coding(code=category)])],
        code=CodeableConcept(
            coding=[Coding(system="http://loinc.org", code=loinc)]
        ),
        valueQuantity=Quantity(value=value, unit=unit),
        effectiveDateTime=ts,
    )


@pytest.mark.asyncio
class TestPphToolShape:
    async def test_pt010_stage3_with_ebl_si_fibrinogen(self) -> None:
        """PT-010 demo trajectory inputs → Stage 3, full action ladder."""
        t = NOW - timedelta(minutes=10)
        labs = [
            _obs("3255-7", 175.0, "mg/dL", t, category="laboratory"),
            _obs("718-7", 7.2, "g/dL", t, category="laboratory"),
        ]
        vitals = [
            _obs("55758-7", 2050.0, "mL", t),
            _obs("8867-4", 132.0, "/min", t),
            _obs("8480-6", 82.0, "mm[Hg]", t),
        ]
        with patch(
            "backend.mcp_server.tools.assess_pph_severity.FhirClient"
        ) as M:
            client = M.return_value.__aenter__.return_value
            # Tool calls vital-signs first then laboratory.
            client.get_observations = AsyncMock(side_effect=[vitals, labs])

            raw = await run("PT-010", SHARP, delivery_route="vaginal")

        out = json.loads(raw)
        assert out["status"] == ToolStatus.TRIGGERED
        assert out["stage"] == 3
        assert out["cumulative_ebl_ml"] == pytest.approx(2050.0)
        assert out["fibrinogen_mg_dl"] == pytest.approx(175.0)
        assert out["hemoglobin_g_dl"] == pytest.approx(7.2)
        assert out["shock_index"] == pytest.approx(132 / 82, abs=0.01)
        assert out["data_source"] == "fhir"
        assert out["ebl_caveat"] is None
        # Verbatim CMQCC action ladder for Stage 3.
        joined = " ".join(out["recommended_actions"]).lower()
        assert "massive transfusion" in joined
        assert "tranexamic" in joined

    async def test_no_ebl_degrades_with_caveat(self) -> None:
        """No EBL Observation → ebl_caveat set, staging from SI only."""
        t = NOW - timedelta(minutes=10)
        vitals = [
            _obs("8867-4", 130.0, "/min", t),
            _obs("8480-6", 90.0, "mm[Hg]", t),
        ]
        with patch(
            "backend.mcp_server.tools.assess_pph_severity.FhirClient"
        ) as M:
            client = M.return_value.__aenter__.return_value
            client.get_observations = AsyncMock(side_effect=[vitals, []])

            raw = await run("PT-010", SHARP, delivery_route="vaginal")

        out = json.loads(raw)
        assert out["cumulative_ebl_ml"] is None
        assert out["ebl_caveat"] is not None
        assert "ACOG" in out["ebl_caveat"]
        # SI 130/90 ≈ 1.44 → Stage 3.
        assert out["stage"] == 3

    async def test_data_source_synthetic_on_auth_fallback(
        self, monkeypatch
    ) -> None:
        """Auth-shape FHIR error + fallback enabled → synthetic_demo
        loads PT-010's bundle for PPH skill calls."""
        monkeypatch.setenv("VIGIL_SYNTHETIC_FALLBACK", "true")
        from backend.fhir.client import FhirClientError
        from backend.mcp_server import synthetic_fallback as sf

        # Force a fresh load so the new fibrinogen rows we wrote to PT-010
        # JSON show up in this test.
        sf.reset_for_tests()

        with patch(
            "backend.mcp_server.tools.assess_pph_severity.FhirClient"
        ) as M:
            client = M.return_value.__aenter__.return_value
            client.get_observations = AsyncMock(
                side_effect=FhirClientError(
                    "403 Forbidden", status_code=403,
                )
            )
            raw = await run("PT-010", SHARP, delivery_route="vaginal")

        out = json.loads(raw)
        assert out["data_source"] == "synthetic_demo"
        # PT-010 bundle peak EBL is 2050 mL → Stage 3.
        assert out["stage"] == 3
