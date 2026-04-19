"""Vigil Postop Sentinel — A2A agent executor with 7-state machine.

State machine: IDLE → POLLING → SCREENING → RISK_SCORING →
SEPSIS_CHECK → ESCALATING → AWAITING_REVIEW.

Each state calls one MCP tool via VigilMcpClient with SHARP headers
extracted from the incoming A2A message metadata. The agent NEVER
writes to FHIR — it posts drafts to the review queue only.

Reference: BUILD_PLAN.md B7, API_CONTRACTS.md §3–§4,
           PROMPT_OPINION_INTEGRATION.md §3.1
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Message,
    Role,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)

from backend.a2a_agent.fhir_hook import (
    extract_fhir_from_metadata,
    fhir_metadata_to_sharp_headers,
)
from backend.a2a_agent.mcp_client import McpClientError, VigilMcpClient
from backend.schemas import AgentState

logger = logging.getLogger("vigil.a2a.sentinel")


class PostopSentinelExecutor(AgentExecutor):
    """A2A agent executor implementing the Vigil state machine.

    Each `execute()` call runs one full screening cycle:
    POLLING → SCREENING → RISK_SCORING → SEPSIS_CHECK →
    [ESCALATING → AWAITING_REVIEW if triggered] → done.

    Note on exact a2a-sdk class names: This implementation targets
    a2a-sdk >=0.2.0. Class names (AgentExecutor, RequestContext,
    EventQueue) were verified against the installed package at build
    time per API_CONTRACTS.md §3 caveat.
    """

    def __init__(self, mcp: VigilMcpClient) -> None:
        self._mcp = mcp

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Run the full screening state machine for one patient."""
        state = AgentState.IDLE
        task_id = context.task_id or str(uuid.uuid4())
        context_id = context.context_id or str(uuid.uuid4())

        try:
            # --- Extract FHIR context from A2A metadata ---
            metadata = None
            if context.message and context.message.metadata:
                metadata = context.message.metadata

            _, fhir_dict = extract_fhir_from_metadata(metadata)
            if not fhir_dict or not fhir_dict.get("fhirUrl"):
                logger.error("Missing FHIR context in A2A metadata")
                await self._emit_status(
                    event_queue, task_id, context_id,
                    TaskState.failed,
                    "Missing FHIR context in message metadata. "
                    "Ensure fhir-context metadata is provided.",
                    final=True,
                )
                return

            sharp_headers = fhir_metadata_to_sharp_headers(fhir_dict)
            patient_id = fhir_dict.get("patientId", "unknown")
            logger.info(
                "Sentinel cycle starting",
                extra={"patient_id": patient_id, "state": state},
            )

            # --- POLLING → SCREENING ---
            state = AgentState.POLLING
            await self._emit_status(
                event_queue, task_id, context_id,
                TaskState.working,
                f"[{state}] Starting screening cycle for {patient_id}",
            )

            state = AgentState.SCREENING
            await self._emit_status(
                event_queue, task_id, context_id,
                TaskState.working,
                f"[{state}] Running MEWT vital threshold screen",
            )
            screen_result = await self._mcp.call_tool(
                "screen_vital_thresholds",
                arguments={"patient_id": patient_id},
                sharp_headers=sharp_headers,
            )
            logger.info(
                "Screening complete",
                extra={
                    "patient_id": patient_id,
                    "screen_status": _safe_get(screen_result, "status"),
                },
            )

            # --- RISK_SCORING ---
            state = AgentState.RISK_SCORING
            await self._emit_status(
                event_queue, task_id, context_id,
                TaskState.working,
                f"[{state}] Computing qSOFA + composite trend score",
            )
            risk_result = await self._mcp.call_tool(
                "score_deterioration_risk",
                arguments={"patient_id": patient_id},
                sharp_headers=sharp_headers,
            )
            logger.info(
                "Risk scoring complete",
                extra={
                    "patient_id": patient_id,
                    "risk_band": _safe_get(risk_result, "risk_band"),
                },
            )

            # --- SEPSIS_CHECK ---
            state = AgentState.SEPSIS_CHECK
            await self._emit_status(
                event_queue, task_id, context_id,
                TaskState.working,
                f"[{state}] Running CDC Adult Sepsis Event screen",
            )
            sepsis_result = await self._mcp.call_tool(
                "flag_sepsis_onset",
                arguments={"patient_id": patient_id},
                sharp_headers=sharp_headers,
            )
            logger.info(
                "Sepsis check complete",
                extra={
                    "patient_id": patient_id,
                    "sepsis_suspected": _safe_get(
                        sepsis_result, "sepsis_suspected"
                    ),
                },
            )

            # --- Decide: escalate or normal ---
            screen_triggered = (
                _safe_get(screen_result, "status") == "triggered"
            )
            sepsis_triggered = _safe_get(
                sepsis_result, "sepsis_suspected"
            ) is True
            risk_high = _safe_get(risk_result, "risk_band") in (
                "moderate",
                "high",
            )

            if not (screen_triggered or sepsis_triggered or risk_high):
                # NORMAL — no escalation needed
                state = AgentState.IDLE
                logger.info(
                    "Screening cycle complete — NORMAL",
                    extra={"patient_id": patient_id},
                )
                await self._emit_status(
                    event_queue, task_id, context_id,
                    TaskState.completed,
                    f"[{state}] All screens normal for {patient_id}. "
                    "No escalation required.",
                    final=True,
                )
                return

            # --- ESCALATING ---
            state = AgentState.ESCALATING
            await self._emit_status(
                event_queue, task_id, context_id,
                TaskState.working,
                f"[{state}] Generating SBAR escalation note",
            )
            escalation_result = await self._mcp.call_tool(
                "generate_escalation_note",
                arguments={
                    "patient_id": patient_id,
                    "vitals_result": screen_result,
                    "risk_result": risk_result,
                    "sepsis_result": sepsis_result,
                    "recipient_role": (
                        "rapid_response"
                        if sepsis_triggered
                        else "charge_nurse"
                    ),
                },
                sharp_headers=sharp_headers,
            )
            logger.info(
                "Escalation note generated",
                extra={
                    "patient_id": patient_id,
                    "severity": _safe_get(escalation_result, "severity"),
                    "model_used": _safe_get(
                        escalation_result, "model_used"
                    ),
                },
            )

            # --- AWAITING_REVIEW ---
            state = AgentState.AWAITING_REVIEW
            narrative = _safe_get(escalation_result, "narrative") or ""
            severity = _safe_get(escalation_result, "severity") or "info"

            summary = (
                f"[{state}] ALERT for {patient_id} "
                f"(severity={severity}). "
                "Draft posted to review queue. "
                "Agent does NOT write to FHIR — "
                "awaiting clinician approval.\n\n"
                f"{narrative}"
            )

            logger.info(
                "Sentinel cycle complete — ESCALATED",
                extra={
                    "patient_id": patient_id,
                    "severity": severity,
                    "state": state,
                },
            )

            await self._emit_status(
                event_queue, task_id, context_id,
                TaskState.completed,
                summary,
                final=True,
            )

        except McpClientError as e:
            logger.error(
                "MCP tool call failed",
                extra={
                    "state": state,
                    "error": str(e),
                },
            )
            await self._emit_status(
                event_queue, task_id, context_id,
                TaskState.failed,
                f"[{state}] MCP tool error: {e}",
                final=True,
            )

        except Exception as e:
            logger.exception(
                "Unexpected error in sentinel executor",
                extra={"state": state},
            )
            await self._emit_status(
                event_queue, task_id, context_id,
                TaskState.failed,
                f"[{state}] Internal error: {e}",
                final=True,
            )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Handle cancellation request."""
        task_id = context.task_id or str(uuid.uuid4())
        context_id = context.context_id or str(uuid.uuid4())
        await self._emit_status(
            event_queue, task_id, context_id,
            TaskState.canceled,
            "Sentinel cycle canceled by request.",
            final=True,
        )

    # ---------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------

    async def _emit_status(
        self,
        event_queue: EventQueue,
        task_id: str,
        context_id: str,
        state: TaskState,
        text: str,
        final: bool = False,
    ) -> None:
        """Emit a Task event with a status message."""
        task = Task(
            id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=state,
                message=Message(
                    message_id=str(uuid.uuid4()),
                    role=Role.agent,
                    parts=[TextPart(text=text)],
                ),
            ),
        )
        await event_queue.enqueue_event(task)


def _safe_get(data: Any, key: str) -> Any:
    """Safely get a key from a dict-like result (may be nested JSON)."""
    if isinstance(data, dict):
        return data.get(key)
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            if isinstance(parsed, dict):
                return parsed.get(key)
        except (json.JSONDecodeError, TypeError):
            pass
    return None
