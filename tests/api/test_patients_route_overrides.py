"""GET /api/patients honours the FHIR-source override headers end-to-end.

Monkey-patches ``backend.api.routes.patients.FhirClient`` with a recorder so
we can assert the ``FhirContext`` constructed inside ``list_patients_action``
carries the URL + bearer token that the request announced.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

import backend.api.routes.patients as patients_module
from backend.api.main import app

_VALID_PO_URL = "https://app.promptopinion.ai/api/workspaces/abc12345-6789-4def-9012-3456789abcde/fhir"


class _RecorderFhirClient:
    """Minimal stand-in for ``FhirClient`` — captures the context and stubs
    every method ``list_patients_action`` reaches into."""

    captured: list[tuple[str, str | None]] = []

    def __init__(self, context):
        type(self).captured.append((context.url, context.token))
        self._context = context

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def get_all_patients(self, count: int = 50):
        return []

    async def get_conditions(self, patient_id: str):
        return []


@pytest.fixture(autouse=True)
def _reset_recorder():
    _RecorderFhirClient.captured = []


@pytest.fixture(autouse=True)
def _patch_fhir_client(monkeypatch):
    monkeypatch.setattr(patients_module, "FhirClient", _RecorderFhirClient)


async def test_list_patients_forwards_po_url_and_token():
    headers = {
        "X-Vigil-Fhir-Source": "po",
        "X-Vigil-Fhir-Url": _VALID_PO_URL,
        "X-Vigil-Fhir-Token": "tok-route-test",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/patients", headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"patients": []}
    assert _RecorderFhirClient.captured, "FhirClient was not constructed"
    url, token = _RecorderFhirClient.captured[0]
    assert url == _VALID_PO_URL
    assert token == "tok-route-test"


async def test_list_patients_default_uses_hapi_no_token():
    """No override headers → resolver falls back to the env HAPI URL with
    no bearer token threaded through."""
    from backend.api import main as api_main

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/patients")

    assert resp.status_code == 200, resp.text
    assert _RecorderFhirClient.captured, "FhirClient was not constructed"
    url, token = _RecorderFhirClient.captured[0]
    assert url == api_main.FHIR_BASE_URL
    assert token is None
