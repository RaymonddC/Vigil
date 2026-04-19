"""Thin async FHIR R4 client wrapping HAPI endpoints via httpx.

Reads base URL from a FhirContext dataclass (constructed from SHARP headers
upstream). Retries on 5xx with exponential backoff using httpx transport.

Reference: po-community-mcp/python/fhir_context.py, fhir_client.py
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from backend.fhir.models import (
    Condition,
    Encounter,
    MedicationAdministration,
    Observation,
    Patient,
)


@dataclass
class FhirContext:
    """FHIR server connection info, constructed from SHARP headers.

    Source: po-community-mcp/python/fhir_context.py
    """

    url: str  # Base URL, e.g. "http://localhost:8080/fhir"
    token: str | None = None  # Bearer token; None for unauth HAPI in dev


class FhirClientError(Exception):
    """Raised on FHIR client errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class FhirClient:
    """Async FHIR R4 client backed by httpx.

    Usage:
        ctx = FhirContext(url="http://localhost:8080/fhir")
        async with FhirClient(ctx) as client:
            patient = await client.get_patient("PT-001")
    """

    def __init__(self, context: FhirContext) -> None:
        self._context = context
        self._base = context.url.rstrip("/")
        # Retry transport: retry on 5xx with exponential backoff
        transport = httpx.AsyncHTTPTransport(retries=3)
        headers: dict[str, str] = {
            "Accept": "application/fhir+json",
        }
        if context.token:
            headers["Authorization"] = f"Bearer {context.token}"
        self._client = httpx.AsyncClient(
            transport=transport,
            headers=headers,
            timeout=httpx.Timeout(30.0),
        )

    async def __aenter__(self) -> FhirClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, str] | None = None) -> dict:
        """Issue a GET request and return parsed JSON."""
        url = f"{self._base}/{path}"
        resp = await self._client.get(url, params=params)
        if resp.status_code == 404:
            raise FhirClientError(f"Not found: {url}", status_code=404)
        if resp.status_code >= 400:
            raise FhirClientError(
                f"FHIR error {resp.status_code}: {resp.text[:200]}",
                status_code=resp.status_code,
            )
        return resp.json()

    async def get_patient(self, patient_id: str) -> Patient:
        """GET /Patient/{id}."""
        data = await self._get(f"Patient/{patient_id}")
        return Patient.model_validate(data)

    async def get_observations(
        self,
        patient_id: str,
        category: str | None = None,
        since: str | None = None,
        count: int = 100,
    ) -> list[Observation]:
        """GET /Observation?patient={id}&category=...&_sort=-date&_count=...

        Args:
            patient_id: FHIR Patient.id.
            category: Filter by category (e.g. "vital-signs", "laboratory").
            since: ISO datetime string for date lower bound.
            count: Maximum number of results.
        """
        params: dict[str, str] = {
            "patient": patient_id,
            "_sort": "-date",
            "_count": str(count),
        }
        if category:
            params["category"] = category
        if since:
            params["date"] = f"ge{since}"

        data = await self._get("Observation", params=params)
        entries = data.get("entry", [])
        return [Observation.model_validate(e["resource"]) for e in entries]

    async def get_conditions(self, patient_id: str) -> list[Condition]:
        """GET /Condition?patient={id}."""
        data = await self._get("Condition", params={"patient": patient_id})
        entries = data.get("entry", [])
        return [Condition.model_validate(e["resource"]) for e in entries]

    async def get_medication_administrations(
        self, patient_id: str
    ) -> list[MedicationAdministration]:
        """GET /MedicationAdministration?patient={id}."""
        data = await self._get(
            "MedicationAdministration", params={"patient": patient_id}
        )
        entries = data.get("entry", [])
        return [MedicationAdministration.model_validate(e["resource"]) for e in entries]

    async def get_encounter(self, patient_id: str) -> Encounter | None:
        """GET /Encounter?patient={id}&status=in-progress (latest active).

        Returns None if no active encounter found.
        """
        data = await self._get(
            "Encounter",
            params={
                "patient": patient_id,
                "status": "in-progress",
                "_sort": "-date",
                "_count": "1",
            },
        )
        entries = data.get("entry", [])
        if not entries:
            return None
        return Encounter.model_validate(entries[0]["resource"])
