"""POST .../approve refuses with 409 when source is not 'hapi'.

Defence-in-depth for the dashboard portfolio play: the frontend separately
disables the Approve button when source ≠ hapi, but the backend must also
refuse direct API calls so a stale tab or a curl can't slip a write through
to a non-HAPI workspace. State in the review queue must not change on refusal.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

import backend.api.review_queue as rq
from backend.api.main import app
from backend.api.review_queue import enqueue_alert, get_alert

_VALID_PO_URL = "https://app.promptopinion.ai/api/workspaces/abc12345-6789-4def-9012-3456789abcde/fhir"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Fresh review-queue DB per test so we own the alert state."""
    db_path = tmp_path / "test_refusal.db"
    monkeypatch.setattr(rq, "DB_PATH", db_path)
    rq.init_db()


def _make_alert(patient_id: str = "PT-001") -> str:
    return enqueue_alert(
        patient_id=patient_id,
        severity="critical",
        sbar={"S": "x", "B": "x", "A": "x", "R": "x"},
        narrative="test narrative",
        recipient_role="charge_nurse",
        model_used="test-model",
        communication_draft={"resourceType": "Communication", "status": "in-progress"},
    )


async def test_approve_refused_with_409_when_source_is_po():
    alert_id = _make_alert()
    payload = {"clinician_id": "prac-nurse-17", "note": "looks good"}
    url = f"/api/patients/PT-001/alerts/{alert_id}/approve"
    headers = {
        "X-Vigil-Fhir-Source": "po",
        "X-Vigil-Fhir-Url": _VALID_PO_URL,
        "X-Vigil-Fhir-Token": "tok-refusal-test",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(url, json=payload, headers=headers)

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == (
        "Approve is disabled in po mode. "
        "Switch source to 'hapi' to acknowledge alerts."
    )

    # Critical: the review-queue row is untouched. No claim, no completed
    # transition, no audit row. Status stays at the enqueue default
    # ('in-progress') so a subsequent legitimate HAPI-mode approve still works.
    alert = get_alert(alert_id)
    assert alert is not None
    assert alert["status"] == "in-progress"
    assert alert.get("acknowledged_at") in (None, "")
    assert alert.get("audit_id") in (None, "")


async def test_approve_refused_when_source_invalid_falls_to_hapi_then_proceeds(
    monkeypatch,
):
    """Even with a recognised but URL-invalid PO override, the resolver
    silently falls back to HAPI — so the approve handler does NOT short
    circuit to 409. It proceeds into the queue claim path.

    We don't need to push the request all the way to a successful HAPI write
    here — the existing test_approve_race covers the write path. We only
    need to confirm the request gets *past* the 409 source-refusal gate.
    Indicator: the queue claim transitions the alert to 'in-progress-writing'
    (or to 'completed' if the write succeeds), never staying 'in-progress'.
    """
    alert_id = _make_alert()
    payload = {"clinician_id": "prac-nurse-17", "note": "looks good"}
    url = f"/api/patients/PT-001/alerts/{alert_id}/approve"
    # source=po with bogus URL → resolver falls back to hapi
    headers = {
        "X-Vigil-Fhir-Source": "po",
        "X-Vigil-Fhir-Url": "https://evil.example.com/fhir",
    }

    # Stub HAPI writes to no-ops so we don't need a live server.
    async def _fake_post(self, resource_type, payload):
        return {"resourceType": resource_type, "id": f"fake-{resource_type.lower()}-1"}

    async def _fake_put(self, resource_type, resource_id, resource):
        return {"resourceType": resource_type, "id": resource_id}

    monkeypatch.setattr(
        "backend.fhir.client.FhirClient.post_resource", _fake_post
    )
    monkeypatch.setattr(
        "backend.fhir.client.FhirClient.put_resource", _fake_put
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(url, json=payload, headers=headers)

    # Resolver fell back to hapi → handler did not return the locked 409
    # detail. (Status 200 from full write path, or some other non-source-409
    # if HAPI stub disagrees with the alert shape.)
    if resp.status_code == 409:
        assert "Approve is disabled" not in resp.json().get("detail", "")
    alert = get_alert(alert_id)
    assert alert is not None
    assert alert["status"] != "in-progress", (
        "alert should have advanced past 'in-progress' once the source-refusal "
        "gate is bypassed via fallback to hapi"
    )
