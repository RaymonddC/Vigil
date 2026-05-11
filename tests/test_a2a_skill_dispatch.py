"""Tests for A2A skill dispatch — slice A.

Verifies that the A2A executor:

  1. Resolves an inbound message to the right skill (metadata first,
     keyword fallback).
  2. Dispatches each skill to the correct MCP tool(s).
  3. Returns chat-friendly text that completes the task with
     ``TaskState.completed`` even on precondition failures (no
     ``TaskState.failed`` for missing patient_id, MCP errors, etc.).
  4. Does NOT enqueue to the SQLite review queue from
     ``vigil.draft_sbar`` — Option 3 puts the human-in-the-loop on
     Prompt Opinion's general chat instead.

Mirrors the style of ``tests/test_sharp_compliance.py`` and
``tests/test_sentinel.py``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from a2a.types import TaskState

from backend.a2a_agent.mcp_client import McpClientError
from backend.a2a_agent.sentinel import PostopSentinelExecutor
from backend.a2a_agent.skill_router import (
    DEFAULT_SKILL,
    SkillId,
    resolve_skill,
)

PATIENT_ID = "PT-007"
FHIR_URL = "http://localhost:8080/fhir"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fhir_metadata(patient_id: str | None = PATIENT_ID) -> dict:
    return {
        "fhir-context": {
            "fhirUrl": FHIR_URL,
            "fhirToken": None,
            "patientId": patient_id,
        }
    }


def _mcp_text(payload: dict) -> dict:
    """Wrap a payload as an MCP tools/call result."""
    return {
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "isError": False,
    }


def _make_message(
    text: str = "",
    metadata: dict | None = None,
    fhir_metadata: dict | None = None,
) -> MagicMock:
    """Build a Message-like mock with parts[*].text + metadata."""
    msg = MagicMock()
    part = MagicMock()
    part.text = text
    msg.parts = [part]
    combined: dict = {}
    if fhir_metadata is not None:
        combined.update(fhir_metadata)
    if metadata:
        combined.update(metadata)
    msg.metadata = combined or None
    return msg


def _make_context(message: MagicMock) -> MagicMock:
    ctx = MagicMock()
    ctx.task_id = "task-1"
    ctx.context_id = "ctx-1"
    ctx.message = message
    return ctx


def _make_event_queue() -> MagicMock:
    eq = MagicMock()
    eq.enqueue_event = AsyncMock()
    return eq


def _final_task(event_queue: MagicMock):
    """Return the Task object emitted on the last enqueue_event call."""
    return event_queue.enqueue_event.call_args_list[-1].args[0]


def _final_text(event_queue: MagicMock) -> str:
    task = _final_task(event_queue)
    return task.status.message.parts[0].root.text


# ---------------------------------------------------------------------------
# Skill resolution — metadata + keyword routing
# ---------------------------------------------------------------------------


class TestResolveSkill:
    def test_metadata_skill_id_overrides_text(self) -> None:
        """A skill_id in metadata wins even when text says something else."""
        msg = _make_message(
            text="please draft an SBAR",  # would map to draft_sbar
            metadata={"skill_id": SkillId.CHECK_SEPSIS.value},
        )
        assert resolve_skill(msg) is SkillId.CHECK_SEPSIS

    def test_metadata_skillId_camelcase_accepted(self) -> None:
        msg = _make_message(
            text="anything", metadata={"skillId": SkillId.SCORE_RISK.value}
        )
        assert resolve_skill(msg) is SkillId.SCORE_RISK

    def test_metadata_bare_skill_key_accepted(self) -> None:
        msg = _make_message(
            text="anything", metadata={"skill": SkillId.SCREEN_VITALS.value}
        )
        assert resolve_skill(msg) is SkillId.SCREEN_VITALS

    def test_metadata_unknown_skill_falls_through_to_keywords(self) -> None:
        msg = _make_message(
            text="check sepsis please",
            metadata={"skill_id": "vigil.does_not_exist"},
        )
        assert resolve_skill(msg) is SkillId.CHECK_SEPSIS

    def test_keyword_sepsis(self) -> None:
        msg = _make_message(text="run a sepsis screen")
        assert resolve_skill(msg) is SkillId.CHECK_SEPSIS

    def test_keyword_sbar(self) -> None:
        msg = _make_message(text="draft an SBAR for handoff")
        assert resolve_skill(msg) is SkillId.DRAFT_SBAR

    def test_keyword_risk(self) -> None:
        # NEWS2 is now its own skill — generic ``risk``/``qsofa``
        # keywords still route to SCORE_RISK.
        msg = _make_message(text="what's the qsofa risk")
        assert resolve_skill(msg) is SkillId.SCORE_RISK

    def test_keyword_vitals(self) -> None:
        msg = _make_message(text="screen the vitals")
        assert resolve_skill(msg) is SkillId.SCREEN_VITALS

    def test_keyword_watch(self) -> None:
        msg = _make_message(text="start watching this patient")
        assert resolve_skill(msg) is SkillId.START_WATCHING

    def test_no_match_falls_back_to_default(self) -> None:
        msg = _make_message(text="totally unrelated request about lunch")
        assert resolve_skill(msg) is DEFAULT_SKILL is SkillId.SCREEN_VITALS

    def test_empty_text_falls_back_to_default(self) -> None:
        msg = _make_message(text="")
        assert resolve_skill(msg) is SkillId.SCREEN_VITALS

    def test_part_with_root_text_supported(self) -> None:
        """Real wire-parsed parts expose text via .root.text."""
        msg = MagicMock()
        part = MagicMock()
        # Simulate the RootModel — no .text directly, only .root.text.
        part.text = None
        part.root = MagicMock()
        part.root.text = "please check sepsis"
        msg.parts = [part]
        msg.metadata = None
        assert resolve_skill(msg) is SkillId.CHECK_SEPSIS


# ---------------------------------------------------------------------------
# Per-skill dispatch — verify the right MCP tool is called and the text
# emitted on the final event references the patient.
# ---------------------------------------------------------------------------


class TestSkillDispatch:
    @pytest.mark.asyncio
    async def test_screen_vitals_calls_screen_tool(self) -> None:
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value=_mcp_text(
                {
                    "status": "ok",
                    "patient_id": PATIENT_ID,
                    "trajectory": "postop",
                    "breaches": [],
                    "scanned_count": 14,
                    "window_start": "2026-04-15T08:00:00Z",
                    "window_end": "2026-04-15T12:00:00Z",
                }
            )
        )
        executor = PostopSentinelExecutor(mcp=mcp)
        ctx = _make_context(
            _make_message(
                text="screen this patient",
                fhir_metadata=_fhir_metadata(),
            )
        )
        event_queue = _make_event_queue()

        await executor.execute(ctx, event_queue)

        # Exactly one MCP call, to the vital-screen tool
        mcp.call_tool.assert_awaited_once()
        called_tool = mcp.call_tool.await_args.args[0]
        assert called_tool == "screen_vital_thresholds"

        task = _final_task(event_queue)
        assert task.status.state is TaskState.completed
        text = _final_text(event_queue)
        assert "Vital screen" in text
        # Reply is patient-context-aware: PO already shows the selected
        # patient in the chat header, so the body focuses on the clinical
        # finding rather than echoing the ID. Either CLEAR or TRIGGERED
        # plus a recommended action must appear.
        assert "CLEAR" in text or "TRIGGERED" in text
        assert "Action" in text

    @pytest.mark.asyncio
    async def test_score_risk_calls_risk_tool(self) -> None:
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value=_mcp_text(
                {
                    "status": "triggered",
                    "patient_id": PATIENT_ID,
                    "qsofa_score": 2,
                    "qsofa_components": {
                        "rr_ge_22": True,
                        "sbp_le_100": True,
                        "altered_mental": False,
                    },
                    "composite_risk": 0.71,
                    "risk_band": "high",
                    "rationale": "qSOFA=2 meets sepsis screen.",
                    "contributing_conditions": ["44054006 Type 2 diabetes"],
                }
            )
        )
        executor = PostopSentinelExecutor(mcp=mcp)
        ctx = _make_context(
            _make_message(
                text="score the qsofa risk", fhir_metadata=_fhir_metadata()
            )
        )
        event_queue = _make_event_queue()

        await executor.execute(ctx, event_queue)

        mcp.call_tool.assert_awaited_once()
        assert (
            mcp.call_tool.await_args.args[0] == "score_deterioration_risk"
        )
        text = _final_text(event_queue)
        # New layout uses an uppercase band badge ("HIGH — escalate now")
        # and prints qSOFA without backticks for chat readability.
        assert "HIGH" in text
        assert "qSOFA **2 / 3**" in text

    @pytest.mark.asyncio
    async def test_check_sepsis_calls_sepsis_tool(self) -> None:
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value=_mcp_text(
                {
                    "status": "triggered",
                    "patient_id": PATIENT_ID,
                    "sepsis_suspected": True,
                    "mode": "cdc_ase",
                    "criteria_met": [
                        "presumed infection (antibiotic started)",
                        "organ dysfunction: lactate 2.4 mmol/L",
                    ],
                    "onset_estimate": "2026-04-15T10:30:00Z",
                    "evidence": {"abx_code": "J01DD04"},
                }
            )
        )
        executor = PostopSentinelExecutor(mcp=mcp)
        ctx = _make_context(
            _make_message(
                text="check for sepsis",
                fhir_metadata=_fhir_metadata(),
            )
        )
        event_queue = _make_event_queue()

        await executor.execute(ctx, event_queue)

        mcp.call_tool.assert_awaited_once()
        assert mcp.call_tool.await_args.args[0] == "flag_sepsis_onset"
        text = _final_text(event_queue)
        assert "SUSPECTED" in text
        assert "presumed infection" in text

    @pytest.mark.asyncio
    async def test_draft_sbar_runs_full_pipeline_no_enqueue(
        self, monkeypatch
    ) -> None:
        """draft_sbar must call all 4 tools but NOT enqueue to SQLite."""
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            side_effect=[
                _mcp_text(
                    {
                        "status": "triggered",
                        "patient_id": PATIENT_ID,
                        "trajectory": "postop",
                        "breaches": [],
                        "scanned_count": 12,
                        "window_start": "2026-04-15T08:00:00Z",
                        "window_end": "2026-04-15T12:00:00Z",
                    }
                ),
                _mcp_text(
                    {
                        "status": "triggered",
                        "patient_id": PATIENT_ID,
                        "qsofa_score": 2,
                        "qsofa_components": {
                            "rr_ge_22": True,
                            "sbp_le_100": True,
                            "altered_mental": False,
                        },
                        "composite_risk": 0.71,
                        "risk_band": "high",
                        "rationale": "qSOFA=2",
                        "contributing_conditions": [],
                    }
                ),
                _mcp_text(
                    {
                        "status": "triggered",
                        "patient_id": PATIENT_ID,
                        "sepsis_suspected": True,
                        "mode": "cdc_ase",
                        "criteria_met": ["organ dysfunction: lactate 2.4"],
                        "onset_estimate": None,
                        "evidence": {},
                    }
                ),
                _mcp_text(
                    {
                        "status": "ok",
                        "patient_id": PATIENT_ID,
                        "sbar": {
                            "situation": "Sepsis suspected.",
                            "background": "Day 1 postop.",
                            "assessment": "qSOFA=2.",
                            "recommendation": "Activate rapid response.",
                        },
                        "narrative": (
                            "S: situation. B: background. "
                            "A: assessment. R: recommendation."
                        ),
                        "severity": "critical",
                        "recipient_role": "rapid_response",
                        "communication_draft": {
                            "resourceType": "Communication"
                        },
                        "generated_at": datetime.now(UTC).isoformat(),
                        "model_used": "stub/test",
                    }
                ),
            ]
        )

        # If anything tries to enqueue, this test fails.
        enqueued = False

        def fail_if_called(*_args, **_kwargs):
            nonlocal enqueued
            enqueued = True
            return "alert-should-not-happen"

        monkeypatch.setattr(
            "backend.api.review_queue.enqueue_alert", fail_if_called
        )

        executor = PostopSentinelExecutor(mcp=mcp)
        ctx = _make_context(
            _make_message(
                text="draft an SBAR for handoff",
                fhir_metadata=_fhir_metadata(),
            )
        )
        event_queue = _make_event_queue()

        await executor.execute(ctx, event_queue)

        assert enqueued is False, (
            "vigil.draft_sbar must not enqueue in Option 3"
        )
        assert mcp.call_tool.await_count == 4
        called_tools = [
            call.args[0] for call in mcp.call_tool.await_args_list
        ]
        assert called_tools == [
            "screen_vital_thresholds",
            "score_deterioration_risk",
            "flag_sepsis_onset",
            "generate_escalation_note",
        ]

        task = _final_task(event_queue)
        assert task.status.state is TaskState.completed
        text = _final_text(event_queue)
        assert "SBAR" in text
        # New layout renders the severity as a clinician-facing badge
        # ("EMERGENCY — page now") and the recipient as plain English
        # ("Rapid Response Team — page immediately"), not the raw enum.
        assert "EMERGENCY" in text
        assert "Rapid Response Team" in text

    @pytest.mark.asyncio
    async def test_start_watching_returns_acknowledgement(self) -> None:
        mcp = MagicMock()
        mcp.call_tool = AsyncMock()  # should not be invoked
        executor = PostopSentinelExecutor(mcp=mcp)
        ctx = _make_context(
            _make_message(
                text="start watching this patient",
                fhir_metadata=_fhir_metadata(),
            )
        )
        event_queue = _make_event_queue()

        await executor.execute(ctx, event_queue)

        mcp.call_tool.assert_not_awaited()
        task = _final_task(event_queue)
        assert task.status.state is TaskState.completed
        text = _final_text(event_queue)
        # New layout shows the clinician-facing watch-active confirmation
        # with the patient id, not the raw env-var name.
        assert "Watch" in text
        assert PATIENT_ID in text


# ---------------------------------------------------------------------------
# Routing edge cases
# ---------------------------------------------------------------------------


class TestExecuteRouting:
    @pytest.mark.asyncio
    async def test_metadata_skill_id_overrides_keyword(self) -> None:
        """Even if text says 'sbar', metadata skill_id wins."""
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value=_mcp_text(
                {
                    "status": "ok",
                    "patient_id": PATIENT_ID,
                    "trajectory": "postop",
                    "breaches": [],
                    "scanned_count": 0,
                    "window_start": "2026-04-15T08:00:00Z",
                    "window_end": "2026-04-15T12:00:00Z",
                }
            )
        )
        executor = PostopSentinelExecutor(mcp=mcp)
        # Text would map to draft_sbar, but metadata says screen_vitals.
        msg = _make_message(
            text="draft an SBAR please",
            metadata={"skill_id": SkillId.SCREEN_VITALS.value},
            fhir_metadata=_fhir_metadata(),
        )
        ctx = _make_context(msg)
        event_queue = _make_event_queue()

        await executor.execute(ctx, event_queue)

        mcp.call_tool.assert_awaited_once()
        assert (
            mcp.call_tool.await_args.args[0] == "screen_vital_thresholds"
        )

    @pytest.mark.asyncio
    async def test_empty_text_defaults_to_screen_vitals(self) -> None:
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value=_mcp_text(
                {
                    "status": "ok",
                    "patient_id": PATIENT_ID,
                    "trajectory": "postop",
                    "breaches": [],
                    "scanned_count": 7,
                    "window_start": "2026-04-15T08:00:00Z",
                    "window_end": "2026-04-15T12:00:00Z",
                }
            )
        )
        executor = PostopSentinelExecutor(mcp=mcp)
        ctx = _make_context(
            _make_message(text="", fhir_metadata=_fhir_metadata())
        )
        event_queue = _make_event_queue()

        await executor.execute(ctx, event_queue)
        assert (
            mcp.call_tool.await_args.args[0] == "screen_vital_thresholds"
        )


# ---------------------------------------------------------------------------
# Friendly failure modes — TaskState.completed, never failed.
# ---------------------------------------------------------------------------


class TestFriendlyFailures:
    @pytest.mark.asyncio
    async def test_missing_patient_id_returns_friendly_completed(self) -> None:
        mcp = MagicMock()
        mcp.call_tool = AsyncMock()
        executor = PostopSentinelExecutor(mcp=mcp)
        ctx = _make_context(
            _make_message(
                text="screen this patient",
                fhir_metadata=_fhir_metadata(patient_id=None),
            )
        )
        event_queue = _make_event_queue()

        await executor.execute(ctx, event_queue)

        mcp.call_tool.assert_not_awaited()
        task = _final_task(event_queue)
        assert task.status.state is TaskState.completed
        text = _final_text(event_queue)
        # Wording updated when cohort-level skills (tick_now / list_recent_alerts
        # / estimate_savings / feedback) were exempted from the patient_id
        # guard. Error text now nudges the clinician toward either picking
        # a patient OR running a ward-level skill.
        assert "no patient" in text.lower() or "pick a patient" in text.lower()

    @pytest.mark.asyncio
    async def test_missing_fhir_url_returns_friendly_completed(self) -> None:
        mcp = MagicMock()
        mcp.call_tool = AsyncMock()
        executor = PostopSentinelExecutor(mcp=mcp)
        # No fhir-context metadata at all.
        ctx = _make_context(_make_message(text="screen vitals"))
        event_queue = _make_event_queue()

        await executor.execute(ctx, event_queue)

        mcp.call_tool.assert_not_awaited()
        task = _final_task(event_queue)
        assert task.status.state is TaskState.completed
        text = _final_text(event_queue)
        assert "FHIR" in text

    @pytest.mark.asyncio
    async def test_mcp_unreachable_returns_friendly_completed(self) -> None:
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            side_effect=McpClientError(
                "screen_vital_thresholds",
                "connection refused",
            )
        )
        executor = PostopSentinelExecutor(mcp=mcp)
        ctx = _make_context(
            _make_message(
                text="screen vitals", fhir_metadata=_fhir_metadata()
            )
        )
        event_queue = _make_event_queue()

        await executor.execute(ctx, event_queue)

        task = _final_task(event_queue)
        assert task.status.state is TaskState.completed
        text = _final_text(event_queue)
        assert "couldn't" in text.lower()
        assert "screen vitals" in text.lower()

    @pytest.mark.asyncio
    async def test_tool_error_envelope_returns_friendly_completed(
        self,
    ) -> None:
        """A tool that returns ``status='fhir_error'`` is a precondition
        failure — surface it as friendly text, not a stack trace."""
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value=_mcp_text(
                {
                    "status": "fhir_error",
                    "message": "HAPI FHIR server unreachable",
                    "detail": {"http_status": 503},
                }
            )
        )
        executor = PostopSentinelExecutor(mcp=mcp)
        ctx = _make_context(
            _make_message(
                text="check sepsis", fhir_metadata=_fhir_metadata()
            )
        )
        event_queue = _make_event_queue()

        await executor.execute(ctx, event_queue)

        task = _final_task(event_queue)
        assert task.status.state is TaskState.completed
        text = _final_text(event_queue)
        assert "HAPI FHIR server unreachable" in text
        assert PATIENT_ID in text


# ---------------------------------------------------------------------------
# Synthetic-fallback disclosure — the agent's chat reply must say so.
# ---------------------------------------------------------------------------


class TestSyntheticFallbackDisclosure:
    """When MCP tool output carries data_source='synthetic_demo', the
    skill handler prefixes the reply with an honest one-liner and
    echoes data_source in A2A response metadata."""

    @pytest.mark.asyncio
    async def test_screen_vitals_disclosure_in_text_and_metadata(self) -> None:
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value=_mcp_text(
                {
                    "status": "ok",
                    "patient_id": PATIENT_ID,
                    "trajectory": "postop",
                    "breaches": [],
                    "scanned_count": 9,
                    "window_start": "2026-04-15T08:00:00Z",
                    "window_end": "2026-04-15T12:00:00Z",
                    "data_source": "synthetic_demo",
                }
            )
        )
        executor = PostopSentinelExecutor(mcp=mcp)
        ctx = _make_context(
            _make_message(text="screen vitals", fhir_metadata=_fhir_metadata())
        )
        event_queue = _make_event_queue()

        await executor.execute(ctx, event_queue)

        text = _final_text(event_queue)
        # Honest one-liner — must reference the demo trajectory.
        assert (
            "demo trajectory" in text.lower()
            or "synthetic" in text.lower()
        )
        # The actual screening result is still present.
        assert "Vital screen" in text

        # Response metadata carries the data_source for downstream consumers.
        task = _final_task(event_queue)
        meta = task.status.message.metadata or {}
        assert meta.get("data_source") == "synthetic_demo"

    @pytest.mark.asyncio
    async def test_check_sepsis_disclosure_in_text(self) -> None:
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value=_mcp_text(
                {
                    "status": "triggered",
                    "patient_id": PATIENT_ID,
                    "sepsis_suspected": True,
                    "mode": "cdc_ase",
                    "criteria_met": ["organ dysfunction: lactate 2.4"],
                    "onset_estimate": None,
                    "evidence": {},
                    "data_source": "synthetic_demo",
                }
            )
        )
        executor = PostopSentinelExecutor(mcp=mcp)
        ctx = _make_context(
            _make_message(text="check sepsis", fhir_metadata=_fhir_metadata())
        )
        event_queue = _make_event_queue()

        await executor.execute(ctx, event_queue)

        text = _final_text(event_queue)
        assert (
            "demo trajectory" in text.lower()
            or "synthetic" in text.lower()
        )
        assert "SUSPECTED" in text

    @pytest.mark.asyncio
    async def test_live_data_does_not_add_disclosure(self) -> None:
        """Live FHIR data must not trigger the synthetic disclosure."""
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value=_mcp_text(
                {
                    "status": "ok",
                    "patient_id": PATIENT_ID,
                    "trajectory": "postop",
                    "breaches": [],
                    "scanned_count": 9,
                    "window_start": "2026-04-15T08:00:00Z",
                    "window_end": "2026-04-15T12:00:00Z",
                    "data_source": "fhir",
                }
            )
        )
        executor = PostopSentinelExecutor(mcp=mcp)
        ctx = _make_context(
            _make_message(text="screen vitals", fhir_metadata=_fhir_metadata())
        )
        event_queue = _make_event_queue()

        await executor.execute(ctx, event_queue)

        text = _final_text(event_queue)
        assert "demo trajectory" not in text.lower()
        assert "synthetic" not in text.lower()

        task = _final_task(event_queue)
        meta = task.status.message.metadata or {}
        assert meta.get("data_source") == "fhir"
