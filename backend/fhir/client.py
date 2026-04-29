"""Thin async FHIR R4 client wrapping HAPI endpoints via httpx.

Reads base URL from a FhirContext dataclass (constructed from SHARP headers
upstream). Retries on 5xx with exponential backoff using httpx transport.

Reference: po-community-mcp/python/fhir_context.py, fhir_client.py
"""

from __future__ import annotations

import logging

import httpx

from backend.cache import fhir_cache_get, fhir_cache_key, fhir_cache_set
from backend.fhir.models import (
    Condition,
    Encounter,
    MedicationAdministration,
    MedicationRequest,
    Observation,
    Patient,
)
from backend.schemas import FhirContext  # canonical definition — single source of truth

_logger = logging.getLogger("vigil.fhir.client")


class FhirClientError(Exception):
    """Raised on FHIR client errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def is_fhir_auth_error(exc: BaseException) -> bool:
    """Return True if the exception should trigger the synthetic-FHIR fallback.

    When ``VIGIL_SYNTHETIC_FALLBACK`` is on (demo mode), ANY ``FhirClientError``
    flips us to the bundled PT-007 trajectory so the launchpad always renders
    a clinically coherent response. PO's FHIR proxy returns 401/403 for
    missing-scope reads but also 4xx (e.g. 422) for unrecognised workspace
    paths and 5xx during transient failures — all of these are "we can't
    read FHIR right now" and the demo should degrade gracefully rather than
    surfacing a raw error to a recruiter.

    When the env flag is OFF (production default), behaviour reverts to the
    original narrow 401/403 match so real FHIR-server errors still surface
    through the standard ``fhir_error`` envelope.

    Emits a single ``vigil.fhir.client`` INFO record at the boundary so
    deployed JSON logs reveal exactly which upstream status PO returned —
    regardless of whether we end up on the synthetic-fallback path or the
    raw-error path. Without this we have no observability into PO's
    refusal mode.
    """
    if not isinstance(exc, FhirClientError):
        return False
    # Demo mode: any FHIR error → synthetic.
    import os
    fallback_active = os.environ.get(
        "VIGIL_SYNTHETIC_FALLBACK", ""
    ).lower() in ("1", "true", "yes", "on")
    decision = fallback_active or exc.status_code in (401, 403)
    _logger.info(
        "fhir upstream error evaluated for synthetic fallback",
        extra={
            "_vigil_status_code": exc.status_code,
            # exc.args[0] embeds the URL that 4xx'd in fhir_client._get's
            # message ("FHIR error 403: <body>"); pass through verbatim so
            # log readers can grep for the failing path. Already redacted by
            # the bearer-token filter on the root logger.
            "_vigil_message": str(exc),
            "_vigil_synthetic_fallback_active": fallback_active,
            "_vigil_will_fallback": decision,
        },
    )
    if fallback_active:
        return True
    return exc.status_code in (401, 403)


class FhirClient:
    """Async FHIR R4 client backed by httpx.

    Usage:
        ctx = FhirContext(url="http://localhost:8080/fhir")
        async with FhirClient(ctx) as client:
            patient = await client.get_patient("PT-001")
    """

    def __init__(self, context: FhirContext) -> None:
        # SEC-01: context.url is validated against ALLOWED_FHIR_HOSTS
        # by the SHARP header middleware (B8) before FhirClient is constructed.
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
        """Issue a GET request and return parsed JSON.

        Checks the request-scoped FHIR cache (I4) before hitting HAPI.
        Cache is active only inside a ``fhir_cache_scope()`` context.
        """
        ck = fhir_cache_key(self._base, path, params)
        cached = fhir_cache_get(ck)
        if cached is not None:
            return cached  # type: ignore[return-value]

        url = f"{self._base}/{path}"
        resp = await self._client.get(url, params=params)
        if resp.status_code == 404:
            raise FhirClientError(f"Not found: {url}", status_code=404)
        if resp.status_code >= 400:
            raise FhirClientError(
                f"FHIR error {resp.status_code}: {resp.text[:200]}",
                status_code=resp.status_code,
            )
        result: dict = resp.json()
        fhir_cache_set(ck, result)
        return result

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

    async def get_medication_requests(
        self, patient_id: str, status: str = "active",
    ) -> list[MedicationRequest]:
        """GET /MedicationRequest?patient={id}&status={status}.

        Used by ``flag_treatment_conflicts`` to surface drug *orders* that
        haven't necessarily been administered yet. Defaults to ``active``
        per FHIR R4 — pass ``""`` (or any falsy value) to skip filtering.
        """
        params: dict[str, str] = {"patient": patient_id}
        if status:
            params["status"] = status
        data = await self._get("MedicationRequest", params=params)
        entries = data.get("entry", [])
        return [MedicationRequest.model_validate(e["resource"]) for e in entries]

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

    async def get_all_patients(self, count: int = 50) -> list[Patient]:
        """GET /Patient?_count={count} — list all patients in HAPI."""
        data = await self._get("Patient", params={"_count": str(count)})
        entries = data.get("entry", [])
        return [Patient.model_validate(e["resource"]) for e in entries]

    async def post_resource(
        self, resource_type: str, resource: dict
    ) -> dict:
        """POST a FHIR resource to HAPI and return the created resource.

        Used exclusively by the approve endpoint (B10) to write
        Communication (status=completed) and AuditEvent.  This is the
        ONLY FHIR write path in the stack.
        """
        url = f"{self._base}/{resource_type}"
        resp = await self._client.post(
            url,
            json=resource,
            headers={"Content-Type": "application/fhir+json"},
        )
        if resp.status_code >= 400:
            raise FhirClientError(
                f"FHIR POST {resource_type} error {resp.status_code}: {resp.text[:200]}",
                status_code=resp.status_code,
            )
        return resp.json()

    async def put_resource(
        self, resource_type: str, resource_id: str, resource: dict
    ) -> dict:
        """PUT a FHIR resource at a known id (idempotent upsert).

        Used to ensure the Vigil agent Device exists before approve writes
        Communication / AuditEvent that reference it. Same id every call =
        safe to invoke per request.
        """
        url = f"{self._base}/{resource_type}/{resource_id}"
        resp = await self._client.put(
            url,
            json={**resource, "id": resource_id, "resourceType": resource_type},
            headers={"Content-Type": "application/fhir+json"},
        )
        if resp.status_code >= 400:
            raise FhirClientError(
                f"FHIR PUT {resource_type}/{resource_id} error "
                f"{resp.status_code}: {resp.text[:200]}",
                status_code=resp.status_code,
            )
        return resp.json()
