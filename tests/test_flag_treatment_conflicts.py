"""Tool-level integration tests for flag_treatment_conflicts.

Mocks the FHIR client; asserts output shape, ``data_source`` field, and
the synthetic-fallback path on a 4xx error.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from backend.fhir.models import (
    CategoryItem,
    CodeableConcept,
    Coding,
    MedicationAdministration,
    MedicationRequest,
    Observation,
    Quantity,
)
from backend.mcp_server.tools.flag_treatment_conflicts import run
from backend.schemas import FhirContext, ToolStatus

NOW = datetime.now(UTC)
SHARP = FhirContext(
    url="http://localhost:8080/fhir", token=None, patient_id=None,
)


def _obs(loinc: str, value: float, ts: datetime, category: str = "laboratory") -> Observation:
    return Observation(
        resourceType="Observation",
        category=[CategoryItem(coding=[Coding(code=category)])],
        code=CodeableConcept(
            coding=[Coding(system="http://loinc.org", code=loinc)]
        ),
        valueQuantity=Quantity(value=value, unit="unit"),
        effectiveDateTime=ts,
    )


def _request(display: str) -> MedicationRequest:
    return MedicationRequest(
        resourceType="MedicationRequest",
        status="active",
        intent="order",
        medicationCodeableConcept=CodeableConcept(
            coding=[Coding(display=display)]
        ),
    )


def _admin(display: str, ts: datetime) -> MedicationAdministration:
    return MedicationAdministration(
        resourceType="MedicationAdministration",
        status="completed",
        medicationCodeableConcept=CodeableConcept(
            coding=[Coding(display=display)]
        ),
        effectiveDateTime=ts,
    )


@pytest.mark.asyncio
class TestFlagTreatmentConflictsShape:
    async def test_no_drugs_no_conflicts_status_ok(self) -> None:
        """No medication data → no conflicts, status ok, fhir source."""
        with patch(
            "backend.mcp_server.tools.flag_treatment_conflicts.FhirClient"
        ) as M:
            client = M.return_value.__aenter__.return_value
            # vitals, labs, admins, requests all empty
            client.get_observations = AsyncMock(side_effect=[[], []])
            client.get_medication_administrations = AsyncMock(return_value=[])
            client.get_medication_requests = AsyncMock(return_value=[])
            raw = await run("PT-001", SHARP)

        out = json.loads(raw)
        assert out["status"] == ToolStatus.OK
        assert out["conflicts"] == []
        assert out["safe_alternatives"] == []
        assert out["data_source"] == "fhir"

    async def test_nsaid_aki_triggered_with_citation_and_mitigation(self) -> None:
        """AKI (creatinine 0.9→2.0) + ibuprofen order → critical conflict."""
        creats = [
            _obs("2160-0", 0.9, NOW - timedelta(days=2)),
            _obs("2160-0", 2.0, NOW - timedelta(minutes=10)),
        ]
        with patch(
            "backend.mcp_server.tools.flag_treatment_conflicts.FhirClient"
        ) as M:
            client = M.return_value.__aenter__.return_value
            client.get_observations = AsyncMock(side_effect=[[], creats])
            client.get_medication_administrations = AsyncMock(return_value=[])
            client.get_medication_requests = AsyncMock(
                return_value=[_request("Ibuprofen 600 mg po q6h prn")]
            )
            raw = await run("PT-008", SHARP)

        out = json.loads(raw)
        assert out["status"] == ToolStatus.TRIGGERED
        rule_ids = [c["rule_id"] for c in out["conflicts"]]
        assert "nsaid_aki" in rule_ids
        nsaid = next(c for c in out["conflicts"] if c["rule_id"] == "nsaid_aki")
        assert nsaid["severity"] == "critical"
        assert "KDIGO" in nsaid["citation_anchor"]
        assert "acetaminophen" in nsaid["mitigation"].lower()
        assert "acetaminophen" in nsaid["safe_alternatives"]
        # Evidence block must surface KDIGO stage so reviewers can probe.
        assert out["evidence"]["kdigo_stage"] >= 1

    async def test_data_source_synthetic_on_auth_fallback(
        self, monkeypatch
    ) -> None:
        """Auth-shape FHIR error + fallback enabled → synthetic_demo."""
        monkeypatch.setenv("VIGIL_SYNTHETIC_FALLBACK", "true")
        from backend.fhir.client import FhirClientError
        from backend.mcp_server import synthetic_fallback as sf

        sf.reset_for_tests()

        with patch(
            "backend.mcp_server.tools.flag_treatment_conflicts.FhirClient"
        ) as M:
            client = M.return_value.__aenter__.return_value
            client.get_observations = AsyncMock(
                side_effect=FhirClientError(
                    "401 Unauthorized", status_code=401,
                )
            )
            raw = await run("PT-008", SHARP)

        out = json.loads(raw)
        assert out["data_source"] == "synthetic_demo"

    async def test_synthetic_pt008_lights_up_nsaid_aki(
        self, monkeypatch,
    ) -> None:
        """PT-008's bundled trajectory + active ibuprofen order → conflict."""
        monkeypatch.setenv("VIGIL_SYNTHETIC_FALLBACK", "true")
        from backend.fhir.client import FhirClientError
        from backend.mcp_server import synthetic_fallback as sf

        sf.reset_for_tests()

        with patch(
            "backend.mcp_server.tools.flag_treatment_conflicts.FhirClient"
        ) as M:
            client = M.return_value.__aenter__.return_value
            client.get_observations = AsyncMock(
                side_effect=FhirClientError(
                    "403 Forbidden", status_code=403,
                )
            )
            raw = await run("PT-008", SHARP)

        out = json.loads(raw)
        assert out["data_source"] == "synthetic_demo"
        rule_ids = [c["rule_id"] for c in out["conflicts"]]
        assert "nsaid_aki" in rule_ids

    async def test_fhir_unavailable_returns_error_envelope(self) -> None:
        """500-shape error + fallback OFF → fhir_error envelope."""
        from backend.fhir.client import FhirClientError

        with patch(
            "backend.mcp_server.tools.flag_treatment_conflicts.FhirClient"
        ) as M:
            client = M.return_value.__aenter__.return_value
            client.get_observations = AsyncMock(
                side_effect=FhirClientError(
                    "500 boom", status_code=500,
                )
            )
            raw = await run("PT-001", SHARP)

        out = json.loads(raw)
        assert out["status"] == ToolStatus.FHIR_UNAVAILABLE
        assert out["data_source"] == "fhir"


@pytest.mark.asyncio
class TestFlagTreatmentConflictsAdministration:
    async def test_recent_administration_counts_as_active_drug(self) -> None:
        """A morphine administration 1h ago + SpO2 90 → opioid rule fires."""
        creats: list[Observation] = []
        vitals = [
            _obs("59408-5", 90.0, NOW - timedelta(minutes=10),
                 category="vital-signs"),
        ]
        admins = [
            _admin("Morphine 4 mg IV", NOW - timedelta(hours=1)),
        ]
        with patch(
            "backend.mcp_server.tools.flag_treatment_conflicts.FhirClient"
        ) as M:
            client = M.return_value.__aenter__.return_value
            client.get_observations = AsyncMock(side_effect=[vitals, creats])
            client.get_medication_administrations = AsyncMock(return_value=admins)
            client.get_medication_requests = AsyncMock(return_value=[])
            raw = await run("PT-007", SHARP)

        out = json.loads(raw)
        rule_ids = [c["rule_id"] for c in out["conflicts"]]
        assert "opioid_resp_depression" in rule_ids
