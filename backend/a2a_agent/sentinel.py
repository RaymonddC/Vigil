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
        status = data.get("status", "ok")

        if not breaches:
            body = (
                f"**Vital screen** — patient `{patient_id}`\n\n"
                f"No MEWT breaches across {scanned} recent observations. "
                "All vitals within thresholds."
            )
            return _with_disclosure(body, data), _data_source(data)

        red = sum(1 for b in breaches if b.get("severity") == "red")
        yellow = sum(1 for b in breaches if b.get("severity") == "yellow")

        rows = [
            "| Vital | Value | Threshold | Severity |",
            "|---|---|---|---|",
        ]
        for b in breaches[:8]:
            sev = b.get("severity", "?")
            rows.append(
                f"| {b.get('label', '?')} "
                f"| {b.get('value', '?')} {b.get('unit', '')} "
                f"| {b.get('threshold', '?')} "
                f"| **{sev}** |"
            )

        body = (
            f"**Vital screen** — patient `{patient_id}` "
            f"(status: **{status}**)\n\n"
            f"{len(breaches)} MEWT breach(es) — "
            f"**{red} red**, **{yellow} yellow** — across {scanned} observations.\n\n"
            + "\n".join(rows)
        )
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

        band = data.get("risk_band", "unknown")
        qsofa = data.get("qsofa_score")
        composite = data.get("composite_risk")
        rationale = data.get("rationale") or "no rationale provided"
        comorbid = data.get("contributing_conditions") or []

        composite_str = (
            f"`{composite:.2f}`" if isinstance(composite, (int, float))
            else "`?`"
        )
        lines = [
            f"Deterioration risk for `{patient_id}`: band `{band}` "
            f"(qSOFA `{qsofa} / 3`, composite {composite_str}).",
            f"Rationale: {rationale}",
        ]
        if comorbid:
            lines.append(
                "Contributing conditions: "
                + ", ".join(f"`{c}`" for c in comorbid[:5])
            )
        body = "\n".join(lines)
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
            tail = (
                f" Mode `{mode}`, no criteria met."
                if not criteria
                else f" Mode `{mode}`; partial criteria: "
                + "; ".join(f"`{c}`" for c in criteria[:3])
            )
            body = (
                f"Sepsis screen for `{patient_id}`: not suspected."
                + tail
            )
            return _with_disclosure(body, data), _data_source(data)

        header = (
            f"Sepsis screen for `{patient_id}`: SUSPECTED "
            f"(mode `{mode}`"
            + (f", onset `{onset}`" if onset else "")
            + ")."
        )
        bullets = [f"- {c}" for c in criteria[:5]]
        body = "\n".join([header, "Criteria met:", *bullets])
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
        severity = data.get("severity") or "info"
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

        header = (
            f"SBAR for `{patient_id}` — severity `{severity}`, "
            f"recipient `{resolved_recipient}` (model `{model_used}`)."
        )
        if narrative:
            body = f"{header}\n\n{narrative}"
        else:
            # Fall back to assembling from the structured SBAR block if the
            # narrative is empty.
            sbar = data.get("sbar") or {}
            block = "\n".join(
                f"**{k.title()}:** {sbar.get(k, '').strip() or '—'}"
                for k in (
                    "situation",
                    "background",
                    "assessment",
                    "recommendation",
                )
            )
            body = f"{header}\n\n{block}"

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

        creat_str = f"`{creat:.2f}`" if isinstance(creat, (int, float)) else "`?`"
        baseline_str = (
            f"`{baseline:.2f}`" if isinstance(baseline, (int, float)) else "`?`"
        )
        if ttf is None:
            ttf_str = "no urgent intervention indicated"
        elif ttf == 0:
            ttf_str = "**immediate** intervention (SCCM 2017)"
        else:
            ttf_str = f"intervention within `{ttf}h` (SCCM 2017)"

        header = (
            f"AKI assessment for `{patient_id}`: KDIGO **Stage "
            f"{stage}**. SCr {creat_str} mg/dL vs baseline "
            f"{baseline_str} mg/dL. Recommendation: {ttf_str}."
        )
        lines = [header]
        if baseline_imputed:
            lines.append(f"Baseline imputed — {baseline_source}.")
        if criteria:
            lines.append("Criteria met:")
            lines.extend(f"- {c}" for c in criteria[:5])
        lines.append(f"Rationale: {rationale}")
        body = "\n".join(lines)
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

        agg = data.get("aggregate_score", 0)
        band = data.get("band", "unknown")
        red_flag = bool(data.get("red_flag"))
        contributions = data.get("parameter_contributions") or []
        rationale = data.get("rationale") or "no rationale provided"

        flag_text = " — **red flag** (single-parameter 3)" if red_flag else ""
        header = (
            f"NEWS2 for `{patient_id}`: aggregate `{agg}/20`, band "
            f"`{band}`{flag_text}."
        )
        contrib_bullets = [
            f"- `{c.get('parameter', '?')}` "
            f"value=`{c.get('value', '?')}` "
            f"score=`{c.get('score', 0)}`"
            for c in contributions
            if int(c.get("score", 0) or 0) > 0
        ]
        lines = [header]
        if contrib_bullets:
            lines.append("Non-zero contributions:")
            lines.extend(contrib_bullets[:7])
        lines.append(f"Rationale: {rationale}")
        body = "\n".join(lines)
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

        ebl_str = f"`{ebl:.0f} mL`" if isinstance(ebl, (int, float)) else "`unmeasured`"
        si_str = f"`{si:.2f}`" if isinstance(si, (int, float)) else "`?`"
        hgb_str = (
            f"`{hgb:.1f} g/dL`" if isinstance(hgb, (int, float)) else "`?`"
        )
        fib_str = (
            f"`{fib:.0f} mg/dL`" if isinstance(fib, (int, float)) else "`?`"
        )

        header = (
            f"PPH assessment for `{patient_id}`: CMQCC **Stage {stage}**. "
            f"EBL {ebl_str}, shock index {si_str}, Hgb {hgb_str}, "
            f"fibrinogen {fib_str}."
        )
        lines = [header]
        if ebl_caveat:
            lines.append(f"Caveat: {ebl_caveat}")
        if triggers:
            lines.append("Triggers:")
            lines.extend(f"- {t}" for t in triggers[:5])
        if actions:
            lines.append("CMQCC recommended actions (verbatim):")
            lines.extend(f"- {a}" for a in actions[:5])
        lines.append(f"Rationale: {rationale}")
        body = "\n".join(lines)
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
            body = (
                f"Treatment safety scan for `{patient_id}`: "
                "**no conflicts detected** across the 5 rules "
                "(NSAID/AKI, β-blocker/bradycardia, "
                "ACE-I/hyperkalemia, opioid/respiratory depression, "
                "anticoagulant/bleeding). Order request can proceed "
                "with standard monitoring."
            )
            return _with_disclosure(body, data), _data_source(data)

        crit = sum(
            1 for c in conflicts if c.get("severity") == "critical"
        )
        warn = sum(
            1 for c in conflicts if c.get("severity") == "warning"
        )
        header = (
            f"Treatment safety scan for `{patient_id}`: "
            f"`{len(conflicts)}` conflict(s) — `{crit}` critical, "
            f"`{warn}` warning."
        )
        lines: list[str] = [header]
        for c in conflicts[:5]:
            sev = c.get("severity", "?")
            drug_class = c.get("drug_class", "?")
            drug_disp = c.get("drug_display", "?")
            physio = c.get("physiology_summary", "?")
            cite = c.get("citation_anchor", "?")
            mitig = c.get("mitigation", "?")
            lines.append(
                f"- **[{sev}] {drug_class}** (`{drug_disp}`) vs "
                f"{physio}. Cite: {cite}. Mitigation: {mitig}"
            )
        if safe_alts:
            lines.append(
                "Safe alternatives: "
                + ", ".join(f"`{a}`" for a in safe_alts[:6])
            )
        body = "\n".join(lines)
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

        if interval_sec > 0:
            cadence = (
                f"Vigil is actively watching every {interval_sec}s "
                f"(deployment-wide cadence)."
            )
        else:
            cadence = (
                "Vigil's autonomous loop is currently disabled "
                "(`POLL_INTERVAL_SEC=0`); skills run on-demand only."
            )

        history_bits: list[str] = []
        if pending:
            history_bits.append(f"{pending} pending alert(s) in the review queue")
        if superseded:
            history_bits.append(f"{superseded} superseded alert(s)")
        if last_seen:
            history_bits.append(f"last alert at {last_seen}")
        history = (
            "Patient history: " + "; ".join(history_bits) + "."
            if history_bits
            else f"No alerts have been raised for `{patient_id}` yet."
        )

        return (
            f"{cadence} {history} "
            "Programmatic per-patient enable/disable is post-MVP — to change "
            "cadence, update `POLL_INTERVAL_SEC` and restart the agent service."
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
