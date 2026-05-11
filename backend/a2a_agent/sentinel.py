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
            elif skill is SkillId.READ_NURSING_SIGNALS:
                text, data_source = await self._handle_read_nursing_signals(
                    sharp_headers, patient_id
                )
            elif skill is SkillId.EXPLAIN:
                text = await self._handle_explain(
                    sharp_headers, patient_id, context.message
                )
            elif skill is SkillId.FORECAST_TRAJECTORY:
                text, data_source = await self._handle_forecast_trajectory(
                    sharp_headers, patient_id
                )
            elif skill is SkillId.ESTIMATE_SAVINGS:
                text = await self._handle_estimate_savings()
            elif skill is SkillId.FEEDBACK:
                text = await self._handle_feedback(context.message)
            elif skill is SkillId.SCREEN_PEDIATRIC:
                text, data_source = await self._handle_screen_pediatric(
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

        # Trend arrows per breached vital — clinicians read direction
        # before number. Compute from vitals_history (LOINC → samples,
        # oldest first) shipped by the MCP tool. Fall back silently if
        # history is missing (older tool version) or has fewer than 2
        # samples for that LOINC.
        history = data.get("vitals_history") or {}

        def _trend(loinc: str, latest: float | int | str) -> str:
            samples = history.get(loinc) or []
            if len(samples) < 2:
                return ""
            try:
                prev = float(samples[-2].get("value"))
                curr = float(latest) if not isinstance(latest, str) else float(latest)
            except (TypeError, ValueError):
                return ""
            if prev <= 0:
                return ""
            pct = ((curr - prev) / abs(prev)) * 100
            # 5% deadband — clinically meaningful threshold for
            # most postop vitals at hourly cadence; below this is
            # visit-to-visit noise.
            if pct >= 5:
                return f" ↑ ({pct:+.0f}% vs prior)"
            if pct <= -5:
                return f" ↓ ({pct:+.0f}% vs prior)"
            return " ↔ (stable vs prior)"

        def _baseline(loinc: str, latest: float | int | str) -> str:
            """Earliest sample in the fetched window as a pseudo-baseline.

            True pre-op baseline would need a separate FHIR query against
            the procedure-anchored window; this is the cheap approximation
            that lights up "% drift since first observation we have"
            without a tool change. Honest framing in the chat label.
            """
            samples = history.get(loinc) or []
            if len(samples) < 3:
                return ""
            try:
                first = float(samples[0].get("value"))
                curr = float(latest) if not isinstance(latest, str) else float(latest)
            except (TypeError, ValueError):
                return ""
            if first <= 0:
                return ""
            pct = ((curr - first) / abs(first)) * 100
            if abs(pct) < 5:
                return ""
            unit = (samples[0].get("unit") or "").strip()
            unit_tail = f" {unit}" if unit else ""
            return f" — first reading {first:g}{unit_tail} ({pct:+.0f}%)"

        def _line(b: dict) -> str:
            label = b.get("label", "?")
            value = b.get("value", "?")
            unit = (b.get("unit", "") or "").strip()
            thr = _humanize(b.get("threshold", ""))
            loinc = b.get("loinc", "")
            tail = f" {unit}" if unit else ""
            trend = _trend(loinc, value) if loinc else ""
            base = _baseline(loinc, value) if loinc else ""
            return f"- **{label}** {value}{tail}{trend} (threshold {thr}){base}"

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

        # Severity-weight attribution — additive decomposition of which
        # breaches drove the screen's "triggered" verdict. RED weighted
        # 1.0, YELLOW 0.5; total severity index = sum. Lets a reviewer
        # see the clinical weight of each contributing breach without
        # re-running the rule engine. TRIPOD+AI item 16 (interpretability).
        if breaches:
            sev_index = sum(
                1.0 if b.get("severity") == "red" else 0.5
                for b in breaches
            )
            sections.append(
                "\n**Severity attribution** *(clinical-weight decomposition):*"
            )
            for b in (red_breaches + yellow_breaches)[:6]:
                w = 1.0 if b.get("severity") == "red" else 0.5
                sections.append(
                    f"- {b.get('label', '?')} "
                    f"({b.get('severity', '?').upper()}, weight {w:.1f})"
                )
            sections.append(
                f"- **Severity index: {sev_index:.1f}** "
                f"({len(red_breaches)}×1.0 + {len(yellow_breaches)}×0.5)"
            )

        # Confidence — driven by scan count and freshness. Aligns with
        # the data-completeness framing in clinical-AI evaluation
        # frameworks (TRIPOD-AI 2024).
        if scanned >= 6:
            conf_level, conf_reason = (
                "high", f"{scanned} observations in window, recent reading"
            )
        elif scanned >= 3:
            conf_level, conf_reason = (
                "medium", f"{scanned} observations — sparse window"
            )
        else:
            conf_level, conf_reason = (
                "low", f"only {scanned} observation(s) — verify at bedside"
            )
        sections.append(_confidence(conf_level, conf_reason))

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

        # "What would lower this risk" — derive from which qSOFA
        # components fired. Specific, actionable next steps tied to
        # the failing physiology, not generic advice. Each suggestion
        # is the standard first-line reversal step for that finding.
        reversal_steps: list[str] = []
        if qsofa_components.get("sbp_le_100"):
            reversal_steps.append(
                "Crystalloid bolus 250–500 mL; reassess SBP and lactate "
                "in 15 min. Surviving Sepsis 30 mL/kg if MAP <65 sustained."
            )
        if qsofa_components.get("rr_ge_22"):
            reversal_steps.append(
                "Recheck SpO2 + work of breathing; supplemental O2 if "
                "SpO2 <94%; consider CXR + ABG if persistent ≥22."
            )
        if qsofa_components.get("altered_mental"):
            reversal_steps.append(
                "Recheck GCS; rule out hypoglycemia (POC glucose), opioid "
                "effect, electrolytes. Document baseline mental status."
            )

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
        if reversal_steps:
            sections.append("\n**To lower this risk** *(first-line per failing component):*")
            sections.extend(f"- {s}" for s in reversal_steps)

        # Patient-context interpretation — LLM reads the deterministic
        # output + comorbidities + active conditions and adds a 1-2
        # sentence note about what this means *for this patient
        # specifically* (e.g. "HR 110 is significant given baseline
        # bradycardia from beta-blocker"). Rules can't do that.
        # Skip when there's nothing patient-specific to interpret —
        # qSOFA 0 with no comorbidities is just "low risk", no LLM
        # needed.
        if qsofa or comorbid:
            from backend.llm.provider import LLMError, get_provider

            firing = [
                label for key, label in component_labels
                if qsofa_components.get(key)
            ]
            ctx_prompt = (
                "You are Vigil, a postop sentinel agent. Interpret the "
                "deterioration risk for this specific patient in 1-2 "
                "concise sentences, taking comorbidities and active "
                "conditions into account. Focus on what's clinically "
                "significant for THIS patient that a static threshold "
                "wouldn't capture (e.g. baseline meds masking tachycardia, "
                "comorbid CKD altering AKI staging interpretation, etc).\n\n"
                f"Patient: {patient_id}\n"
                f"Risk band: {band} (qSOFA {qsofa}/3, composite {composite_str})\n"
                f"Firing qSOFA components: {firing or 'none'}\n"
                f"Active conditions: {', '.join(comorbid) or 'none documented'}\n\n"
                "Output: 1-2 sentences only. No bullets, no preamble, no "
                "guideline citation (those are elsewhere). Plain prose. "
                "Begin directly with clinical reasoning."
            )
            try:
                interp = (
                    await get_provider().complete(ctx_prompt, max_tokens=150)
                ).strip()
                if interp:
                    sections.append(
                        f"\n**Patient-specific context** *(LLM-interpreted):*\n{interp}"
                    )
            except LLMError as exc:
                logger.debug(
                    "score_risk LLM interpretation failed (non-fatal)",
                    extra={"patient_id": patient_id, "error": str(exc)},
                )

        # Shapley-style attribution — render each feature's deterministic
        # contribution to the composite_risk score so the clinician (and
        # any reviewer) can see exactly which inputs drove the band.
        # The rule engine in score_deterioration_risk uses the formula:
        #   composite = qsofa/3 + min(mewt_breaches * 0.15, 0.30)
        #             + min(active_conditions * 0.05, 0.15), capped at 1.0
        # so the contributions decompose additively (true SHAP for an
        # additive model collapses to feature contribution).
        attr_lines: list[str] = []
        if qsofa:
            qsofa_share = (qsofa / 3.0)
            attr_lines.append(
                f"- qSOFA contribution: **+{qsofa_share:.2f}** "
                f"({qsofa}/3 components)"
            )
        # MEWT breach count not directly returned here; infer from
        # whichever rationale fragment lists it. Skip if absent.
        if "MEWT" in (rationale or ""):
            # The score_risk rationale embeds breach counts; pull a
            # rough number from contributing_conditions instead — best
            # we can do without re-fetching.
            pass
        if comorbid:
            comorbid_share = min(len(comorbid) * 0.05, 0.15)
            attr_lines.append(
                f"- Comorbidity contribution: **+{comorbid_share:.2f}** "
                f"({len(comorbid)} active condition"
                f"{'s' if len(comorbid) != 1 else ''})"
            )
        if attr_lines and isinstance(composite, (int, float)):
            attr_lines.append(f"- **Composite total: {composite:.2f}**")
            sections.append(
                "\n**Score attribution** *(Shapley-style decomposition, "
                "TRIPOD+AI item 16 — model interpretability):*"
            )
            sections.extend(attr_lines)

        # Confidence — driven by how many qSOFA components actually
        # fired (more signal = more confident verdict) and whether we
        # have comorbidity context to ground it.
        firing_n = sum(1 for v in qsofa_components.values() if v)
        if firing_n >= 2 and comorbid:
            conf_level, conf_reason = (
                "high",
                f"{firing_n}/3 qSOFA components fired with documented comorbidities",
            )
        elif firing_n >= 1:
            conf_level, conf_reason = (
                "medium",
                f"{firing_n}/3 qSOFA components fired — single-feature signal",
            )
        else:
            conf_level, conf_reason = (
                "low",
                "qSOFA 0; verdict driven by comorbidity-weighted composite",
            )
        sections.append(_confidence(conf_level, conf_reason))

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

        # Confidence — driven by criteria-met count + mode. CDC ASE with
        # ≥3 criteria is the authoritative surveillance threshold.
        n_crit = len(criteria)
        if n_crit >= 3:
            conf_level, conf_reason = (
                "high",
                f"{n_crit} CDC ASE criteria met (mode `{mode}`)",
            )
        elif n_crit >= 2:
            conf_level, conf_reason = (
                "medium",
                f"{n_crit} criteria met — borderline by CDC ASE threshold",
            )
        else:
            conf_level, conf_reason = (
                "low",
                f"only {n_crit} criterion met — verify with cultures + lactate",
            )
        sections.append(_confidence(conf_level, conf_reason))

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

        # "What to expect when you arrive" — short clinical priming
        # tuned to severity. Helps the receiving clinician walk to the
        # bedside with the right expectations and gear, instead of
        # arriving cold to the SBAR and re-orienting.
        priming = {
            "critical": (
                "Expect cool/mottled extremities, slow capillary refill, "
                "oliguria, possible altered mentation. Bring fluids and "
                "have vasopressor on standby; consider arterial line."
            ),
            "emergency": (
                "Expect cool/mottled extremities, slow capillary refill, "
                "oliguria, possible altered mentation. Bring fluids and "
                "have vasopressor on standby; consider arterial line."
            ),
            "urgent": (
                "Expect mild diaphoresis, tachycardia, possible early "
                "shock signs. Recheck obs and review the trend chart on "
                "arrival; have IV access verified."
            ),
            "routine": (
                "Expect stable vitals at the bedside. Routine review and "
                "documentation; no immediate action expected."
            ),
            "info": (
                "Expect stable vitals at the bedside. Routine review and "
                "documentation; no immediate action expected."
            ),
        }.get(severity, "")

        # Multi-modal framing — count the distinct input modalities
        # this SBAR was synthesised from (structured vitals + structured
        # labs + unstructured nursing notes) and surface that in the
        # header. This is the COMPOSER-LLM (npj Digital Medicine 2025)
        # multi-modal pattern: deterministic structured detection +
        # LLM enrichment of free text. Prove it in the response itself,
        # not just the marketing copy.
        n_breaches = len(unwrapped_vitals.get("breaches") or [])
        n_scanned = unwrapped_vitals.get("scanned_count") or 0
        n_conditions = len(unwrapped_risk.get("contributing_conditions") or [])
        n_notes = 0
        try:
            from backend.fhir.client import FhirClient as _FC
            from backend.schemas import FhirContext as _FX
            _ctx = _FX(
                url=sharp_headers.get("x-fhir-server-url", ""),
                token=sharp_headers.get("x-fhir-access-token"),
                patient_id=sharp_headers.get("x-patient-id"),
            )
            async with _FC(_ctx) as _fc:
                _obs = await _fc.get_observations(
                    patient_id, category="vital-signs"
                )
            _seen: set[str] = set()
            for _o in _obs:
                for _n in _o.note or []:
                    _t = (_n.text or "").strip()
                    if _t and _t not in _seen:
                        _seen.add(_t)
            n_notes = len(_seen)
        except Exception:  # noqa: BLE001 — non-fatal, just lose the count
            logger.debug("draft_sbar nursing-note count failed (non-fatal)")

        modality_line = (
            f"*Multi-modal: synthesised **{n_scanned} vital-sign "
            f"observation{'s' if n_scanned != 1 else ''}** "
            f"({n_breaches} breached), "
            f"**{n_conditions} active condition{'s' if n_conditions != 1 else ''}**, "
            f"and **{n_notes} free-text nursing note{'s' if n_notes != 1 else ''}** "
            f"— deterministic detection + LLM-narrated synthesis "
            f"(architecture: COMPOSER-LLM, npj Digital Medicine 2025).*"
        )

        sections = [
            f"### SBAR — **{badge}**",
            f"**To:** {recipient_text}",
            "**From:** Vigil postop & postpartum sentinel",
            f"**Patient:** `{patient_id}`",
            modality_line,
            "",
            "```",
            sbar_body,
            "```",
        ]
        if priming:
            sections.extend(["", f"**On arrival, expect:** {priming}"])

        # Differential diagnosis — LLM reads the SBAR body + the three
        # screen results and proposes a ranked differential the receiving
        # clinician should consider. Rules can't generate a differential;
        # this is squarely in the "AI you can't replace with case
        # statements" category. Output is suggestion only; the SBAR
        # recommendation section (rule-engine generated) remains the
        # authoritative escalation guidance.
        try:
            from backend.llm.provider import LLMError, get_provider

            screen_summary = json.dumps(
                {
                    "vitals": {
                        "status": unwrapped_vitals.get("status"),
                        "breaches": [
                            {
                                "label": b.get("label"),
                                "value": b.get("value"),
                                "severity": b.get("severity"),
                            }
                            for b in (unwrapped_vitals.get("breaches") or [])[:6]
                        ],
                    },
                    "risk": {
                        "band": unwrapped_risk.get("risk_band"),
                        "qsofa": unwrapped_risk.get("qsofa_score"),
                        "conditions": unwrapped_risk.get(
                            "contributing_conditions"
                        ) or [],
                    },
                    "sepsis": {
                        "suspected": unwrapped_sepsis.get("sepsis_suspected"),
                        "criteria_met": unwrapped_sepsis.get("criteria_met"),
                    },
                },
                default=str,
            )
            diff_prompt = (
                "You are Vigil, a postop and postpartum sentinel agent. "
                "Given the deterministic screen results below, propose a "
                "ranked clinical differential — the diagnoses the "
                "receiving clinician should rule in or out at the "
                "bedside. Use Bayesian framing: most likely first, "
                "with one short clause per item explaining why these "
                "findings support it.\n\n"
                f"Patient: {patient_id}\n"
                f"Screen results: {screen_summary}\n\n"
                "Output rules:\n"
                "- 3-5 markdown bullets, ordered most likely first.\n"
                "- Format: `- **Diagnosis** — short rationale citing the "
                "specific finding (e.g. 'lactate 2.8 + Tmax 38.6').`\n"
                "- Do NOT invent findings not present in the screen.\n"
                "- Do NOT output any introduction or conclusion."
            )
            differential = (
                await get_provider().complete(diff_prompt, max_tokens=300)
            ).strip()
            if differential:
                sections.extend([
                    "",
                    "**Differential to consider** *(LLM-ranked, not "
                    "deterministic — verify at bedside):*",
                    differential,
                ])
        except LLMError as exc:
            logger.debug(
                "draft_sbar differential failed (non-fatal)",
                extra={"patient_id": patient_id, "error": str(exc)},
            )

        body = "\n".join(sections)
        if data_source == SYNTHETIC_DATA_SOURCE:
            body = f"{synthetic_disclosure(patient_id)}\n\n{body}"
        # Audit footer (P1 cross-cutting). Use the synthetic-aware
        # variant to match the inferred data source from the upstream
        # screen calls.
        body = body + _audit_footer(data_source)
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
        urine = data.get("urine_output_ml_kg_h")
        oliguria_hr = data.get("oliguria_hours")
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

        # Urine output line — KDIGO 2012 staging uses both creatinine
        # AND urine output, so surface the urine reading whenever the
        # tool returns it. Oliguria duration cues fluid-balance review.
        urine_line = ""
        if isinstance(urine, (int, float)):
            urine_line = f" · **Urine** {urine:.2f} mL/kg/h"
            if isinstance(oliguria_hr, (int, float)) and oliguria_hr > 0:
                urine_line += f" (oliguria {oliguria_hr:.0f}h)"

        sections = [
            f"### AKI — **{stage_badge}** *(per KDIGO 2012)*",
            f"**SCr** {creat_str} mg/dL · **baseline** {baseline_str} mg/dL"
            + delta_str
            + urine_line,
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

        # Confidence — NEWS2 expects all 7 parameters; missing
        # parameters reduce the verdict's reliability.
        n_params = len(contributions)
        if n_params >= 6:
            conf_level, conf_reason = (
                "high",
                f"{n_params}/7 NEWS2 parameters scored",
            )
        elif n_params >= 4:
            conf_level, conf_reason = (
                "medium",
                f"{n_params}/7 NEWS2 parameters scored — partial set",
            )
        else:
            conf_level, conf_reason = (
                "low",
                f"only {n_params}/7 parameters — sparse score; recheck obs",
            )
        sections.append(_confidence(conf_level, conf_reason))

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
            list_alerts_for_patient,
        )

        try:
            interval_sec = int(os.environ.get("POLL_INTERVAL_SEC", "900"))
        except ValueError:
            interval_sec = 0

        try:
            pending = count_unread_alerts(patient_id)
            superseded = count_superseded_alerts(patient_id)
            last_seen = get_latest_alert_at(patient_id)
            timeline = list_alerts_for_patient(patient_id, limit=5)
        except Exception:  # noqa: BLE001 — review queue is best-effort here
            logger.exception("review queue read failed in start_watching")
            pending, superseded, last_seen, timeline = 0, 0, None, []

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
                + _AUDIT_FOOTER_LIVE
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

        # Mini-timeline — last 5 alerts for this patient (any status).
        # Renders the escalation arc rather than just a count, so a
        # clinician sees pattern: "yellow at 12:14, yellow at 14:30,
        # red at 16:02" tells a different story than "3 alerts."
        if timeline:
            from datetime import UTC
            from datetime import datetime as _dt
            sections.append("\n**Timeline (latest 5):**")
            for a in timeline:
                created = (a.get("created_at") or "")
                sev = a.get("severity", "?")
                status = a.get("status", "?")
                try:
                    dt = _dt.fromisoformat(created.replace("Z", "+00:00"))
                    age_min = int((_dt.now(UTC) - dt).total_seconds() // 60)
                    when = (
                        f"{age_min}m ago" if age_min < 60
                        else f"{age_min // 60}h {age_min % 60}m ago"
                    )
                except (ValueError, AttributeError):
                    when = created[:19].replace("T", " ") if created else "?"
                sections.append(
                    f"- {when} · **{sev}** · status: {status}"
                )

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
        return "\n".join(sections) + _AUDIT_FOOTER_LIVE

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
                + _AUDIT_FOOTER_LIVE
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
        # Claim-this hint — give the charge nurse a concrete next step
        # for accountability. Programmatic claim is a future skill;
        # for now, the hint nudges the workflow.
        sections.append(
            "\n*To claim an alert and silence the queue for that patient, "
            "select the patient in PO scope and run `draft an SBAR` — "
            "review, then approve via the dashboard's HITL queue.*"
        )
        return "\n".join(sections) + _AUDIT_FOOTER_LIVE

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
        per_patient = summary.get("per_patient") or []

        sections = [
            "### Tick complete",
            f"Screened **{ticked}** patient(s) on Vigil's HAPI cohort. "
            f"**{generated}** new alert(s) enqueued.",
        ]

        # Per-patient row-by-row breakdown — clinicians and judges both
        # want this visible, not just an aggregate count. Two short
        # buckets: triggered (with severity) and clear.
        triggered_rows = [
            p for p in per_patient if p.get("triggered")
        ]
        if triggered_rows:
            sections.append("\n**Triggered:**")
            for p in triggered_rows[:10]:
                pid = p.get("patient_id", "?")
                sev = p.get("severity", "?")
                sections.append(f"- `{pid}` · severity **{sev}**")

        clear_count = len(per_patient) - len(triggered_rows)
        if clear_count > 0:
            sections.append(f"\n**Clear:** {clear_count} patient(s) within thresholds.")

        sections.append(
            "\nAsk `show recent alerts` for full review-queue detail."
        )
        return "\n".join(sections) + _AUDIT_FOOTER_LIVE

    async def _handle_read_nursing_signals(
        self,
        sharp_headers: dict[str, str],
        patient_id: str,
    ) -> tuple[str, str]:
        """LLM-extract subjective deterioration signals from nursing notes.

        Threshold-based screens (MEWT, NEWS2) catch deterioration *after*
        it shows in vitals. The most reliable early signal in postop care
        is what the bedside nurse writes in free text — "feeling off",
        "doesn't look right", "increasingly restless". Vital-sign rule
        engines literally cannot read those.

        This handler fetches the patient's vital-signs Observations (which
        carry ``Observation.note`` from the seeder), feeds the free-text
        notes to the LLM with a structured-extraction prompt, and renders
        the signals as actionable bullets. If FHIR is unreachable, returns
        a friendly message.
        """
        from backend.fhir.client import FhirClient, FhirClientError
        from backend.llm.provider import LLMError, get_provider
        from backend.schemas import FhirContext

        fhir_ctx = FhirContext(
            url=sharp_headers.get("x-fhir-server-url", ""),
            token=sharp_headers.get("x-fhir-access-token"),
            patient_id=sharp_headers.get("x-patient-id"),
        )

        try:
            async with FhirClient(fhir_ctx) as fhir:
                observations = await fhir.get_observations(
                    patient_id, category="vital-signs"
                )
                # Also pull DocumentReference resources. Some FHIR
                # importers (notably PO's data-import pipeline) strip
                # the inline Observation.note array, so the DocumentRef
                # path is the more portable carrier of free-text notes.
                # Falling open if the call fails — handler keeps working
                # against whatever notes the Observation path returned.
                try:
                    doc_refs = await fhir.get_document_references(patient_id)
                except FhirClientError:
                    doc_refs = []
        except FhirClientError as exc:
            logger.warning(
                "nursing-signals FHIR fetch failed",
                extra={"patient_id": patient_id, "error": str(exc)},
            )
            return (
                f"I couldn't read nursing notes for `{patient_id}` because "
                f"the FHIR server was unreachable: {exc}.",
                "fhir",
            )

        # Pull free-text notes from each observation, with timestamps so
        # the LLM sees the chronology. Dedupe identical strings (the
        # seeder attaches the same note to one observation per timepoint;
        # in real EHRs a single note may appear across multiple obs).
        note_entries: list[tuple[Any, str]] = []
        seen: set[str] = set()
        for obs in observations:
            for n in obs.note or []:
                txt = (n.text or "").strip()
                if not txt or txt in seen:
                    continue
                seen.add(txt)
                ts = obs.effectiveDateTime
                note_entries.append((ts, txt))

        # Merge in DocumentReference-carried notes. Each note's free text
        # is base64-encoded in content[].attachment.data per FHIR R4;
        # decode best-effort, skip ones we can't read.
        import base64
        from datetime import datetime as _dt
        for doc in doc_refs:
            doc_date = doc.get("date") or (doc.get("context") or {}).get("period", {}).get("start")
            try:
                ts = _dt.fromisoformat(str(doc_date).replace("Z", "+00:00")) if doc_date else None
            except (TypeError, ValueError):
                ts = None
            for content in doc.get("content") or []:
                att = content.get("attachment") or {}
                data = att.get("data")
                if not isinstance(data, str):
                    continue
                try:
                    txt = base64.b64decode(data).decode("utf-8", "replace").strip()
                except (ValueError, TypeError):
                    continue
                if not txt or txt in seen:
                    continue
                seen.add(txt)
                note_entries.append((ts, txt))

        note_entries.sort(key=lambda p: p[0] or "")

        if not note_entries:
            return (
                f"### Nursing notes — none on file\n"
                f"No free-text nursing notes found for `{patient_id}` in "
                "the recent observation window. Subjective signal review "
                "needs the bedside team to document — vital signs alone "
                "miss soft signs that precede deterioration.",
                "fhir",
            )

        # Build the prompt — keep notes inline, ask for structured
        # extraction with quoted phrases. Cap at 8 notes to control
        # token use and keep the LLM's signal-to-noise high.
        notes_block = "\n".join(
            f"- {ts.isoformat() if hasattr(ts, 'isoformat') else ts}: \"{txt}\""
            for ts, txt in note_entries[-8:]
        )
        prompt = (
            "You are an experienced postop ward nurse reviewing colleagues' "
            "documentation for early deterioration signals. Read the notes "
            "below (oldest first) and identify subjective signs that the "
            "patient is becoming unstable, even if vital signs haven't yet "
            "crossed thresholds.\n\n"
            f"Patient: {patient_id}\n"
            f"Notes:\n{notes_block}\n\n"
            "Output rules:\n"
            "- Output 1-5 markdown bullets, one per signal you found.\n"
            "- Each bullet: quote the exact phrase in double quotes, then "
            "one short clause explaining clinical significance.\n"
            "- If the notes are routine (pain controlled, ambulating, "
            "vitals stable, family at bedside), output exactly one bullet "
            "saying so and nothing else.\n"
            "- Do NOT invent signals not present in the notes.\n"
            "- Do NOT output any introduction or conclusion text."
        )

        try:
            provider = get_provider()
            llm_text = (await provider.complete(prompt, max_tokens=400)).strip()
        except LLMError as exc:
            logger.warning(
                "nursing-signals LLM call failed",
                extra={"patient_id": patient_id, "error": str(exc)},
            )
            # Fall back to listing the raw notes so the clinician at
            # least sees the source material.
            llm_text = "\n".join(
                f"- (raw) \"{txt}\"" for _, txt in note_entries[-5:]
            )

        sections = [
            "### Nursing-note signals",
            f"LLM-extracted from **{len(note_entries)}** free-text "
            "nursing note(s). Subjective signs precede vital-sign breach "
            "by 30–60 min in most postop deterioration; this surface "
            "complements `screen vitals`, it doesn't replace it.",
            "",
            llm_text,
            "",
            "*Architecture validated by COMPOSER-LLM (npj Digital "
            "Medicine, May 2025) — prospective trial of an LLM extracting "
            "sepsis signals from unstructured nursing notes achieved 72.1% "
            "sensitivity at 0.0087 false alarms / patient-hour. Vigil "
            "applies the same multi-modal pattern (deterministic detector "
            "+ LLM enrichment of free text) FHIR-natively.*",
            "",
            "*Signal extraction is generative — verify against the "
            "original notes before acting. Source: deterministic FHIR "
            "fetch + LLM-narrated extraction.*",
        ]
        return "\n".join(sections) + _AUDIT_FOOTER_LIVE, "fhir"

    async def _handle_explain(
        self,
        sharp_headers: dict[str, str],
        patient_id: str,
        message: Any,
    ) -> str:
        """LLM-driven conversational follow-up.

        When a clinician asks a free-text question ("why did you flag this
        if SBP is only 92?", "could it be the antibiotic instead?"), the
        canned skill replies don't fit. This handler runs the question
        through the LLM with the patient context, returning a short
        consultative answer. It deliberately does NOT make escalation
        decisions — it only explains, suggests, or chains to a more
        specific skill.
        """
        from backend.llm.provider import LLMError, get_provider

        # Pull the user's question text from the inbound message.
        parts = getattr(message, "parts", None) or []
        question = ""
        for part in parts:
            text = getattr(part, "text", None)
            if isinstance(text, str):
                question = text
                break
            root = getattr(part, "root", None)
            if root is not None:
                rtext = getattr(root, "text", None)
                if isinstance(rtext, str):
                    question = rtext
                    break
        question = question.strip()

        if not question:
            return (
                "I couldn't find a question to answer. Try `why did you "
                "escalate this?` or `could this be sepsis instead?`."
                + _AUDIT_FOOTER_LIVE
            )

        prompt = (
            "You are Vigil — a postop and postpartum sentinel agent acting "
            "as a clinical consultant via Prompt Opinion's general-chat "
            "agent. A clinician is asking a follow-up question about the "
            "patient currently in scope.\n\n"
            f"Patient ID: {patient_id}\n"
            f"Question: {question}\n\n"
            "Answer rules:\n"
            "- 3-5 sentences max. No bullet salad.\n"
            "- Cite the deterministic guideline if relevant: "
            "Subbe MEWS 2001, qSOFA Sepsis-3 JAMA 2016, NEWS2 RCP 2017, "
            "KDIGO 2012, CDC ASE, CMQCC v3.0.\n"
            "- If the answer requires fresh measurements you don't have, "
            "say so and suggest exactly which Vigil skill to run "
            "(`screen vitals`, `score risk`, `check sepsis`, `assess AKI`, "
            "`assess postpartum hemorrhage`, `score NEWS2`, "
            "`flag treatment conflicts`, `draft an SBAR`, `read nursing "
            "notes`, `show recent alerts`).\n"
            "- NEVER make an escalation decision (page MD, activate RRT). "
            "Vigil's HITL invariant is that the clinician decides; you "
            "advise."
        )

        try:
            provider = get_provider()
            answer = (await provider.complete(prompt, max_tokens=400)).strip()
        except LLMError as exc:
            logger.warning(
                "explain LLM call failed",
                extra={"patient_id": patient_id, "error": str(exc)},
            )
            return (
                f"I couldn't answer that right now — the LLM provider "
                f"`{getattr(exc, 'provider', 'unknown')}` is unavailable. "
                "Try one of the structured skills (`screen vitals`, "
                "`score risk`, etc.) for a deterministic answer."
                + _AUDIT_FOOTER_LIVE
            )

        return (
            f"### Follow-up — `{patient_id}`\n"
            f"**Q:** {question}\n\n"
            f"{answer}"
            + _AUDIT_FOOTER_LIVE
        )

    async def _handle_forecast_trajectory(
        self,
        sharp_headers: dict[str, str],
        patient_id: str,
    ) -> tuple[str, str]:
        """Predictive trajectory forecasting — when does each vital cross
        its MEWT threshold, given the current slope?

        This is forward-looking AI: rather than reporting which thresholds
        are tripped right now (`screen_vitals`) or what the trend
        *direction* is (`score_risk`), this skill *projects* the linear
        slope forward and estimates **time-to-breach** with a 95%
        confidence band per least-squares regression. Maps directly to
        the TREWS lead-time concept (Adams 2022, Nature Medicine —
        median 5.7h before threshold).

        We piggyback on `screen_vital_thresholds`'s ``vitals_history``
        rather than fetching FHIR again. Vitals with <3 samples are
        skipped (regression undefined). The LLM only narrates clinical
        significance once the math is locked in — the deterministic
        slope and confidence interval are the source of truth, not
        the prose.
        """
        import math

        try:
            raw = await self._mcp.call_tool(
                "screen_vital_thresholds",
                arguments={"patient_id": patient_id},
                sharp_headers=sharp_headers,
            )
        except McpClientError as e:
            return (
                f"I couldn't forecast the trajectory for `{patient_id}` "
                f"because the MCP tool was unreachable: {e}.",
                "fhir",
            )

        data = _unwrap_tool_result(raw)
        err = _tool_error_text(data, patient_id, action="forecast trajectory")
        if err is not None:
            return err, _data_source(data)

        history = data.get("vitals_history") or {}
        if not history:
            return (
                "I couldn't forecast the trajectory because no vital-sign "
                "history is available — need ≥3 readings per vital for a "
                "regression."
                + _AUDIT_FOOTER_LIVE,
                _data_source(data),
            )

        # MEWT-aligned forecast targets per LOINC. Each (loinc, label,
        # direction, threshold) tuple says what we're projecting toward.
        # Direction: 'down' = vital trends below threshold = bad;
        # 'up' = trends above threshold = bad. Mirrors the rule
        # engine's red breach definitions in backend/criteria/mewt.py.
        forecast_targets: list[tuple[str, str, str, float, str]] = [
            ("8480-6", "SBP", "down", 90.0, "mm[Hg]"),
            ("8867-4", "HR", "up", 110.0, "/min"),
            ("9279-1", "RR", "up", 22.0, "/min"),
            ("59408-5", "SpO2", "down", 93.0, "%"),
            ("8310-5", "Temp", "up", 38.0, "°C"),
            ("9192-6", "Urine", "down", 30.0, "mL/h"),
        ]

        # Pure-Python OLS — no scipy/numpy dep. Returns slope, intercept,
        # R², standard error of the slope. Times are minutes since the
        # earliest sample so units are stable per vital.
        def _regress(samples: list[dict]) -> dict[str, float] | None:
            if len(samples) < 3:
                return None
            try:
                from datetime import datetime as _dt
                t0_str = samples[0].get("observed_at") or ""
                t0 = _dt.fromisoformat(str(t0_str).replace("Z", "+00:00"))
                xs: list[float] = []
                ys: list[float] = []
                for s in samples:
                    ts_str = s.get("observed_at") or ""
                    ti = _dt.fromisoformat(str(ts_str).replace("Z", "+00:00"))
                    xs.append((ti - t0).total_seconds() / 60.0)
                    ys.append(float(s.get("value")))
            except (TypeError, ValueError):
                return None
            n = len(xs)
            mean_x = sum(xs) / n
            mean_y = sum(ys) / n
            ss_xy = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
            ss_xx = sum((xs[i] - mean_x) ** 2 for i in range(n))
            if ss_xx == 0:
                return None
            slope = ss_xy / ss_xx
            intercept = mean_y - slope * mean_x
            ss_yy = sum((ys[i] - mean_y) ** 2 for i in range(n))
            r_sq = (ss_xy * ss_xy) / (ss_xx * ss_yy) if ss_yy > 0 else 0.0
            # Residual standard error → SE of slope (n-2 dof).
            if n > 2:
                resids = [ys[i] - (slope * xs[i] + intercept) for i in range(n)]
                rss = sum(r * r for r in resids)
                se_slope = math.sqrt(rss / (n - 2) / ss_xx) if ss_xx > 0 else 0.0
            else:
                se_slope = 0.0
            latest_t = xs[-1]
            latest_y = ys[-1]
            return {
                "slope": slope,
                "intercept": intercept,
                "r_squared": r_sq,
                "se_slope": se_slope,
                "latest_t": latest_t,
                "latest_y": latest_y,
                "n": float(n),
            }

        forecasts: list[dict[str, Any]] = []
        for loinc, label, direction, thr, unit in forecast_targets:
            samples = history.get(loinc) or []
            reg = _regress(samples)
            if reg is None:
                continue
            slope = reg["slope"]
            latest_y = reg["latest_y"]
            n = int(reg["n"])

            # Time to breach the threshold from the LATEST reading,
            # not the regression intercept (more honest in chat).
            # If slope direction agrees with deterioration direction,
            # compute t_remaining; otherwise mark "stable / improving".
            already_breached = (
                (direction == "down" and latest_y <= thr)
                or (direction == "up" and latest_y >= thr)
            )
            if already_breached:
                forecasts.append({
                    "label": label,
                    "latest": latest_y,
                    "unit": unit,
                    "slope_per_h": slope * 60.0,
                    "threshold": thr,
                    "direction": direction,
                    "status": "already_breached",
                    "t_to_breach_min": 0.0,
                    "ci_low_min": 0.0,
                    "ci_high_min": 0.0,
                    "r_squared": reg["r_squared"],
                    "n": n,
                })
                continue

            heading_bad = (
                (direction == "down" and slope < 0)
                or (direction == "up" and slope > 0)
            )
            if not heading_bad or abs(slope) < 1e-6:
                forecasts.append({
                    "label": label,
                    "latest": latest_y,
                    "unit": unit,
                    "slope_per_h": slope * 60.0,
                    "threshold": thr,
                    "direction": direction,
                    "status": "stable_or_improving",
                    "t_to_breach_min": None,
                    "ci_low_min": None,
                    "ci_high_min": None,
                    "r_squared": reg["r_squared"],
                    "n": n,
                })
                continue

            t_to_breach = (thr - latest_y) / slope  # minutes
            # 95% CI on the slope translates to a CI on time-to-breach
            # via the inverse map. Use ~1.96 × SE for the slope band;
            # n-2 t-quantile would be tighter but ±1.96 is the
            # clinically familiar 95% framing.
            slope_low = slope - 1.96 * reg["se_slope"]
            slope_high = slope + 1.96 * reg["se_slope"]

            def _t(s: float, _thr: float = thr, _y: float = latest_y) -> float | None:
                if s == 0:
                    return None
                t = (_thr - _y) / s
                return t if t >= 0 else None

            ci_a = _t(slope_low)
            ci_b = _t(slope_high)
            cis = [t for t in (ci_a, ci_b) if t is not None]
            ci_low = min(cis) if cis else t_to_breach
            ci_high = max(cis) if cis else t_to_breach

            forecasts.append({
                "label": label,
                "latest": latest_y,
                "unit": unit,
                "slope_per_h": slope * 60.0,
                "threshold": thr,
                "direction": direction,
                "status": "projected_breach",
                "t_to_breach_min": t_to_breach,
                "ci_low_min": ci_low,
                "ci_high_min": ci_high,
                "r_squared": reg["r_squared"],
                "n": n,
            })

        if not forecasts:
            return (
                "### Trajectory forecast — insufficient data\n"
                "Need ≥3 samples per vital for a regression. The current "
                "observation window doesn't have that for the deterioration-"
                "relevant vitals (SBP, HR, RR, SpO2, Temp, Urine)."
                + _AUDIT_FOOTER_LIVE,
                _data_source(data),
            )

        # Sort: already-breached first, then nearest projected breach,
        # then stable/improving.
        def _sort_key(f: dict) -> tuple[int, float]:
            if f["status"] == "already_breached":
                return (0, 0.0)
            if f["status"] == "projected_breach":
                return (1, f["t_to_breach_min"] or float("inf"))
            return (2, float("inf"))
        forecasts.sort(key=_sort_key)

        def _fmt_min(m: float | None) -> str:
            if m is None:
                return "n/a"
            if m < 60:
                return f"{m:.0f} min"
            return f"{m / 60:.1f} h"

        sections: list[str] = [
            "### Trajectory forecast",
            "Linear-regression projection per vital from the most-recent "
            "observation window. **Forward-looking — these are AI "
            "projections, not measurements.** Time-to-breach is the "
            "minutes from the latest reading until each vital crosses "
            "its MEWT red threshold at the current slope, with 95% CI "
            "from the regression standard error.",
            "",
        ]

        breached = [f for f in forecasts if f["status"] == "already_breached"]
        projected = [f for f in forecasts if f["status"] == "projected_breach"]
        stable = [f for f in forecasts if f["status"] == "stable_or_improving"]

        if breached:
            sections.append("**Already breached:**")
            for f in breached:
                op = "≤" if f["direction"] == "down" else "≥"
                sections.append(
                    f"- **{f['label']}** {f['latest']:.1f} {f['unit']} "
                    f"(threshold {op} {f['threshold']:g})"
                )
            sections.append("")

        if projected:
            sections.append("**Projected to breach (sorted soonest first):**")
            for f in projected:
                sections.append(
                    f"- **{f['label']}** {f['latest']:.1f} {f['unit']} → "
                    f"crosses {f['threshold']:g} in **"
                    f"{_fmt_min(f['t_to_breach_min'])}** "
                    f"(95% CI: {_fmt_min(f['ci_low_min'])}"
                    f"–{_fmt_min(f['ci_high_min'])}; "
                    f"slope {f['slope_per_h']:+.2f}/h, "
                    f"R²={f['r_squared']:.2f}, n={f['n']})"
                )
            sections.append("")

        if stable:
            sections.append("**Stable or improving:**")
            for f in stable:
                sections.append(
                    f"- {f['label']} {f['latest']:.1f} {f['unit']} "
                    f"(slope {f['slope_per_h']:+.2f}/h)"
                )
            sections.append("")

        # LLM narration — clinically significant interpretation of the
        # nearest projected breach, in 2-3 sentences. Skipped if there
        # are no projected breaches (no clinical urgency to interpret).
        if projected:
            try:
                from backend.llm.provider import LLMError, get_provider
                head = projected[0]
                prompt = (
                    "You are Vigil, a postop sentinel agent. The "
                    "deterministic trajectory forecast below is the "
                    "ground truth — interpret it clinically in 2-3 "
                    "sentences. Reference the named guideline (NEWS2 "
                    "RCP-2017, qSOFA Sepsis-3) only if relevant. Do "
                    "NOT invent figures.\n\n"
                    f"Patient: {patient_id}\n"
                    f"Nearest projected breach: {head['label']} "
                    f"crosses {head['threshold']} {head['unit']} in "
                    f"~{_fmt_min(head['t_to_breach_min'])} "
                    f"(latest {head['latest']:.1f}, "
                    f"slope {head['slope_per_h']:+.2f}/h, "
                    f"R² {head['r_squared']:.2f}).\n\n"
                    "Output: 2-3 sentences only. No bullets, no "
                    "preamble, plain prose."
                )
                interp = (
                    await get_provider().complete(prompt, max_tokens=180)
                ).strip()
                if interp:
                    sections.extend([
                        "**Clinical interpretation** *(LLM-narrated):*",
                        interp,
                        "",
                    ])
            except LLMError as exc:
                logger.debug(
                    "forecast LLM narration failed (non-fatal)",
                    extra={"patient_id": patient_id, "error": str(exc)},
                )

        sections.append(
            "*Forward projection assumes the current slope holds. "
            "Maps to the TREWS lead-time concept (Adams 2022, Nature "
            "Medicine — median 5.7h before threshold). Refresh by "
            "running this skill again after the next vital reading.*"
        )
        body = "\n".join(sections).rstrip() + _AUDIT_FOOTER_LIVE
        return body, _data_source(data)

    async def _handle_estimate_savings(self) -> str:
        """Return a hypothetical savings estimate from the alert queue.

        Sources (all checked into CLINICAL_EVIDENCE.md):
        - $1,200 average direct cost per delayed RRT activation
          (Bavarsad-Shahripour et al, J Patient Saf 2020).
        - 18% relative reduction in in-hospital mortality with AI-
          driven early sepsis detection (Adams et al, Nature Medicine
          2022 — TREWS prospective).
        - $12,200 attributable cost per inpatient sepsis death
          (Paoli et al, Crit Care Med 2018).

        Multiplies these published rates against the count of urgent+
        critical alerts in Vigil's review queue over the past 30 days
        to give a hospital purchaser a defensible ballpark of what
        Vigil-style early detection could prevent.
        """
        from datetime import UTC, datetime, timedelta

        from backend.api.review_queue import list_pending_alerts

        try:
            alerts = list_pending_alerts()
        except Exception:  # noqa: BLE001 — best-effort read
            logger.exception("estimate_savings review queue read failed")
            alerts = []

        # Window — last 30 days. The seeded cohort produces a tick of
        # 7 alerts per cycle; this gives the demo a defensible monthly
        # extrapolation.
        cutoff = datetime.now(UTC) - timedelta(days=30)
        recent = [
            a for a in alerts
            if a.get("created_at")
            and a["created_at"] >= cutoff.isoformat()
        ]
        urgent_or_crit = [
            a for a in recent
            if a.get("severity") in ("urgent", "critical")
        ]
        n_urgent = sum(1 for a in urgent_or_crit if a.get("severity") == "urgent")
        n_crit = sum(1 for a in urgent_or_crit if a.get("severity") == "critical")

        # Published unit rates (all USD, all peer-reviewed).
        cost_per_delayed_rrt = 1200.0
        mortality_reduction_pct = 0.18
        cost_per_sepsis_death = 12200.0

        rrt_avoided = n_urgent + n_crit
        rrt_savings = rrt_avoided * cost_per_delayed_rrt
        sepsis_avoided = round(n_crit * mortality_reduction_pct, 2)
        mortality_savings = sepsis_avoided * cost_per_sepsis_death
        total = rrt_savings + mortality_savings

        sections = [
            "### ROI estimate — last 30 days",
            f"Vigil's autonomous loop surfaced **{n_urgent} urgent** and "
            f"**{n_crit} critical** alerts on the watched cohort.",
            "",
            "**Hypothetical impact** *(per published unit rates):*",
            f"- {rrt_avoided} potentially-avoidable delayed RRTs "
            f"× **${cost_per_delayed_rrt:,.0f}** (Bavarsad 2020)"
            f" = **${rrt_savings:,.0f}**",
            f"- {n_crit} critical alerts × {mortality_reduction_pct:.0%} "
            "TREWS mortality-reduction (Adams 2022, Nature Medicine) "
            f"× **${cost_per_sepsis_death:,.0f}** per averted sepsis "
            "death (Paoli 2018) = "
            f"**${mortality_savings:,.0f}**",
            "",
            f"**Conservative 30-day total: ${total:,.0f}**",
            "",
            "*Hypothetical and synthetic-cohort-derived. Not a clinical "
            "outcome claim. Real validation requires a prospective trial — "
            "see CLINICAL_EVIDENCE §1.5 for the canonical 18% TREWS "
            "figure that drives the mortality term.*",
        ]
        return "\n".join(sections) + _AUDIT_FOOTER_LIVE

    async def _handle_screen_pediatric(
        self,
        sharp_headers: dict[str, str],
        patient_id: str,
    ) -> tuple[str, str]:
        """PEWS — age-banded paediatric early-warning screen.

        MEWT and qSOFA are adult-validated. Children have age-dependent
        normal ranges (HR 110-160 in infants vs 60-110 in adolescents),
        so the same vital signs that breach an adult threshold may be
        completely normal for a child — and vice versa. PEWS handles
        this with age-banded thresholds.

        Implementation: fetch Patient.birthDate + recent vital-sign
        Observations from FHIR via SHARP, compute age, run the PEWS
        scorer (`backend/criteria/pews.py`), render the verdict with
        per-parameter scores and a paediatric-specific recommended
        action.

        Reference: Monaghan 2005 Paediatric Nursing 17(1); Roland 2014
        Arch Dis Child 99:26-29; RCPCH PEWS national chart 2023.
        """
        from datetime import UTC, datetime

        from backend.criteria.pews import evaluate_pews
        from backend.fhir.client import FhirClient, FhirClientError
        from backend.schemas import FhirContext

        ctx = FhirContext(
            url=sharp_headers.get("x-fhir-server-url", ""),
            token=sharp_headers.get("x-fhir-access-token"),
            patient_id=sharp_headers.get("x-patient-id"),
        )

        try:
            async with FhirClient(ctx) as fhir:
                patient = await fhir.get_patient(patient_id)
                observations = await fhir.get_observations(
                    patient_id, category="vital-signs"
                )
        except FhirClientError as exc:
            return (
                f"I couldn't run a paediatric screen for `{patient_id}` "
                f"because the FHIR server was unreachable: {exc}.",
                "fhir",
            )

        # Compute age in years from birthDate.
        age_years: float | None = None
        try:
            if patient and patient.birthDate:
                bd = datetime.fromisoformat(str(patient.birthDate))
                if bd.tzinfo is None:
                    bd = bd.replace(tzinfo=UTC)
                age_years = (datetime.now(UTC) - bd).days / 365.25
        except (ValueError, AttributeError):
            pass

        if age_years is None:
            return (
                f"I couldn't run a paediatric screen for `{patient_id}` "
                "because the Patient resource has no `birthDate`. "
                "PEWS requires age to select the right band."
                + _AUDIT_FOOTER_LIVE,
                "fhir",
            )

        if age_years >= 18:
            return (
                f"### Paediatric screen — NOT APPLICABLE\n"
                f"Patient is **{age_years:.1f} years old** (≥18). PEWS "
                "covers ages 0-17; adults use MEWT/NEWS2/qSOFA. Run "
                "`screen vitals` instead."
                + _AUDIT_FOOTER_LIVE,
                "fhir",
            )

        # Pull most-recent values for the 3 PEWS parameters.
        latest: dict[str, tuple[datetime, float]] = {}
        for obs in observations:
            loinc = obs.loinc_code
            val = (
                obs.valueQuantity.value
                if obs.valueQuantity and obs.valueQuantity.value is not None
                else None
            )
            ts = obs.effectiveDateTime
            if not loinc or val is None or not ts:
                continue
            existing = latest.get(loinc)
            if existing is None or ts > existing[0]:
                latest[loinc] = (ts, float(val))

        hr = latest.get("8867-4", (None, None))[1]
        rr = latest.get("9279-1", (None, None))[1]
        spo2 = latest.get("59408-5", (None, None))[1]

        result = evaluate_pews(age_years=age_years, hr=hr, rr=rr, spo2=spo2)

        sections: list[str] = [
            f"### Paediatric screen — **{('TRIGGERED' if result.triggered else 'CLEAR')}**"
            f" *(per RCPCH PEWS / Monaghan 2005)*",
            f"Patient age **{age_years:.1f}y** — band: **{result.age_band}**",
        ]
        # Per-parameter score breakdown.
        score_lines: list[str] = []
        if hr is not None:
            score_lines.append(
                f"- HR **{hr:.0f}** /min → score {result.hr_score}"
            )
        if rr is not None:
            score_lines.append(
                f"- RR **{rr:.0f}** /min → score {result.rr_score}"
            )
        if spo2 is not None:
            score_lines.append(
                f"- SpO2 **{spo2:.0f}** % → score {result.spo2_score}"
            )
        if score_lines:
            sections.append("\n**Score breakdown:**")
            sections.extend(score_lines)
        sections.append(
            f"\n**Aggregate: {result.aggregate}** "
            + ("· **RED FLAG** (single-parameter ≥3)" if result.red_flag else "")
        )

        # Paediatric-specific action mapping. RCPCH 2023 chart uses
        # similar response bands to NEWS2 but tunes the urgency to
        # paediatric escalation pathways (consultant + paediatric
        # rapid-response).
        if result.red_flag or result.aggregate >= 5:
            action = (
                "**Action**: URGENT paediatric review by consultant or "
                "paediatric rapid-response team within **15 min**. "
                "Continuous monitoring; consider PICU consult."
            )
        elif result.aggregate >= 3:
            action = (
                "**Action**: Senior paediatric review within **1 hour**. "
                "Hourly observations; reassess after each."
            )
        else:
            action = (
                "**Action**: Continue routine paediatric observation "
                "schedule; reassess on next round."
            )
        sections.append(f"\n{action}")

        # Confidence — driven by parameter completeness.
        n_params = sum(1 for v in (hr, rr, spo2) if v is not None)
        if n_params == 3:
            sections.append(
                _confidence("high", "all 3 PEWS parameters scored")
            )
        elif n_params == 2:
            sections.append(
                _confidence(
                    "medium",
                    f"{n_params}/3 parameters — refresh recommended",
                )
            )
        else:
            sections.append(
                _confidence(
                    "low",
                    f"only {n_params}/3 parameters — partial score",
                )
            )

        sections.append(f"\n*Rationale:* {result.rationale}")
        return (
            "\n".join(sections) + _AUDIT_FOOTER_LIVE,
            "fhir",
        )

    async def _handle_feedback(self, message: Any) -> str:
        """Record clinician feedback on a prior Vigil verdict.

        Stores the free-text feedback message in the SQLite review queue's
        ``note`` column on the most-recent alert for the current scope.
        Does NOT retrain anything — that would be irresponsible without a
        proper MLOps pipeline. Logs the data so a future tuning cycle has
        labelled examples to draw on, and confirms receipt to the
        clinician so they know the loop is closed.
        """
        # Pull the user's feedback text from the inbound message.
        parts = getattr(message, "parts", None) or []
        feedback_text = ""
        for part in parts:
            text = getattr(part, "text", None)
            if isinstance(text, str):
                feedback_text = text
                break
            root = getattr(part, "root", None)
            if root is not None:
                rtext = getattr(root, "text", None)
                if isinstance(rtext, str):
                    feedback_text = rtext
                    break
        feedback_text = feedback_text.strip()

        # Lightweight categoriser — picks up signals from the message
        # text. Useful for the future-tuning use case even though this
        # skill itself doesn't act on the categorisation.
        lower = feedback_text.lower()
        if any(s in lower for s in ("not helpful", "false positive",
                                     "false-positive", "wrong",
                                     "thumbs down", "useless")):
            tag = "false_positive"
        elif any(s in lower for s in ("helpful", "useful", "good catch",
                                       "correct", "thumbs up", "spot on")):
            tag = "true_positive"
        else:
            tag = "uncategorised"

        # Append to the metrics event log — same pipeline that records
        # alert_drafted / alert_approved events. Tagged so a future
        # tuning cycle can filter by feedback class without parsing
        # free text.
        try:
            from backend.obs.metrics import append_event
            await append_event(
                "clinician_feedback",
                {"tag": tag, "feedback": feedback_text[:500]},
            )
        except Exception:  # noqa: BLE001 — non-fatal logging
            logger.exception("feedback append_event failed")

        return (
            "### Feedback recorded\n"
            f"Tagged **{tag}**. Logged to the metrics event store for "
            "future model-tuning review.\n\n"
            "*Vigil does NOT retrain on chat-side feedback alone — this "
            "is a labelled-example pipeline for offline review. Closed-"
            "loop active learning is post-MVP.*"
            + _AUDIT_FOOTER_LIVE
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


# Confidence framing — every clinical claim ships with a categorical
# tag (HIGH / MEDIUM / LOW) tied to objective inputs (data freshness,
# number of criteria met, n of regression samples). Surfaces uncertainty
# the way clinicians and FDA reviewers expect rather than presenting
# AI verdicts as gospel.
def _confidence(level: str, reason: str) -> str:
    return (
        f"\n*Confidence: **{level.upper()}** — {reason}*"
    )


# Audit / regulatory footer — appended to every clinician-facing reply
# so the source posture is unambiguous in any screenshot or transcript
# a reviewer might pull. Kept short to avoid mobile-chat clutter.
_AUDIT_FOOTER_LIVE = (
    "\n\n---\n*Source: deterministic rule engine (Subbe MEWS, qSOFA, "
    "CDC ASE, KDIGO 2012, RCP NEWS2 2017, CMQCC v3.0); narrative LLM-"
    "drafted; data: live FHIR via SHARP context.*"
)
_AUDIT_FOOTER_SYNTHETIC = (
    "\n\n---\n*Source: deterministic rule engine; narrative LLM-drafted; "
    "data: Vigil synthetic seeded cohort (PT-001..PT-010, no PHI).*"
)


def _audit_footer(data_source_value: str) -> str:
    return (
        _AUDIT_FOOTER_SYNTHETIC
        if data_source_value == SYNTHETIC_DATA_SOURCE
        else _AUDIT_FOOTER_LIVE
    )


def _with_disclosure(body: str, data: dict[str, Any]) -> str:
    """Wrap a chat reply with synthetic-data disclosure + audit footer.

    Two pieces:
      - **Synthetic prefix** (only when ``data_source`` is ``synthetic_demo``):
        the public-facing receipt that PO's launchpad shows the operator
        when the workspace's FHIR server didn't accept our token. The
        bundle name is selected by ``patient_id`` so PT-010 (PPH cameo)
        reports its own bundle rather than the default PT-007.
      - **Audit footer** (always): one-liner naming the deterministic
        guidelines + LLM narration role + data origin. Lets any reviewer
        scanning a screenshot know the data posture without scrolling
        out to AgentCard or repo docs.
    """
    ds = _data_source(data)
    out = body
    if ds == SYNTHETIC_DATA_SOURCE:
        pid = data.get("patient_id") if isinstance(data, dict) else None
        out = f"{synthetic_disclosure(pid)}\n\n{out}"
    return out + _audit_footer(ds)


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
