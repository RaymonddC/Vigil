"""Tests for PostopSentinelExecutor — A2A agent state machine.

Covers FIX 1 (C1): the AWAITING_REVIEW state must persist the SBAR draft to
the SQLite review queue via ``enqueue_alert`` so ``/api/alerts`` and
``/api/patients/{id}/alerts/latest`` have something to return.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.a2a_agent.sentinel import (
    PostopSentinelExecutor,
    _unwrap_tool_result,
)

PATIENT_ID = "PT-009"
FHIR_URL = "http://localhost:8080/fhir"


def _fhir_metadata() -> dict:
    return {
        "fhir-context": {
            "fhirUrl": FHIR_URL,
            "fhirToken": None,
            "patientId": PATIENT_ID,
        }
    }


def _mcp_text_result(payload: dict) -> dict:
    """Wrap a payload as an MCP tools/call result (content[0].text)."""
    return {
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "isError": False,
    }


def _escalation_payload() -> dict:
    return {
        "status": "ok",
        "patient_id": PATIENT_ID,
        "sbar": {
            "situation": "Postop sepsis suspected.",
            "background": "C-section day 1, chorioamnionitis.",
            "assessment": "qSOFA=2, lactate 4.2, SBP 84.",
            "recommendation": "Activate rapid response.",
        },
        "narrative": "S: ... B: ... A: ... R: ...",
        "severity": "critical",
        "recipient_role": "rapid_response",
        "communication_draft": {
            "resourceType": "Communication",
            "status": "in-progress",
            "priority": "urgent",
            "subject": {"reference": f"Patient/{PATIENT_ID}"},
        },
        "generated_at": datetime.now(UTC).isoformat(),
        "model_used": "stub/test",
    }


# ---------------------------------------------------------------------------
# _unwrap_tool_result: shape coverage
# ---------------------------------------------------------------------------


class TestUnwrapToolResult:
    def test_mcp_content_wrapped(self) -> None:
        wrapped = _mcp_text_result({"severity": "critical"})
        assert _unwrap_tool_result(wrapped) == {"severity": "critical"}

    def test_plain_dict_passthrough(self) -> None:
        assert _unwrap_tool_result({"severity": "info"}) == {"severity": "info"}

    def test_json_string(self) -> None:
        assert _unwrap_tool_result('{"a": 1}') == {"a": 1}

    def test_malformed_returns_empty(self) -> None:
        assert _unwrap_tool_result("not-json") == {}
        assert _unwrap_tool_result(None) == {}
        assert _unwrap_tool_result(12345) == {}


# ---------------------------------------------------------------------------
# Execute: triggered path enqueues an alert
# ---------------------------------------------------------------------------


class TestSentinelExecute:
    @pytest.mark.asyncio
    async def test_escalation_enqueues_alert(self, monkeypatch) -> None:
        """When screening triggers, AWAITING_REVIEW must persist to SQLite."""
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            side_effect=[
                _mcp_text_result(
                    {
                        "status": "triggered",
                        "patient_id": PATIENT_ID,
                        "breaches": [{"severity": "red"}],
                    }
                ),
                _mcp_text_result(
                    {
                        "status": "triggered",
                        "patient_id": PATIENT_ID,
                        "risk_band": "high",
                        "qsofa_score": 2,
                    }
                ),
                _mcp_text_result(
                    {
                        "status": "triggered",
                        "patient_id": PATIENT_ID,
                        "sepsis_suspected": True,
                        "mode": "cdc_ase",
                    }
                ),
                _mcp_text_result(_escalation_payload()),
            ]
        )

        captured: dict = {}

        def fake_enqueue(
            patient_id,
            severity,
            sbar,
            narrative,
            recipient_role,
            model_used,
            communication_draft,
        ):
            captured.update(
                patient_id=patient_id,
                severity=severity,
                sbar=sbar,
                narrative=narrative,
                recipient_role=recipient_role,
                model_used=model_used,
                communication_draft=communication_draft,
            )
            return "alert-abc12345"

        monkeypatch.setattr(
            "backend.a2a_agent.sentinel.enqueue_alert", fake_enqueue
        )

        executor = PostopSentinelExecutor(mcp=mcp)

        # Minimal RequestContext + EventQueue stand-ins
        ctx = MagicMock()
        ctx.task_id = "task-1"
        ctx.context_id = "ctx-1"
        ctx.message = MagicMock()
        ctx.message.metadata = _fhir_metadata()

        event_queue = MagicMock()
        event_queue.enqueue_event = AsyncMock()

        await executor.execute(ctx, event_queue)

        # enqueue_alert was called with the fields from the escalation payload
        assert captured["patient_id"] == PATIENT_ID
        assert captured["severity"] == "critical"
        assert captured["recipient_role"] == "rapid_response"
        assert captured["model_used"] == "stub/test"
        assert captured["sbar"]["situation"] == "Postop sepsis suspected."
        assert captured["communication_draft"]["resourceType"] == "Communication"

        # Final event carries alert_id in message metadata
        final_call = event_queue.enqueue_event.call_args_list[-1]
        task = final_call.args[0]
        assert task.status.message.metadata["alert_id"] == "alert-abc12345"
        assert task.status.message.metadata["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_normal_path_does_not_enqueue(self, monkeypatch) -> None:
        """If nothing triggers, enqueue_alert must not be called."""
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            side_effect=[
                _mcp_text_result(
                    {"status": "ok", "patient_id": PATIENT_ID, "breaches": []}
                ),
                _mcp_text_result(
                    {
                        "status": "ok",
                        "patient_id": PATIENT_ID,
                        "risk_band": "low",
                        "qsofa_score": 0,
                    }
                ),
                _mcp_text_result(
                    {
                        "status": "ok",
                        "patient_id": PATIENT_ID,
                        "sepsis_suspected": False,
                        "mode": "cdc_ase",
                    }
                ),
            ]
        )

        called = False

        def fake_enqueue(*args, **kwargs):
            nonlocal called
            called = True
            return "alert-should-not-happen"

        monkeypatch.setattr(
            "backend.a2a_agent.sentinel.enqueue_alert", fake_enqueue
        )

        executor = PostopSentinelExecutor(mcp=mcp)
        ctx = MagicMock()
        ctx.task_id = "task-2"
        ctx.context_id = "ctx-2"
        ctx.message = MagicMock()
        ctx.message.metadata = _fhir_metadata()
        event_queue = MagicMock()
        event_queue.enqueue_event = AsyncMock()

        await executor.execute(ctx, event_queue)
        assert called is False
        # only 3 MCP calls (no escalation)
        assert mcp.call_tool.await_count == 3
