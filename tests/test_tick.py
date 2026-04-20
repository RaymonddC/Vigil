"""Tests for the A2A agent's /tick endpoint and cycle runner (FIX 2 / C2)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.a2a_agent import tick as tick_mod


def _wrap(payload: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


def _triggered_patient_results() -> list[dict]:
    return [
        _wrap(
            {
                "status": "triggered",
                "patient_id": "PT-009",
                "breaches": [{"severity": "red"}],
            }
        ),
        _wrap(
            {
                "status": "triggered",
                "patient_id": "PT-009",
                "risk_band": "high",
                "qsofa_score": 2,
            }
        ),
        _wrap(
            {
                "status": "triggered",
                "patient_id": "PT-009",
                "sepsis_suspected": True,
                "mode": "cdc_ase",
            }
        ),
        _wrap(
            {
                "status": "ok",
                "patient_id": "PT-009",
                "sbar": {
                    "situation": "s",
                    "background": "b",
                    "assessment": "a",
                    "recommendation": "r",
                },
                "narrative": "S: s B: b A: a R: r",
                "severity": "critical",
                "recipient_role": "rapid_response",
                "communication_draft": {
                    "resourceType": "Communication",
                    "status": "in-progress",
                },
                "generated_at": "2026-04-20T12:00:00Z",
                "model_used": "stub/test",
            }
        ),
    ]


def _normal_patient_results() -> list[dict]:
    return [
        _wrap({"status": "ok", "patient_id": "PT-001", "breaches": []}),
        _wrap(
            {
                "status": "ok",
                "patient_id": "PT-001",
                "risk_band": "low",
                "qsofa_score": 0,
            }
        ),
        _wrap(
            {
                "status": "ok",
                "patient_id": "PT-001",
                "sepsis_suspected": False,
                "mode": "cdc_ase",
            }
        ),
    ]


# ---------------------------------------------------------------------------
# run_cycle_for_patient
# ---------------------------------------------------------------------------


class TestRunCycle:
    @pytest.mark.asyncio
    async def test_triggered_enqueues_and_returns_alert_id(
        self, monkeypatch
    ) -> None:
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(side_effect=_triggered_patient_results())

        captured: dict = {}

        def fake_enqueue(*args, **kwargs):
            captured["called"] = True
            return "alert-deadbeef"

        monkeypatch.setattr(
            "backend.a2a_agent.tick.enqueue_alert", fake_enqueue
        )

        out = await tick_mod.run_cycle_for_patient(
            mcp, "PT-009", "http://localhost:8080/fhir"
        )
        assert out["triggered"] is True
        assert out["alert_id"] == "alert-deadbeef"
        assert out["severity"] == "critical"
        assert captured["called"] is True

    @pytest.mark.asyncio
    async def test_normal_returns_not_triggered(self, monkeypatch) -> None:
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(side_effect=_normal_patient_results())

        called = {"n": 0}

        def fake_enqueue(*args, **kwargs):
            called["n"] += 1
            return "should-not-happen"

        monkeypatch.setattr(
            "backend.a2a_agent.tick.enqueue_alert", fake_enqueue
        )

        out = await tick_mod.run_cycle_for_patient(
            mcp, "PT-001", "http://localhost:8080/fhir"
        )
        assert out["triggered"] is False
        assert called["n"] == 0
        assert mcp.call_tool.await_count == 3


# ---------------------------------------------------------------------------
# POST /tick HTTP endpoint
# ---------------------------------------------------------------------------


class TestTickEndpoint:
    def test_tick_returns_triggered_summary(self, monkeypatch) -> None:
        async def fake_runner(mcp, fhir_url):
            return {
                "triggered": True,
                "patients_ticked": 2,
                "alerts_generated": 1,
                "per_patient": [
                    {"triggered": True, "patient_id": "PT-009"},
                    {"triggered": False, "patient_id": "PT-001"},
                ],
            }

        from backend.a2a_agent import app as app_module

        monkeypatch.setattr(
            app_module, "run_cycle_for_all_patients", fake_runner
        )

        client = TestClient(app_module.app)
        resp = client.post("/tick")
        assert resp.status_code == 200
        body = resp.json()
        assert body["triggered"] is True
        assert body["patients_ticked"] == 2
        assert body["alerts_generated"] == 1
        assert "ts" in body
