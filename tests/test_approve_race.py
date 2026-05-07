"""Tests: concurrent approve requests are serialized by atomic DB claim.

Two simultaneous approves on the same alert must produce exactly one 200 and
one 409 — and HAPI must receive exactly two POST calls (Communication + AuditEvent
for the winner only; the loser returns 409 before touching HAPI).
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

import backend.api.review_queue as rq
from backend.api.main import app
from backend.api.review_queue import claim_alert_for_writing, enqueue_alert

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Redirect the review queue to a fresh temp SQLite DB for each test."""
    db_path = tmp_path / "test_review.db"
    monkeypatch.setattr(rq, "DB_PATH", db_path)
    rq.init_db()


def _make_alert(patient_id: str = "PT-001") -> str:
    return enqueue_alert(
        patient_id=patient_id,
        severity="critical",
        sbar={"S": "x", "B": "x", "A": "x", "R": "x"},
        narrative="test narrative",
        recipient_role="nurse",
        model_used="test-model",
        communication_draft={"resourceType": "Communication", "status": "in-progress"},
    )


# ---------------------------------------------------------------------------
# Unit: claim_alert_for_writing serializes concurrent callers
# ---------------------------------------------------------------------------


async def test_claim_is_exclusive():
    """Concurrent claims on one alert: exactly one wins, the other gets None."""
    alert_id = _make_alert()

    results = await asyncio.gather(
        asyncio.to_thread(claim_alert_for_writing, alert_id),
        asyncio.to_thread(claim_alert_for_writing, alert_id),
    )

    wins = [r for r in results if r is not None]
    losses = [r for r in results if r is None]
    assert len(wins) == 1, "exactly one thread should claim the alert"
    assert len(losses) == 1, "exactly one thread should find the alert already claimed"
    assert wins[0]["status"] == "in-progress-writing"


async def test_claim_returns_none_for_unknown_alert():
    assert claim_alert_for_writing("no-such-id") is None


async def test_claim_returns_none_when_already_completed():
    from backend.api.review_queue import approve_alert

    alert_id = _make_alert()
    claim_alert_for_writing(alert_id)  # transition to in-progress-writing
    approve_alert(alert_id, "prac-1", "note", "audit-1")

    assert claim_alert_for_writing(alert_id) is None


# ---------------------------------------------------------------------------
# Integration: concurrent HTTP approves produce 200 + 409, one HAPI POST
# ---------------------------------------------------------------------------


async def test_concurrent_approves_one_wins_one_409():
    alert_id = _make_alert()
    hapi_calls: list[str] = []

    async def _fake_post(self, resource_type: str, payload: dict) -> dict:
        hapi_calls.append(resource_type)
        return {"resourceType": resource_type, "id": f"fake-{resource_type.lower()}-1"}

    async def _fake_put(
        self, resource_type: str, resource_id: str, resource: dict
    ) -> dict:
        # _ensure_vigil_referenced_resources PUTs the Vigil Device and
        # PractitionerRole idempotently before the Communication POST (HAPI-1094
        # referential integrity). Not part of this test's race assertions — we
        # only care about POST call counts — so short-circuit to a no-op.
        return {"resourceType": resource_type, "id": resource_id}

    payload = {"clinician_id": "prac-nurse-17", "note": "looks good"}
    url = f"/api/patients/PT-001/alerts/{alert_id}/approve"

    with (
        patch("backend.fhir.client.FhirClient.post_resource", new=_fake_post),
        patch("backend.fhir.client.FhirClient.put_resource", new=_fake_put),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r1, r2 = await asyncio.gather(
                client.post(url, json=payload),
                client.post(url, json=payload),
            )

    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [200, 409], f"expected [200, 409], got {statuses}"

    # Winner posts Communication + Provenance + AuditEvent; loser
    # never reaches HAPI. Provenance is the new attestation resource
    # (Vigil agent author + clinician verifier + AgentCard hash) added
    # for hospital procurement / FDA SaMD review readiness.
    assert len(hapi_calls) == 3, f"expected 3 HAPI calls, got {hapi_calls}"
    assert "Communication" in hapi_calls
    assert "Provenance" in hapi_calls
    assert "AuditEvent" in hapi_calls
