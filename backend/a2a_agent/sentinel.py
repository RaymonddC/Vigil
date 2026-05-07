"""Vigil Postop Sentinel — A2A agent executor with skill dispatch.

Inbound A2A messages are routed to one of five clinical skills:

  vigil.screen_vitals  → MEWT vital threshold screen
  vigil.score_risk     → qSOFA + composite trend risk
  vigil.check_sepsis   → CDC Adult Sepsis Event surveillance
  vigil.draft_sbar     → all 3 screens + SBAR escalation note (no enqueue)
  vigil.start_watching → informational; deployment-level loop control

The autonomous polling loop (see ``app.py``) and the historical 7-state
machine still live in the codebase, but the request-response path is the
hackathon submission's primary surface — Prompt Opinion's launchpad chat
invokes one skill at a time and renders the chat-ready text we return.

`vigil.draft_sbar` returns the SBAR text only — it does NOT enqueue to
the SQLite review queue. In Option 3, Prompt Opinion's general chat is
the human-in-the-loop surface; the autonomous loop continues to enqueue
for the dashboard's HITL view.

Reference: docs/A2A_REFACTOR_AUDIT.md, BUILD_PLAN.md B7,
           API_CONTRACTS.md §3–§4, PROMPT_OPINION_INTEGRATION.md §3.1
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
from backend.a2a_agent.skill_router import SkillId, resolve_skill
from backend.mcp_server.synthetic_fallback import (
    SYNTHETIC_DATA_SOURCE,
    synthetic_disclosure,
)

logger = logging.getLogger("vigil.a2a.sentinel")

# Tool-status values that indicate a precondition failure (vs. a clinical
# trigger). ``triggered`` is a clinical signal, not an error.
_TOOL_ERROR_STATUSES = {
    "bad_input",
    "fhir_error",
    "fhir_not_found",
    "llm_error",
}


class PostopSentinelExecutor(AgentExecutor):
    """A2A agent executor implementing skill dispatch.

    Each ``execute()`` call:
      1. Extracts SHARP context from ``message.metadata``.
      2. Resolves the requested skill via :func:`resolve_skill`.
      3. Dispatches to the matching ``_handle_*`` coroutine, which calls
         one or more MCP tools and formats a chat-friendly reply.
      4. Emits a single ``TaskState.completed`` event with the reply text.

    Failure modes (missing FHIR context, MCP unreachable, tool-level error
    envelope) all complete the task with a one-line "I couldn't compute
    X because Y" message rather than raising — Prompt Opinion's general
    chat surfaces the text either way, and a friendly sentence reads
    cleaner than a stack trace.

    Note on a2a-sdk class names: Targets a2a-sdk >=0.2.0. ``AgentExecutor``,
    ``RequestContext``, ``EventQueue`` were verified against the installed
    package per API_CONTRACTS.md §3 caveat.
    """

    def __init__(self, mcp: VigilMcpClient) -> None:
        self._mcp = mcp

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Resolve the inbound skill and dispatch."""
        task_id = context.task_id or str(uuid.uuid4())
        context_id = context.context_id or str(uuid.uuid4())

        # --- Extract FHIR context from A2A metadata ---
        metadata = None
        if context.message and context.message.metadata:
            metadata = context.message.metadata

        _, fhir_dict = extract_fhir_from_metadata(metadata)
        if not fhir_dict or not fhir_dict.get("fhirUrl"):
            logger.warning("Missing FHIR context in A2A metadata")
            await self._emit_completed(
                event_queue, task_id, context_id,
                "I couldn't run any check because the request was missing "
                "FHIR connection context. Please ensure the FHIR-context "
                "extension is enabled on this agent connection.",
            )
            return

        sharp_headers = fhir_metadata_to_sharp_headers(fhir_dict)
        patient_id = fhir_dict.get("patientId")
        if not patient_id:
            logger.warning("Missing patient_id in SHARP context")
            await self._emit_completed(
                event_queue, task_id, context_id,
                "I couldn't run any check because no patient_id was "
                "supplied in the FHIR context. Pick a patient in Prompt "
                "Opinion before invoking this skill.",
            )
            return

        # --- Resolve skill ---
        skill = resolve_skill(context.message)
        logger.info(
            "Dispatching A2A skill",
            extra={"skill": skill.value, "patient_id": patient_id},
        )

        # --- Dispatch ---
        # Each handler returns (chat_text, data_source). Skills that don't
        # call MCP tools (start_watching) use ``LIVE_DATA_SOURCE`` (== "fhir")
        # as a benign default — the env-var-gated synthetic path only fires
        # inside the screening tools.
        text: str
        data_source: str = "fhir"
        try:
            if skill is SkillId.SCREEN_VITALS:
                text, data_source = await self._handle_screen_vitals(
                    sharp_headers, patient_id
                )
            elif skill is SkillId.SCORE_RISK:
                text, data_source = await self._handle_score_risk(
                    sharp_headers, patient_id
                )
            elif skill is SkillId.CHECK_SEPSIS:
                text, data_source = await self._handle_check_sepsis(
                    sharp_headers, patient_id
                )
            elif skill is SkillId.DRAFT_SBAR:
                text, data_source = await self._handle_draft_sbar(
                    sharp_headers, patient_id
                )
            elif skill is SkillId.ASSESS_AKI:
                text, data_source = await self._handle_assess_aki(
                    sharp_headers, patient_id
                )
            elif skill is SkillId.SCORE_NEWS2:
                text, data_source = await self._handle_score_news2(
                    sharp_headers, patient_id
                )
            elif skill is SkillId.ASSESS_PPH:
                text, data_source = await self._handle_assess_pph(
                    sharp_headers, patient_id
                )
            elif skill is SkillId.FLAG_TREATMENT_CONFLICTS:
                text, data_source = await self._handle_flag_treatment_conflicts(
                    sharp_headers, patient_id
                )
            elif skill is SkillId.START_WATCHING:
                text = await self._handle_start_watching(
                    sharp_headers, patient_id
                )
            elif skill is SkillId.LIST_RECENT_ALERTS:
                text = await self._handle_list_recent_alerts()
            elif skill is SkillId.TICK_NOW:
                text = await self._handle_tick_now()
            else:  # pragma: no cover — exhaustive enum dispatch
                text = (
                    f"I don't recognise the skill `{skill}`. "
                    "Try asking me to screen vitals, score risk, "
                    "check sepsis, or draft an SBAR."
                )
        except Exception as e:  # noqa: BLE001 — surface as friendly chat reply
            logger.exception(
                "Unhandled error in skill handler",
                extra={"skill": skill.value, "patient_id": patient_id},
            )
            text = (
                f"I couldn't complete `{skill.value}` for `{patient_id}` "
                f"because of an internal error: {e}."
            )

        await self._emit_completed(
            event_queue, task_id, context_id, text,
            metadata={
                "skill": skill.value,
                "patient_id": patient_id,
                "data_source": data_source,
            },
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
    # Skill handlers — each calls 1+ MCP tools and returns chat text.
    # ---------------------------------------------------------------

    async def _handle_screen_vitals(
        self,
        sharp_headers: dict[str, str],
        patient_id: str,
    ) -> tuple[str, str]:
        """Run screen_vital_thresholds and format the MEWT result.

        Returns ``(chat_text, data_source)`` where ``data_source`` is
        either ``"fhir"`` or ``"synthetic_demo"`` so the dispatch loop
        can echo it in A2A response metadata.
        """
        try:
            raw = await self._mcp.call_tool(
                "screen_vital_thresholds",
                arguments={"patient_id": patient_id},
                sharp_headers=sharp_headers,
            )
        except McpClientError as e:
            return (
                f"I couldn't screen vitals for `{patient_id}` because "
                f"the MCP tool was unreachable: {e}.",
                "fhir",
            )

        data = _unwrap_tool_result(raw)
        err = _tool_error_text(data, patient_id, action="screen vitals")
        if err is not None:
            return err, _data_source(data)

        breaches = data.get("breaches") or []
        scanned = data.get("scanned_count", 0)

        # Render thresholds with natural-language operators ("below 90"
        # rather than "<90") — PO's markdown renderer can otherwise eat
        # the angle brackets as HTML, and the natural form reads aloud
        # cleanly when a clinician scans the chat reply at the bedside.
        def _humanize(threshold: str) -> str:
            t = (threshold or "").strip()
            if t.startswith("<="):
                return f"≤ {t[2:].strip()}"
            if t.startswith(">="):
                return f"≥ {t[2:].strip()}"
            if t.startswith("<"):
                return f"below {t[1:].strip()}"
            if t.startswith(">"):
                return f"above {t[1:].strip()}"
            return t

        # Freshness — clinicians treat a vital-sign reading older than
        # ~30 min on a watched postop patient as stale. Surface the gap
        # explicitly so a stale screen is never silently relied on.
        from datetime import UTC, datetime
        latest_iso = max(
            (b.get("observed_at", "") for b in breaches),
            default=data.get("window_end", ""),
        )
        freshness = ""
        try:
            if latest_iso:
                latest_dt = datetime.fromisoformat(
                    str(latest_iso).replace("Z", "+00:00")
                )
                age_min = int((datetime.now(UTC) - latest_dt).total_seconds() // 60)
                if age_min < 60:
                    freshness = f"Last reading {age_min} min ago."
                else:
                    freshness = (
                        f"Last reading {age_min // 60}h "
                        f"{age_min % 60}m ago — **data may be stale**."
                    )
        except (ValueError, TypeError):
            pass

        if not breaches:
            body = (
                f"### Vital screen — CLEAR\n"
                f"All {scanned} recent observations within MEWT thresholds. "
                f"{freshness}\n\n"
                "**Action**: Continue routine observation schedule."
            ).strip()
            return _with_disclosure(body, data), _data_source(data)

        red_breaches = [b for b in breaches if b.get("severity") == "red"]
        yellow_breaches = [b for b in breaches if b.get("severity") == "yellow"]

        def _line(b: dict) -> str:
            label = b.get("label", "?")
            value = b.get("value", "?")
            unit = (b.get("unit", "") or "").strip()
            thr = _humanize(b.get("threshold", ""))
            tail = f" {unit}" if unit else ""
            return f"- **{label}** {value}{tail} (threshold {thr})"

        # Recommended action — derived from severity per NEWS2 RCP-2017
        # response framework, adapted to MEWT's binary red/yellow scheme.
        # Cite the guideline inline so a clinician scanning the chat reply
        # sees the source of the recommendation without scrolling.
        if red_breaches:
            action = (
                "**Action** *(per NEWS2 RCP-2017 / Subbe MEWS)*: URGENT — "
                "recheck within 15 min, page covering MD or rapid-response "
                "team. Move to hourly observations minimum. Consider qSOFA "
                "/ NEWS2 follow-up; if any further deterioration, escalate "
                "to ICU."
            )
        else:
            action = (
                "**Action** *(per NEWS2 RCP-2017)*: Increase to hourly "
                "observations. RN reassess in 30 min; escalate to MD if "
                "any breach persists or a new red breach develops."
            )

        sections = [
            f"### Vital screen — TRIGGERED ({len(breaches)} breach"
            f"{'es' if len(breaches) != 1 else ''})"
        ]
        if freshness:
            sections.append(freshness)
        sections.append(
            f"Scanned **{scanned}** observation"
            f"{'s' if scanned != 1 else ''} — "
            f"**{len(red_breaches)} red**, **{len(yellow_breaches)} yellow**."
        )
        if red_breaches:
            sections.append("\n**Critical (RED) — escalate now:**")
            sections.extend(_line(b) for b in red_breaches[:6])
        if yellow_breaches:
            sections.append("\n**Concerning (YELLOW):**")
            sections.extend(_line(b) for b in yellow_breaches[:6])
        sections.append("")
        sections.append(action)
        # Chain hint — direct the clinician to the skill that does
        # multivariate trend analysis when they want direction-of-travel
        # rather than a point-in-time threshold breach.
        sections.append(
            "\n*For trend direction across the last few hours, run "
            "`score risk` — it computes qSOFA + composite trend.*"
        )

        body = "\n".join(sections)
        return _with_disclosure(body, data), _data_source(data)

    async def _handle_score_risk(
        self,
        sharp_headers: dict[str, str],
        patient_id: str,
    ) -> tuple[str, str]:
        """Run score_deterioration_risk and format risk band + qSOFA."""
        try:
            raw = await self._mcp.call_tool(
                "score_deterioration_risk",
                arguments={"patient_id": patient_id},
                sharp_headers=sharp_headers,
            )
        except McpClientError as e:
            return (
                f"I couldn't score deterioration risk for `{patient_id}` "
                f"because the MCP tool was unreachable: {e}.",
                "fhir",
            )

        data = _unwrap_tool_result(raw)
        err = _tool_error_text(data, patient_id, action="score risk")
        if err is not None:
            return err, _data_source(data)

        band = (data.get("risk_band") or "unknown").lower()
        qsofa = data.get("qsofa_score")
        qsofa_components = data.get("qsofa_components") or {}
        composite = data.get("composite_risk")
        rationale = data.get("rationale") or "no rationale provided"
        comorbid = data.get("contributing_conditions") or []

        composite_str = (
            f"{composite:.2f}" if isinstance(composite, (int, float))
            else "?"
        )

        # Band badge — converts an abstract score into a clear urgency
        # tier. Mapping aligns with Singer Sepsis-3 (qSOFA ≥2 → high
        # mortality risk) and ward escalation conventions.
        band_badge = {
            "high": "HIGH — escalate now",
            "moderate": "MODERATE — increase surveillance",
            "low": "LOW — routine monitoring",
        }.get(band, f"{band.upper()} — review")

        # Per-band time-to-action — turns "moderate" into a concrete
        # clock the receiving clinician can plan around.
        action = {
            "high": (
                "Continuous monitoring; covering MD or rapid-response "
                "team within **30 min**. Consider ICU consult if "
                "SBP <90 sustained or lactate >2 mmol/L."
            ),
            "moderate": (
                "Hourly observations; MD review within **1 hour**. "
                "Re-score with NEWS2 if any parameter worsens."
            ),
            "low": (
                "Continue routine schedule; recheck in **4 hours** or "
                "sooner if clinical concern."
            ),
        }.get(
            band,
            "Review with covering MD before next round.",
        )

        # qSOFA component check/cross marks (Sepsis-3, JAMA 2016).
        # Letting the clinician audit the AI math is non-negotiable.
        component_labels = [
            ("rr_ge_22", "Resp rate ≥ 22"),
            ("sbp_le_100", "SBP ≤ 100 mmHg"),
            ("altered_mental", "Altered mentation (GCS <15)"),
        ]
        check_lines = [
            f"- {'[x]' if qsofa_components.get(key) else '[ ]'} {label}"
            for key, label in component_labels
        ]

        sections = [
            f"### Deterioration risk — **{band_badge}** "
            f"*(per qSOFA / Sepsis-3 JAMA 2016)*",
            f"qSOFA **{qsofa} / 3** · composite **{composite_str}**",
            "",
            "**qSOFA components:**",
            *check_lines,
        ]
        if comorbid:
            sections.append(
                "\n**Contributing conditions:** "
                + ", ".join(comorbid[:5])
            )
        sections.append(f"\n**Action**: {action}")
        sections.append(f"\n*Rationale:* {rationale}")
        body = "\n".join(sections)
        return _with_disclosure(body, data), _data_source(data)

    async def _handle_check_sepsis(
        self,
        sharp_headers: dict[str, str],
        patient_id: str,
    ) -> tuple[str, str]:
        """Run flag_sepsis_onset and format the CDC ASE evidence."""
        try:
            raw = await self._mcp.call_tool(
                "flag_sepsis_onset",
                arguments={"patient_id": patient_id},
                sharp_headers=sharp_headers,
            )
        except McpClientError as e:
            return (
                f"I couldn't run the sepsis screen for `{patient_id}` "
                f"because the MCP tool was unreachable: {e}.",
                "fhir",
            )

        data = _unwrap_tool_result(raw)
        err = _tool_error_text(data, patient_id, action="check sepsis")
        if err is not None:
            return err, _data_source(data)

        suspected = bool(data.get("sepsis_suspected"))
        mode = data.get("mode", "cdc_ase")
        criteria = data.get("criteria_met") or []
        onset = data.get("onset_estimate")

        if not suspected:
            sections = [
                f"### Sepsis screen — NOT SUSPECTED *(per CDC ASE, mode `{mode}`)*",
            ]
            if criteria:
                sections.append(
                    f"Partial criteria seen ({len(criteria)}): "
                    + "; ".join(criteria[:3])
                    + ". Below the surveillance threshold."
                )
            else:
                sections.append(
                    "No CDC ASE criteria met on the most recent observations."
                )
            sections.append(
                "**Action**: Continue routine observation. Re-screen "
                "automatically on next tick."
            )
            body = "\n".join(sections)
            return _with_disclosure(body, data), _data_source(data)

        # Sepsis-3 1-hour bundle (Surviving Sepsis Campaign 2021) — the
        # single most under-applied checklist in postop wards. Vigil
        # doesn't write orders; this skill surfaces the bundle as a
        # prompt for the receiving clinician to verify item-by-item.
        bundle_items = [
            "Measure lactate; remeasure if initial ≥ 2 mmol/L",
            "Obtain blood cultures BEFORE antibiotics",
            "Administer broad-spectrum antibiotics within 1h",
            "Begin 30 mL/kg crystalloid for hypotension or lactate ≥ 4",
            "Apply vasopressors if MAP < 65 mmHg after fluids",
        ]

        sections = [
            f"### Sepsis screen — SUSPECTED *(per CDC ASE, mode `{mode}`)*",
        ]
        if onset:
            sections.append(f"Estimated onset: **{onset}** UTC.")

        if criteria:
            sections.append("\n**Criteria met:**")
            sections.extend(f"- {c}" for c in criteria[:6])

        sections.append(
            "\n**Sepsis-3 1-hour bundle** *(Surviving Sepsis Campaign 2021 — "
            "verify each before paging back):*"
        )
        sections.extend(f"- [ ] {item}" for item in bundle_items)

        sections.append(
            "\n**Action**: Treat as time-critical. Mortality rises ~7%/hour "
            "of bundle delay (Kumar 2006). Page covering MD now; if no "
            "response in 5 min, activate rapid-response team."
        )
        body = "\n".join(sections)
        return _with_disclosure(body, data), _data_source(data)

    async def _handle_draft_sbar(
        self,
        sharp_headers: dict[str, str],
        patient_id: str,
    ) -> tuple[str, str]:
        """Run all 3 screens + generate_escalation_note. Return SBAR text.

        Does NOT enqueue to the review queue. The autonomous polling loop
        keeps enqueuing; this request-response skill just returns prose,
        because Prompt Opinion's general chat is the HITL surface in
        Option 3.
        """
        # Run the three screens. Any tool error short-circuits to a
        # one-line friendly response.
        try:
            screen_result = await self._mcp.call_tool(
                "screen_vital_thresholds",
                arguments={"patient_id": patient_id},
                sharp_headers=sharp_headers,
            )
            risk_result = await self._mcp.call_tool(
                "score_deterioration_risk",
                arguments={"patient_id": patient_id},
                sharp_headers=sharp_headers,
            )
            sepsis_result = await self._mcp.call_tool(
                "flag_sepsis_onset",
                arguments={"patient_id": patient_id},
                sharp_headers=sharp_headers,
            )
        except McpClientError as e:
            return (
                f"I couldn't draft an SBAR for `{patient_id}` because "
                f"a screening MCP tool was unreachable: {e}.",
                "fhir",
            )

        # Pick a recipient based on whether sepsis fires — same heuristic
        # the autonomous loop has used since B7.
        sepsis_triggered = (
            _safe_get(sepsis_result, "sepsis_suspected") is True
        )
        recipient_role = (
            "rapid_response" if sepsis_triggered else "charge_nurse"
        )

        # Unwrap each upstream result before forwarding — the MCP tool
        # signature expects flat dicts (with ``breaches``, ``qsofa_score``,
        # etc.), not the FastMCP wrapper ``{content: [...], structuredContent}``.
        # Forwarding the wrapper makes the LLM see empty inputs and emit
        # "no breaches / qSOFA 0/3 / unknown" prose regardless of what
        # actually happened upstream.
        unwrapped_vitals = _unwrap_tool_result(screen_result)
        unwrapped_risk = _unwrap_tool_result(risk_result)
        unwrapped_sepsis = _unwrap_tool_result(sepsis_result)

        try:
            escalation_result = await self._mcp.call_tool(
                "generate_escalation_note",
                arguments={
                    "patient_id": patient_id,
                    "vitals_result": unwrapped_vitals,
                    "risk_result": unwrapped_risk,
                    "sepsis_result": unwrapped_sepsis,
                    "recipient_role": recipient_role,
                },
                sharp_headers=sharp_headers,
            )
        except McpClientError as e:
            return (
                f"I couldn't draft an SBAR for `{patient_id}` because "
                f"the escalation-note MCP tool failed: {e}.",
                "fhir",
            )

        data = _unwrap_tool_result(escalation_result)
        err = _tool_error_text(data, patient_id, action="draft an SBAR")
        if err is not None:
            return err, _data_source(data)

        # Synthetic origin propagates from any of the four tool calls —
        # if a single tool fell back, the whole SBAR was generated from
        # synthetic data and the disclosure must say so.
        any_synthetic = any(
            _data_source(_unwrap_tool_result(r)) == SYNTHETIC_DATA_SOURCE
            for r in (
                screen_result,
                risk_result,
                sepsis_result,
                escalation_result,
            )
        )
        data_source = (
            SYNTHETIC_DATA_SOURCE if any_synthetic else "fhir"
        )

        narrative = (data.get("narrative") or "").strip()
        severity = (data.get("severity") or "info").lower()
        resolved_recipient = data.get("recipient_role") or recipient_role
        model_used = data.get("model_used") or "unknown"

        logger.info(
            "SBAR drafted (no enqueue — Option 3 chat is HITL)",
            extra={
                "patient_id": patient_id,
                "severity": severity,
                "model_used": model_used,
                "data_source": data_source,
            },
        )

        # Severity badge — first thing on screen so the reader's eye
        # locks onto urgency before any prose. Maps tool severities to
        # the AHRQ-style ROUTINE / URGENT / EMERGENCY trichotomy
        # clinicians actually use on a paging system.
        badge_map = {
            "critical": "EMERGENCY — page now",
            "emergency": "EMERGENCY — page now",
            "urgent": "URGENT — assessment within 30 min",
            "routine": "ROUTINE — ward review",
            "info": "ROUTINE — ward review",
        }
        badge = badge_map.get(severity, f"{severity.upper()} — escalate")

        # Recipient line in plain English with paging guidance — turns
        # the role enum into something a clinician actually does.
        recipient_text = {
            "rapid_response": (
                "Rapid Response Team — page immediately. "
                "Bedside team should remain with patient."
            ),
            "covering_md": (
                "Covering MD — urgent assessment within 30 min. "
                "Hand off via secure pager."
            ),
            "charge_nurse": (
                "Charge nurse — review at next round, no later than 1h."
            ),
        }.get(resolved_recipient, resolved_recipient)

        # Build the SBAR body. Wrap in a fenced code block so PO renders
        # it monospaced and the clinician can copy-paste straight into
        # the EHR with no manual reformatting.
        if narrative:
            sbar_body = narrative
        else:
            sbar = data.get("sbar") or {}
            sbar_body = "\n".join(
                f"{k[0].upper()}: {sbar.get(k, '').strip() or '—'}"
                for k in (
                    "situation",
                    "background",
                    "assessment",
                    "recommendation",
                )
            )

        sections = [
            f"### SBAR — **{badge}**",
            f"**To:** {recipient_text}",
            "**From:** Vigil postop & postpartum sentinel",
            f"**Patient:** `{patient_id}`",
            "",
            "```",
            sbar_body,
            "```",
        ]
        body = "\n".join(sections)
        if data_source == SYNTHETIC_DATA_SOURCE:
            body = f"{synthetic_disclosure(patient_id)}\n\n{body}"
        return body, data_source

    async def _handle_assess_aki(
        self,
        sharp_headers: dict[str, str],
        patient_id: str,
    ) -> tuple[str, str]:
        """Run assess_postop_aki and format the KDIGO verdict."""
        try:
            raw = await self._mcp.call_tool(
                "assess_postop_aki",
                arguments={"patient_id": patient_id},
                sharp_headers=sharp_headers,
            )
        except McpClientError as e:
            return (
                f"I couldn't assess AKI for `{patient_id}` because the "
                f"MCP tool was unreachable: {e}.",
                "fhir",
            )

        data = _unwrap_tool_result(raw)
        err = _tool_error_text(data, patient_id, action="assess AKI")
        if err is not None:
            return err, _data_source(data)

        stage = data.get("kdigo_stage", 0)
        criteria = data.get("criteria_met") or []
        creat = data.get("creatinine_current")
        baseline = data.get("creatinine_baseline")
        baseline_imputed = bool(data.get("baseline_imputed"))
        baseline_source = data.get("baseline_source") or "unknown source"
        ttf = data.get("time_to_intervention_hours")
        rationale = data.get("rationale") or "no rationale provided"

        creat_str = f"{creat:.2f}" if isinstance(creat, (int, float)) else "?"
        baseline_str = (
            f"{baseline:.2f}" if isinstance(baseline, (int, float)) else "?"
        )

        # Compute creatinine delta + direction-of-travel arrow. Even
        # without a 3-point trajectory in the tool output, showing the
        # change vs. baseline as an arrow + percentage tells the
        # clinician trajectory direction at a glance.
        delta_str = ""
        if isinstance(creat, (int, float)) and isinstance(baseline, (int, float)) and baseline > 0:
            pct = ((creat - baseline) / baseline) * 100
            arrow = "↑" if pct > 5 else ("↓" if pct < -5 else "↔")
            delta_str = f" ({arrow} **{pct:+.0f}%** vs baseline)"

        # Stage badge — KDIGO 2012 §2.1.1 staging mapped to its
        # standard urgency tier.
        stage_badge = {
            0: "STAGE 0 — no AKI",
            1: "STAGE 1 — increased surveillance",
            2: "STAGE 2 — URGENT, nephrology consult",
            3: "STAGE 3 — RRT readiness, ICU",
        }.get(stage, f"STAGE {stage} — escalate")

        # Time-to-intervention prompt per SCCM 2017 (Joannidis,
        # Intensive Care Med 2017;43:730).
        if ttf is None:
            ttf_text = "No urgent intervention indicated."
        elif ttf == 0:
            ttf_text = "**Immediate** intervention required (SCCM 2017)."
        else:
            ttf_text = f"Intervention within **{ttf}h** (SCCM 2017)."

        sections = [
            f"### AKI — **{stage_badge}** *(per KDIGO 2012)*",
            f"**SCr** {creat_str} mg/dL · **baseline** {baseline_str} mg/dL"
            + delta_str,
        ]
        if baseline_imputed:
            sections.append(
                f"*Baseline imputed* — {baseline_source}. Per KDIGO 2012 "
                "§3.1.2, lowest value in the prior 7 days is used when "
                "no formal baseline is documented."
            )
        if criteria:
            sections.append("\n**Criteria met:**")
            sections.extend(f"- {c}" for c in criteria[:5])

        sections.append(f"\n**Time-to-intervention:** {ttf_text}")

        # Nephrotoxin cross-reference prompt — the tool doesn't fetch
        # MedicationRequest yet, so surface this as a clinician
        # prompt. Always render at stage ≥1 because nephrotoxin review
        # is the single most under-applied step in the AKI workup
        # (KDIGO 2012 §3.4.2).
        if stage >= 1:
            sections.append(
                "\n**Review medication list now** *(KDIGO 2012 §3.4.2)*: "
                "stop or dose-adjust nephrotoxins — NSAIDs, ACE-I/ARBs, "
                "aminoglycosides, IV contrast, vancomycin, sulfonamides. "
                "Run `flag treatment conflicts` for an automated NSAID/AKI "
                "and ACE-I/hyperkalemia scan."
            )
            if stage >= 2:
                sections.append(
                    "**Fluid balance**: review 24h I/O. Avoid hyperchloremic "
                    "fluids (KDIGO 2012 §3.5)."
                )

        sections.append(f"\n*Rationale:* {rationale}")
        body = "\n".join(sections)
        return _with_disclosure(body, data), _data_source(data)

    async def _handle_score_news2(
        self,
        sharp_headers: dict[str, str],
        patient_id: str,
    ) -> tuple[str, str]:
        """Run score_news2 and format the RCP NEWS2 verdict."""
        try:
            raw = await self._mcp.call_tool(
                "score_news2",
                arguments={"patient_id": patient_id},
                sharp_headers=sharp_headers,
            )
        except McpClientError as e:
            return (
                f"I couldn't score NEWS2 for `{patient_id}` because the "
                f"MCP tool was unreachable: {e}.",
                "fhir",
            )

        data = _unwrap_tool_result(raw)
        err = _tool_error_text(data, patient_id, action="score NEWS2")
        if err is not None:
            return err, _data_source(data)

        agg = int(data.get("aggregate_score", 0) or 0)
        band = (data.get("band") or "unknown").lower()
        red_flag = bool(data.get("red_flag"))
        contributions = data.get("parameter_contributions") or []
        rationale = data.get("rationale") or "no rationale provided"

        # RCP NEWS2 2017 response framework — verbatim, since clinicians
        # rely on the exact wording for protocol compliance.
        # Single-parameter score of 3 overrides aggregate-band routing
        # per the RCP 2017 escalation chart.
        if red_flag and agg < 5:
            response = (
                "**Single-parameter score 3** — minimum hourly observations; "
                "registered nurse must inform medical team for urgent review "
                "by clinician with core competencies for acute illness."
            )
        elif agg >= 7 or band == "high":
            response = (
                "**Aggregate ≥7 (HIGH)** — continuous monitoring; emergency "
                "clinical response by team with critical-care competencies; "
                "consider transfer to higher-acuity setting (HDU/ICU)."
            )
        elif agg >= 5 or band == "medium":
            response = (
                "**Aggregate 5–6 (MEDIUM)** — minimum hourly observations; "
                "urgent review by clinician with core competencies for "
                "acute illness within 1 hour."
            )
        elif agg >= 1:
            response = (
                "**Aggregate 1–4 (LOW–MEDIUM)** — minimum 4–6 hourly "
                "observations; registered nurse to assess and decide "
                "whether to escalate frequency."
            )
        else:
            response = (
                "**Aggregate 0 (LOW)** — minimum 12-hourly observations; "
                "continue routine NEWS monitoring."
            )

        # Band badge — first line, drives the eye.
        band_badge = (
            "HIGH" if (agg >= 7 or band == "high") else
            "MEDIUM" if (agg >= 5 or band == "medium") else
            "LOW–MEDIUM" if agg >= 1 else
            "LOW"
        )
        red_flag_text = " · **RED FLAG** (single-parameter 3)" if red_flag else ""

        sections = [
            f"### NEWS2 — **{band_badge}** *(per RCP NEWS2 2017)*",
            f"Aggregate **{agg} / 20**{red_flag_text}",
        ]

        # Per-parameter score breakdown — bullet list (not a 4-col
        # table, since PO crammed those). Show all params, not just
        # non-zero, so the clinician can audit the full scoring.
        if contributions:
            sections.append("\n**Score breakdown:**")
            for c in contributions[:8]:
                param = c.get("parameter", "?")
                value = c.get("value", "?")
                score = int(c.get("score", 0) or 0)
                marker = "**" if score >= 3 else ""
                sections.append(
                    f"- {param}: {value} → score {marker}{score}{marker}"
                )

        sections.append(f"\n**RCP response:** {response}")
        sections.append(f"\n*Rationale:* {rationale}")
        body = "\n".join(sections)
        return _with_disclosure(body, data), _data_source(data)

    async def _handle_assess_pph(
        self,
        sharp_headers: dict[str, str],
        patient_id: str,
    ) -> tuple[str, str]:
        """Run assess_pph_severity and format the CMQCC stage verdict."""
        try:
            raw = await self._mcp.call_tool(
                "assess_pph_severity",
                arguments={"patient_id": patient_id},
                sharp_headers=sharp_headers,
            )
        except McpClientError as e:
            return (
                f"I couldn't assess PPH severity for `{patient_id}` "
                f"because the MCP tool was unreachable: {e}.",
                "fhir",
            )

        data = _unwrap_tool_result(raw)
        err = _tool_error_text(data, patient_id, action="assess PPH severity")
        if err is not None:
            return err, _data_source(data)

        stage = data.get("stage", 0)
        ebl = data.get("cumulative_ebl_ml")
        si = data.get("shock_index")
        hgb = data.get("hemoglobin_g_dl")
        fib = data.get("fibrinogen_mg_dl")
        triggers = data.get("triggers") or []
        actions = data.get("recommended_actions") or []
        ebl_caveat = data.get("ebl_caveat")
        rationale = data.get("rationale") or "no rationale provided"

        ebl_str = f"{ebl:.0f} mL" if isinstance(ebl, (int, float)) else "unmeasured"
        si_str = f"{si:.2f}" if isinstance(si, (int, float)) else "?"
        hgb_str = (
            f"{hgb:.1f} g/dL" if isinstance(hgb, (int, float)) else "?"
        )
        fib_str = (
            f"{fib:.0f} mg/dL" if isinstance(fib, (int, float)) else "?"
        )

        # Stage badge — CMQCC v3.0 / ACOG PB 183. Render the urgency in
        # plain English so a clinician scanning the chat reply
        # immediately knows whether to call OB, activate massive
        # transfusion, or continue routine surveillance.
        stage_badge = {
            0: "STAGE 0 — routine postpartum surveillance",
            1: "STAGE 1 — increased surveillance, OB at bedside",
            2: "STAGE 2 — URGENT, second IV + uterotonics + blood bank notify",
            3: "STAGE 3 — MASSIVE TRANSFUSION PROTOCOL, OR/ICU",
        }.get(stage, f"STAGE {stage} — escalate")

        sections = [
            f"### PPH severity — **{stage_badge}** *(CMQCC v3.0 / ACOG PB 183)*",
            f"**EBL** {ebl_str} · **Shock Index** {si_str} (HR/SBP) "
            f"· **Hgb** {hgb_str} · **Fibrinogen** {fib_str}",
        ]
        if ebl_caveat:
            sections.append(f"*EBL caveat:* {ebl_caveat}")

        if triggers:
            sections.append("\n**Triggers:**")
            sections.extend(f"- {t}" for t in triggers[:5])

        if actions:
            sections.append("\n**CMQCC action ladder** *(verbatim, in order):*")
            sections.extend(f"{i}. {a}" for i, a in enumerate(actions[:8], 1))

        # Stage 3 = massive hemorrhage. Surface the MTP ratio prompt
        # explicitly — it's the single most-forgotten step under stress.
        if stage >= 3:
            sections.append(
                "\n**Massive Transfusion Protocol**: activate now. Target "
                "ratio **1:1:1 RBC:FFP:platelets** (PROPPR trial, JAMA 2015). "
                "Notify blood bank; consider TXA 1g IV if within 3h of bleed onset."
            )

        sections.append(f"\n*Rationale:* {rationale}")
        body = "\n".join(sections)
        return _with_disclosure(body, data), _data_source(data)

    async def _handle_flag_treatment_conflicts(
        self,
        sharp_headers: dict[str, str],
        patient_id: str,
    ) -> tuple[str, str]:
        """Run flag_treatment_conflicts and format the conflict list.

        Each conflict row carries severity, drug class, physiology
        rationale, citation anchor, and verbatim mitigation. Only the
        chat prose is layered here — the verdict itself is deterministic
        (rule-engine in ``backend/criteria/treatment_conflicts.py``).
        """
        try:
            raw = await self._mcp.call_tool(
                "flag_treatment_conflicts",
                arguments={"patient_id": patient_id},
                sharp_headers=sharp_headers,
            )
        except McpClientError as e:
            return (
                f"I couldn't scan treatment conflicts for `{patient_id}` "
                f"because the MCP tool was unreachable: {e}.",
                "fhir",
            )

        data = _unwrap_tool_result(raw)
        err = _tool_error_text(
            data, patient_id, action="scan treatment conflicts",
        )
        if err is not None:
            return err, _data_source(data)

        conflicts = data.get("conflicts") or []
        safe_alts = data.get("safe_alternatives") or []

        if not conflicts:
            sections = [
                "### Treatment safety — **CLEAR**",
                "No conflicts across the 5 rule families "
                "(NSAID/AKI, β-blocker/bradycardia, ACE-I/hyperkalemia, "
                "opioid/respiratory depression, anticoagulant/bleeding).",
                "",
                "**Action**: Order may proceed with standard monitoring. "
                "Reassess if AKI, hypotension, or bleeding develops.",
            ]
            return _with_disclosure("\n".join(sections), data), _data_source(data)

        crit = sum(1 for c in conflicts if c.get("severity") == "critical")
        warn = sum(1 for c in conflicts if c.get("severity") == "warning")

        # Severity badge — leading the eye to urgency before any
        # drug/rule detail.
        if crit > 0:
            badge = "CRITICAL — do not order"
        elif warn > 0:
            badge = "WARNING — review before ordering"
        else:
            badge = "ADVISORY"

        sections = [
            f"### Treatment safety — **{badge}**",
            f"{len(conflicts)} conflict(s) — **{crit} critical**, "
            f"**{warn} warning**.",
        ]

        # Per-conflict card — drug, severity, physiology snapshot
        # at-time-of-order (proof), citation, and verbatim mitigation.
        # Order: critical first.
        ordered = sorted(
            conflicts,
            key=lambda c: 0 if c.get("severity") == "critical" else 1,
        )
        for c in ordered[:5]:
            sev = (c.get("severity") or "?").upper()
            drug_class = c.get("drug_class", "?")
            drug_disp = c.get("drug_display", "?")
            physio = c.get("physiology_summary", "?")
            cite = c.get("citation_anchor", "?")
            mitig = c.get("mitigation", "?")
            sections.append(
                f"\n**[{sev}] {drug_class}** — `{drug_disp}`"
            )
            sections.append(f"- *Physiology at order*: {physio}")
            sections.append(f"- *Mitigation*: {mitig}")
            sections.append(f"- *Cite*: {cite}")

        # Safe alternatives — promoted to a prominent "Consider instead"
        # block, never just a tail list. Ordering away from a
        # contraindication is half the answer; the other half is what
        # to write instead.
        if safe_alts:
            sections.append("\n**Consider instead:**")
            sections.extend(f"- `{a}`" for a in safe_alts[:6])

        # Override workflow nudge — real EHRs require documentation
        # for high-severity overrides; remind the prescriber.
        if crit > 0:
            sections.append(
                "\n*If clinically essential to override, document: "
                "indication, alternative considered, monitoring plan, "
                "and consenting clinician.*"
            )
        body = "\n".join(sections)
        return _with_disclosure(body, data), _data_source(data)

    async def _handle_start_watching(
        self,
        sharp_headers: dict[str, str],
        patient_id: str,
    ) -> str:
        """Report the current watch status for ``patient_id``.

        Programmatic per-patient enable/disable is post-MVP — the autonomous
        loop is configured deployment-wide via ``POLL_INTERVAL_SEC``. But the
        skill is more useful as a live status reporter than as a stub: it
        surfaces whether watching is on, what the cadence is, and what's
        already been flagged for this patient in the review queue.
        """
        import os

        from backend.api.review_queue import (
            count_superseded_alerts,
            count_unread_alerts,
            get_latest_alert_at,
        )

        try:
            interval_sec = int(os.environ.get("POLL_INTERVAL_SEC", "900"))
        except ValueError:
            interval_sec = 0

        try:
            pending = count_unread_alerts(patient_id)
            superseded = count_superseded_alerts(patient_id)
            last_seen = get_latest_alert_at(patient_id)
        except Exception:  # noqa: BLE001 — review queue is best-effort here
            logger.exception("review queue read failed in start_watching")
            pending, superseded, last_seen = 0, 0, None

        # Phrase the cadence the way a charge nurse would expect ("every
        # 5 min") rather than as raw seconds.
        if interval_sec >= 60 and interval_sec % 60 == 0:
            cadence_human = f"every {interval_sec // 60} min"
        elif interval_sec > 0:
            cadence_human = f"every {interval_sec}s"
        else:
            cadence_human = "(disabled — POLL_INTERVAL_SEC=0)"

        # Format the most recent alert time + age for this patient. The
        # autonomous loop doesn't expose its actual last-tick time, but
        # last_alert_at is a useful proxy: it confirms the loop has been
        # screening this patient and tells the clinician how fresh the
        # info is.
        from datetime import UTC, datetime
        last_seen_str = "no alerts raised yet"
        if last_seen:
            try:
                seen_dt = datetime.fromisoformat(
                    last_seen.replace("Z", "+00:00")
                )
                age_min = int((datetime.now(UTC) - seen_dt).total_seconds() // 60)
                if age_min < 60:
                    last_seen_str = f"last alert {age_min} min ago"
                else:
                    last_seen_str = f"last alert {age_min // 60}h {age_min % 60}m ago"
            except (ValueError, AttributeError):
                last_seen_str = f"last alert at {last_seen}"

        if interval_sec <= 0:
            return (
                "### Watch — DISABLED\n"
                "Vigil's autonomous loop is off (`POLL_INTERVAL_SEC=0`). "
                "Skills run on-demand only. To enable continuous monitoring "
                "for this ward, set a positive interval and restart the "
                "agent service."
            )

        sections = [
            f"### Watch — ACTIVE for `{patient_id}`",
            f"Autonomous loop polls **{cadence_human}** across the postop "
            f"& postpartum cohort.",
            "",
            "**This patient's review-queue history:**",
            f"- {pending} pending alert{'s' if pending != 1 else ''}",
            f"- {superseded} superseded alert{'s' if superseded != 1 else ''}",
            f"- {last_seen_str}",
        ]
        if pending == 0 and superseded == 0:
            sections.append(
                "\nNo alerts have fired for this patient on Vigil's "
                "monitored cohort yet — but the loop will continue to "
                "screen on every tick."
            )
        elif pending > 0:
            sections.append(
                "\n**Action**: Review pending alert via "
                "`show recent alerts`, then claim or supersede."
            )
        return "\n".join(sections)

    async def _handle_list_recent_alerts(self) -> str:
        """Return alerts the autonomous loop has surfaced on Vigil's HAPI.

        Vigil's autonomous monitoring loop ticks every ``POLL_INTERVAL_SEC``
        against the seeded postop cohort on the agent's own HAPI server,
        independent of whatever patient PO chat is scoped to. This skill
        exposes the resulting review-queue contents so a clinician asking
        "what has been flagged?" via PO chat can see the ward-wide picture
        even if their current chat scope is a different patient.
        """
        import os

        from backend.api.review_queue import list_pending_alerts

        try:
            interval_sec = int(os.environ.get("POLL_INTERVAL_SEC", "0"))
        except ValueError:
            interval_sec = 0

        try:
            alerts = list_pending_alerts()
        except Exception:  # noqa: BLE001 — review queue is best-effort here
            logger.exception("review queue read failed in list_recent_alerts")
            return (
                "I couldn't read the alert queue right now. The autonomous "
                "monitoring loop's SQLite store is temporarily unavailable."
            )

        if interval_sec > 0:
            cadence = (
                f"Vigil's autonomous loop is watching every {interval_sec}s."
            )
        else:
            cadence = (
                "Vigil's autonomous loop is currently disabled "
                "(`POLL_INTERVAL_SEC=0`); only on-demand skill calls run."
            )

        if not alerts:
            return (
                f"### Recent alerts — none pending\n"
                f"{cadence} The watched cohort has no active alerts in the "
                "review queue. All patients are within MEWT thresholds at "
                "the most recent tick."
            )

        # Bucket by severity, surface critical first.
        order = {"critical": 0, "urgent": 1, "routine": 2}
        alerts_sorted = sorted(
            alerts, key=lambda a: (order.get(a.get("severity", ""), 9),)
        )
        crit = [a for a in alerts_sorted if a.get("severity") == "critical"]
        urg = [a for a in alerts_sorted if a.get("severity") == "urgent"]
        rou = [a for a in alerts_sorted if a.get("severity") not in ("critical", "urgent")]

        # Compute age + stale flag once, up here, so every alert line
        # uses the same "now" reference even if list_pending_alerts
        # returned slowly.
        from datetime import UTC, datetime
        now = datetime.now(UTC)

        def _age_str(created_iso: str) -> tuple[str, bool]:
            """Return ('14m ago', is_stale_flag) for a created_at ISO string.

            >30 min without a clinician claim is considered stale per
            ward-charge-nurse convention; the flag drives a visual
            warning in the line so older alerts surface first to the eye.
            """
            try:
                created_dt = datetime.fromisoformat(
                    created_iso.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                return ("just now", False)
            secs = int((now - created_dt).total_seconds())
            stale = secs >= 30 * 60
            if secs < 60:
                return (f"{secs}s ago", stale)
            if secs < 60 * 60:
                return (f"{secs // 60}m ago", stale)
            hours = secs / 3600
            return (f"{hours:.1f}h ago", stale)

        def _line(a: dict) -> str:
            pid = a.get("patient_id", "?")
            sev = a.get("severity", "?")
            age, stale = _age_str(a.get("created_at", "") or "")
            stale_tag = " — **STALE, claim now**" if stale else ""
            note = (a.get("narrative", "") or "")
            if len(note) > 140:
                note = note[:137].rstrip() + "…"
            return (
                f"- **{pid}** · {sev} · raised {age}{stale_tag}\n"
                f"  {note}"
            )

        sections = [
            f"### Recent alerts — {len(alerts)} pending",
            cadence,
        ]
        if crit:
            sections.append("\n**CRITICAL — escalate now:**")
            sections.extend(_line(a) for a in crit)
        if urg:
            sections.append("\n**URGENT:**")
            sections.extend(_line(a) for a in urg)
        if rou:
            sections.append("\n**Routine review:**")
            sections.extend(_line(a) for a in rou)
        sections.append(
            "\nThese alerts come from Vigil's autonomous monitoring of its "
            "seeded postop cohort, not from the patient currently scoped in "
            "PO chat. Use `screen vitals` / `score risk` for the chat-scoped "
            "patient."
        )
        return "\n".join(sections)

    async def _handle_tick_now(self) -> str:
        """Run one autonomous-loop cycle synchronously and return a summary.

        Lets a clinician (or a hackathon judge) trigger the autonomous
        tick on demand from PO chat instead of waiting up to
        ``POLL_INTERVAL_SEC`` for the next scheduled cycle. The cycle
        screens every patient in Vigil's HAPI cohort and enqueues alerts
        in the SQLite review queue exactly the same way the background
        loop would — so a follow-up ``list recent alerts`` returns the
        populated queue immediately.
        """
        import os

        from backend.a2a_agent.tick import run_cycle_for_all_patients

        fhir_base = os.environ.get(
            "FHIR_BASE_URL", "http://localhost:8080/fhir"
        )
        try:
            summary = await run_cycle_for_all_patients(self._mcp, fhir_base)
        except Exception as e:  # noqa: BLE001 — surface as friendly chat reply
            logger.exception("tick_now cycle failed")
            return (
                f"I couldn't run a tick cycle: {e}. The autonomous loop's "
                "FHIR connection or MCP tool layer is unavailable right now."
            )

        ticked = summary.get("patients_ticked", 0)
        generated = summary.get("alerts_generated", 0)
        return (
            f"### Tick complete\n"
            f"Screened **{ticked}** patient(s) on Vigil's HAPI cohort. "
            f"**{generated}** new alert(s) enqueued in the review queue.\n\n"
            "Ask `show recent alerts` to see what was flagged."
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
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Emit a Task event with a status message."""
        message_kwargs: dict[str, Any] = {
            "message_id": str(uuid.uuid4()),
            "role": Role.agent,
            "parts": [TextPart(text=text)],
        }
        if metadata:
            message_kwargs["metadata"] = metadata
        task = Task(
            id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=state,
                message=Message(**message_kwargs),
            ),
        )
        await event_queue.enqueue_event(task)

    async def _emit_completed(
        self,
        event_queue: EventQueue,
        task_id: str,
        context_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Emit a single final ``TaskState.completed`` event with chat text."""
        await self._emit_status(
            event_queue, task_id, context_id,
            TaskState.completed,
            text,
            final=True,
            metadata=metadata,
        )


# ---------------------------------------------------------------
# Module-level helpers — kept for test compatibility.
# ---------------------------------------------------------------


def _safe_get(data: Any, key: str) -> Any:
    """Safely get a key from a dict-like MCP tool result (may be nested JSON).

    Handles three shapes returned by ``VigilMcpClient.call_tool``:
      1. a parsed dict whose keys are the tool output directly,
      2. a JSON string with the tool output,
      3. an MCP ``tools/call`` result wrapping the JSON in
         ``content[0].text``.
    """
    unwrapped = _unwrap_tool_result(data)
    if isinstance(unwrapped, dict):
        return unwrapped.get(key)
    return None


def _unwrap_tool_result(data: Any) -> dict[str, Any]:
    """Normalise an MCP tool result to a plain dict.

    ``VigilMcpClient.call_tool`` returns the JSON-RPC ``result`` field as-is.
    FastMCP wraps tool output in ``{"content": [{"type": "text",
    "text": "<json>"}], "isError": false}``; older callers may also see
    raw dicts or JSON strings.  Returns an empty dict when parsing fails.
    """
    if data is None:
        return {}
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    if isinstance(data, dict):
        content = data.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and isinstance(first.get("text"), str):
                try:
                    parsed = json.loads(first["text"])
                except (json.JSONDecodeError, TypeError):
                    return {}
                return parsed if isinstance(parsed, dict) else {}
        return data
    return {}


def _data_source(data: dict[str, Any]) -> str:
    """Extract ``data_source`` from a tool result. Defaults to ``"fhir"``.

    The 4 MCP tools tag every output with ``data_source=fhir`` (live
    workspace) or ``data_source=synthetic_demo`` (env-var-gated PT-007
    fallback). Consumers default to "fhir" so older outputs without the
    field — e.g. mocks in older tests — keep the existing behaviour.
    """
    src = data.get("data_source")
    return src if isinstance(src, str) else "fhir"


def _with_disclosure(body: str, data: dict[str, Any]) -> str:
    """Prefix an honest one-liner if the result came from synthetic data.

    The synthetic fallback's chat-friendly disclosure (see
    :func:`backend.mcp_server.synthetic_fallback.synthetic_disclosure`)
    is the public-facing receipt that PO's launchpad shows the operator
    when the workspace's FHIR server didn't accept our token. Live-data
    responses pass through unchanged.

    The bundle name in the disclosure is selected by the inbound
    ``patient_id`` so PT-010 (PPH cameo) reports its own bundle rather
    than the default PT-007.
    """
    if _data_source(data) == SYNTHETIC_DATA_SOURCE:
        pid = data.get("patient_id") if isinstance(data, dict) else None
        return f"{synthetic_disclosure(pid)}\n\n{body}"
    return body


def _tool_error_text(
    data: dict[str, Any],
    patient_id: str,
    action: str,
) -> str | None:
    """Return a friendly error sentence iff ``data`` is a tool error envelope.

    The 4 MCP tools share ``ToolStatus`` (``backend/schemas.py``); statuses
    in :data:`_TOOL_ERROR_STATUSES` indicate a precondition failure rather
    than a clinical signal. ``triggered`` is NOT an error.
    """
    status = data.get("status")
    if isinstance(status, str) and status in _TOOL_ERROR_STATUSES:
        message = data.get("message") or "the tool returned an error envelope"
        return (
            f"I couldn't {action} for `{patient_id}` because "
            f"{message} (status `{status}`)."
        )
    return None
