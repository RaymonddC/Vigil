"""Tests for FHIR client with mocked httpx responses."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.fhir.client import FhirClient, FhirClientError
from backend.fhir.models import (
    Condition,
    Encounter,
    MedicationAdministration,
    Observation,
    Patient,
)
from backend.schemas import FhirContext

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FHIR_BASE = "http://localhost:8080/fhir"


@pytest.fixture
def context() -> FhirContext:
    return FhirContext(url=FHIR_BASE, token=None)


@pytest.fixture
def authed_context() -> FhirContext:
    return FhirContext(url=FHIR_BASE, token="test-bearer-token")


def _mock_response(data: dict, status: int = 200) -> MagicMock:
    """Create a mock httpx.Response (synchronous json() like real httpx)."""
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = data
    resp.text = json.dumps(data)
    return resp


# ---------------------------------------------------------------------------
# Patient
# ---------------------------------------------------------------------------


class TestGetPatient:
    async def test_returns_patient(self, context: FhirContext):
        patient_json = {
            "resourceType": "Patient",
            "id": "PT-001",
            "identifier": [{"system": "http://vigil.local/mrn", "value": "MRN-100001"}],
            "name": [{"family": "Patient", "given": ["Synthetic", "1"]}],
            "gender": "female",
            "birthDate": "1978-03-14",
        }
        async with FhirClient(context) as client:
            mock_get = AsyncMock(return_value=_mock_response(patient_json))
            with patch.object(client._client, "get", mock_get):
                result = await client.get_patient("PT-001")
        assert isinstance(result, Patient)
        assert result.id == "PT-001"
        assert result.name[0].family == "Patient"
        assert result.gender == "female"

    async def test_404_raises(self, context: FhirContext):
        async with FhirClient(context) as client:
            mock_get = AsyncMock(return_value=_mock_response({"issue": "not found"}, status=404))
            with patch.object(client._client, "get", mock_get):
                with pytest.raises(FhirClientError) as exc_info:
                    await client.get_patient("NONEXISTENT")
                assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------


class TestGetObservations:
    async def test_returns_observations(self, context: FhirContext):
        bundle = {
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "obs-sbp-1",
                        "status": "final",
                        "category": [
                            {
                                "coding": [
                                    {
                                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                        "code": "vital-signs",
                                    }
                                ]
                            }
                        ],
                        "code": {
                            "coding": [
                                {"system": "http://loinc.org", "code": "8480-6", "display": "SBP"}
                            ]
                        },
                        "effectiveDateTime": "2026-04-15T10:00:00Z",
                        "valueQuantity": {"value": 122, "unit": "mm[Hg]"},
                    }
                }
            ],
        }
        async with FhirClient(context) as client:
            mock_get = AsyncMock(return_value=_mock_response(bundle))
            with patch.object(client._client, "get", mock_get):
                result = await client.get_observations("PT-001", category="vital-signs")
        assert len(result) == 1
        assert isinstance(result[0], Observation)
        assert result[0].loinc_code == "8480-6"
        assert result[0].valueQuantity.value == 122

    async def test_empty_bundle(self, context: FhirContext):
        bundle = {"resourceType": "Bundle", "type": "searchset"}
        async with FhirClient(context) as client:
            mock_get = AsyncMock(return_value=_mock_response(bundle))
            with patch.object(client._client, "get", mock_get):
                result = await client.get_observations("PT-001")
        assert result == []

    async def test_category_filter_sent(self, context: FhirContext):
        bundle = {"resourceType": "Bundle", "type": "searchset", "entry": []}
        async with FhirClient(context) as client:
            mock_get = AsyncMock(return_value=_mock_response(bundle))
            with patch.object(client._client, "get", mock_get):
                await client.get_observations("PT-001", category="laboratory", since="2026-04-15")
            call_kwargs = mock_get.call_args
            params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
            assert params["category"] == "laboratory"
            assert "ge2026-04-15" in params["date"]


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------


class TestGetConditions:
    async def test_returns_conditions(self, context: FhirContext):
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "cond-1",
                        "code": {
                            "coding": [
                                {
                                    "system": "http://snomed.info/sct",
                                    "code": "44054006",
                                    "display": "Type 2 diabetes",
                                }
                            ]
                        },
                        "subject": {"reference": "Patient/PT-007"},
                    }
                }
            ],
        }
        async with FhirClient(context) as client:
            mock_get = AsyncMock(return_value=_mock_response(bundle))
            with patch.object(client._client, "get", mock_get):
                result = await client.get_conditions("PT-007")
        assert len(result) == 1
        assert isinstance(result[0], Condition)
        assert result[0].code.coding[0].code == "44054006"


# ---------------------------------------------------------------------------
# MedicationAdministration
# ---------------------------------------------------------------------------


class TestGetMedicationAdministrations:
    async def test_returns_med_admins(self, context: FhirContext):
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "MedicationAdministration",
                        "id": "medadmin-1",
                        "status": "completed",
                        "medicationCodeableConcept": {
                            "coding": [
                                {
                    "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                    "code": "309264",
                }
                            ]
                        },
                        "subject": {"reference": "Patient/PT-001"},
                        "effectiveDateTime": "2026-04-15T09:30:00Z",
                    }
                }
            ],
        }
        async with FhirClient(context) as client:
            mock_get = AsyncMock(return_value=_mock_response(bundle))
            with patch.object(client._client, "get", mock_get):
                result = await client.get_medication_administrations("PT-001")
        assert len(result) == 1
        assert isinstance(result[0], MedicationAdministration)
        assert result[0].medicationCodeableConcept.coding[0].code == "309264"


# ---------------------------------------------------------------------------
# Encounter
# ---------------------------------------------------------------------------


class TestGetEncounter:
    async def test_returns_encounter(self, context: FhirContext):
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Encounter",
                        "id": "enc-1",
                        "status": "in-progress",
                        "subject": {"reference": "Patient/PT-001"},
                        "period": {"start": "2026-04-14T17:30:00Z"},
                    }
                }
            ],
        }
        async with FhirClient(context) as client:
            mock_get = AsyncMock(return_value=_mock_response(bundle))
            with patch.object(client._client, "get", mock_get):
                result = await client.get_encounter("PT-001")
        assert isinstance(result, Encounter)
        assert result.id == "enc-1"
        assert result.status == "in-progress"

    async def test_no_encounter_returns_none(self, context: FhirContext):
        bundle = {"resourceType": "Bundle", "type": "searchset"}
        async with FhirClient(context) as client:
            mock_get = AsyncMock(return_value=_mock_response(bundle))
            with patch.object(client._client, "get", mock_get):
                result = await client.get_encounter("PT-001")
        assert result is None


# ---------------------------------------------------------------------------
# Auth header
# ---------------------------------------------------------------------------


class TestAuth:
    async def test_bearer_token_set_when_provided(self, authed_context: FhirContext):
        async with FhirClient(authed_context) as client:
            assert client._client.headers["Authorization"] == "Bearer test-bearer-token"

    async def test_no_auth_header_when_no_token(self, context: FhirContext):
        async with FhirClient(context) as client:
            assert "Authorization" not in client._client.headers


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrors:
    async def test_5xx_raises(self, context: FhirContext):
        async with FhirClient(context) as client:
            mock_get = AsyncMock(
                return_value=_mock_response({"error": "server error"}, status=500)
            )
            with patch.object(client._client, "get", mock_get):
                with pytest.raises(FhirClientError) as exc_info:
                    await client.get_patient("PT-001")
                assert exc_info.value.status_code == 500

    async def test_trailing_slash_stripped(self):
        ctx = FhirContext(url="http://localhost:8080/fhir/")
        async with FhirClient(ctx) as client:
            assert client._base == "http://localhost:8080/fhir"
