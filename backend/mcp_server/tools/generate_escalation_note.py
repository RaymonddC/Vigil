"""B5 — generate_escalation_note implementation.

Consumes outputs from B2/B3/B4, fetches Patient + Encounter context from
FHIR, calls the LLM provider for an SBAR narrative, and returns an
EscalationOutput with an unpersisted FHIR Communication draft.

The tool NEVER writes to FHIR — the communication_draft is stored in
the SQLite review queue and only written by the approve endpoint.

Reference: API_CONTRACTS.md §1.4, BUILD_PLAN.md B5
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any, Literal

from backend.cache import get_llm_cached, set_llm_cached
from backend.fhir.client import FhirClient, FhirClientError, is_fhir_auth_error
from backend.llm.provider import LLMError, get_provider
from backend.mcp_server.synthetic_fallback import (
    LIVE_DATA_SOURCE,
    SYNTHETIC_DATA_SOURCE,
    get_synthetic_encounter,
    get_synthetic_patient,
    is_fallback_enabled,
)
from backend.obs.metrics import record_llm_call, tool_call_timer
from backend.schemas import (
    SBAR,
    EscalationOutput,
    FhirContext,
    ToolStatus,
)

logger = logging.getLogger("vigil.mcp.tools.generate_escalation_note")


def _determine_severity(
    vitals_result: dict[str, Any],
    risk_result: dict[str, Any],
    sepsis_result: dict[str, Any],
) -> Literal["info", "urgent", "critical"]:
    """Determine alert severity from the three tool outputs.

    Severity mapping (Vigil operational — tuned for demo narrative clarity):

    critical:
      - Sepsis suspected (CDC ASE or SIRS fallback), OR
      - High risk band AND ≥2 absolute red-zone MEWT breaches simultaneously
        (represents frank hemodynamic collapse, e.g. PT-010 PPH at T+4h
        with both HR >130 and SBP <90 simultaneously).

    urgent:
      - High or moderate risk band (single-threshold deterioration), OR
      - MEWT triggered with at least one absolute red breach.

    info:
      - Only mild (yellow) or trend-based signals.

    Rationale: Shields 2016 MEWT (CLINICAL_EVIDENCE §2.2) distinguishes
    "severe" triggers (any single parameter in the extreme zone = act NOW)
    from "non-severe" (≥2 sustained abnormals = watch and reassess). Vigil
    maps dual absolute-red to "critical" to mirror this stratification:
    single-threshold trend-based deteriorators (PT-004..007) warrant
    urgent escalation, while dual-parameter shock (PT-010 PPH) and sepsis
    (PT-008/009) warrant critical. TREND-rule breaches are excluded from the
    red-count because they fire earlier / before absolute thresholds and
    intentionally carry lower intrinsic severity. (Vigil operational choice.)
    """
    if sepsis_result.get("sepsis_suspected"):
        return "critical"

    # Count absolute (non-TREND) red-severity MEWT breaches.
    # TREND breaches represent slope-based early warnings, not frank threshold
    # violations — they are excluded from the dual-red critical check.
    breaches = vitals_result.get("breaches", [])
    absolute_red_count = sum(
        1 for b in breaches
        if b.get("severity") == "red" and b.get("loinc") != "TREND"
    )

    risk_band = risk_result.get("risk_band", "low")

    # Dual absolute-red at high risk = critical (frank hemodynamic collapse).
    # Example: PT-010 PPH at T+4h — HR 132 (>130 red) AND SBP 82 (<90 red).
    if risk_band == "high" and absolute_red_count >= 2:
        return "critical"

    if risk_band in ("high", "moderate"):
        return "urgent"

    if vitals_result.get("status") == "triggered" and absolute_red_count >= 1:
        return "urgent"

    return "info"


def _build_prompt(
    patient_id: str,
    patient_name: str,
    encounter_id: str | None,
    vitals_result: dict[str, Any],
    risk_result: dict[str, Any],
    sepsis_result: dict[str, Any],
    recipient_role: str,
    severity: str,
) -> str:
    """Build the LLM prompt for SBAR generation."""
    breaches_text = ""
    for b in vitals_result.get("breaches", []):
        breaches_text += (
            f"  - {b.get('label', '?')}: {b.get('value', '?')} "
            f"{b.get('unit', '')} (threshold {b.get('threshold', '?')}, "
            f"severity {b.get('severity', '?')})\n"
        )
    if not breaches_text:
        breaches_text = "  (none)\n"

    criteria_text = ""
    for c in sepsis_result.get("criteria_met", []):
        criteria_text += f"  - {c}\n"
    if not criteria_text:
        criteria_text = "  (none)\n"

    return f"""You are a clinical decision support system generating an SBAR
(Situation, Background, Assessment, Recommendation) escalation note.

Patient: {patient_name} (ID: {patient_id})
Encounter: {encounter_id or 'unknown'}
Recipient: {recipient_role}
Severity: {severity}

VITAL SIGN SCREENING:
Status: {vitals_result.get('status', 'unknown')}
Breaches:
{breaches_text}
DETERIORATION RISK:
qSOFA score: {risk_result.get('qsofa_score', 0)}/3
Risk band: {risk_result.get('risk_band', 'unknown')}
Composite risk: {risk_result.get('composite_risk', 0.0)}
Rationale: {risk_result.get('rationale', '')}
Contributing conditions: {', '.join(risk_result.get('contributing_conditions', [])) or 'none'}

SEPSIS SCREENING:
Sepsis suspected: {sepsis_result.get('sepsis_suspected', False)}
Mode: {sepsis_result.get('mode', 'unknown')}
Criteria met:
{criteria_text}
Generate a concise SBAR note in exactly this JSON format (no markdown, no extra text):
{{
  "situation": "one paragraph",
  "background": "one paragraph",
  "assessment": "one paragraph",
  "recommendation": "one paragraph"
}}

Be specific, clinical, and actionable. Reference the actual values above.
Address the note to the {recipient_role}."""


# Match labeled-text SBAR sections in LLM output, e.g.
#   "S: foo\nB: bar\nA: baz\nR: qux"
# Tolerates case variation, leading whitespace, and ":" or "-" separators.
# DOTALL on the body lets a section span multiple lines until the next
# S:/B:/A:/R: header (or end-of-string).
_LABELED_RE = re.compile(
    r"^\s*([SBAR])\s*[:\-]\s*(.+?)(?=\n\s*[SBAR]\s*[:\-]|\Z)",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)

# Strip a single leading "S:", "B:", "A:" or "R:" from a field value —
# some providers (Claude, Groq) prepend the section letter to each field's
# value even when returning JSON, which would otherwise show up as
# "S: S: Patient is tachycardic" in the SBAR card.
_LEADING_LABEL_RE = re.compile(r"^\s*[SBAR]\s*[:\-]\s*", re.IGNORECASE)


def _strip_label(value: str) -> str:
    """Remove a leading section-letter prefix (S:/B:/A:/R:) from a field."""
    if not value:
        return value
    return _LEADING_LABEL_RE.sub("", value, count=1).strip()


def _parse_labeled_sbar(text: str) -> dict[str, str] | None:
    """Parse `S: foo\\nB: bar\\nA: baz\\nR: qux` into the four SBAR fields.

    Returns None if no S/B/A/R-style headers are found, signalling the
    caller to try the next fallback. Missing fields default to empty
    strings (not "—"), so the SBAR card can render placeholders itself.
    """
    out: dict[str, str] = {
        "situation": "",
        "background": "",
        "assessment": "",
        "recommendation": "",
    }
    key_for: dict[str, str] = {
        "S": "situation",
        "B": "background",
        "A": "assessment",
        "R": "recommendation",
    }
    found = False
    for m in _LABELED_RE.finditer(text):
        letter = m.group(1).upper()
        body = m.group(2).strip()
        out[key_for[letter]] = body
        found = True
    return out if found else None


def _sbar_from_dict(data: dict[str, Any]) -> SBAR:
    """Build an SBAR, stripping any stale leading S:/B:/A:/R: per field."""
    return SBAR(
        situation=_strip_label(str(data.get("situation", ""))),
        background=_strip_label(str(data.get("background", ""))),
        assessment=_strip_label(str(data.get("assessment", ""))),
        recommendation=_strip_label(str(data.get("recommendation", ""))),
    )


def _parse_sbar(llm_output: str) -> SBAR:
    """Parse an SBAR from LLM output.

    Three-layer strategy, in order:

    1. JSON parse (preferred — the prompt asks for JSON). If it parses
       and yields at least one SBAR field, use it.
    2. Labeled-text parse (S:/B:/A:/R: prefixes). Salvages providers
       that ignored the JSON instruction but still produced a sensible
       narrative.
    3. Last-ditch destructive fallback: dump the whole output into
       `situation` with boilerplate for the rest. Only reached when the
       output is unparseable in either format.

    Any leading "S:"/"B:"/"A:"/"R:" prefix is stripped from each field
    after parsing — some providers prepend the section letter to the
    body even when returning JSON.
    """
    text = llm_output.strip()

    # Find JSON block (may be wrapped in markdown code fences)
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            cleaned = part.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith("{"):
                text = cleaned
                break

    sbar_keys = ("situation", "background", "assessment", "recommendation")

    # 1. JSON parse
    try:
        data = json.loads(text)
        if isinstance(data, dict) and any(k in data for k in sbar_keys):
            return _sbar_from_dict(data)
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. Labeled-text parse (S:/B:/A:/R:)
    labeled = _parse_labeled_sbar(llm_output)
    if labeled is not None:
        return _sbar_from_dict(labeled)

    # 3. Last-ditch destructive fallback
    return SBAR(
        situation=llm_output[:500],
        background="See automated screening results.",
        assessment="Clinical review required.",
        recommendation="Evaluate patient and confirm findings.",
    )


def _build_communication_draft(
    patient_id: str,
    encounter_id: str | None,
    narrative: str,
    severity: str,
    recipient_role: str,
) -> dict[str, Any]:
    """Build an unpersisted FHIR Communication resource draft."""
    priority = "urgent" if severity in ("urgent", "critical") else "routine"

    # Map recipient_role to display text
    role_display = {
        "charge_nurse": "Charge Nurse",
        "resident": "Resident Physician",
        "attending": "Attending Physician",
        "rapid_response": "Rapid Response Team",
    }

    draft: dict[str, Any] = {
        "resourceType": "Communication",
        "status": "in-progress",
        "category": [
            {
                "coding": [
                    {
                        "system": (
                            "http://terminology.hl7.org/CodeSystem"
                            "/communication-category"
                        ),
                        "code": "alert",
                    }
                ]
            }
        ],
        "priority": priority,
        "subject": {"reference": f"Patient/{patient_id}"},
        "sender": {
            "reference": "Device/vigil-postop-sentinel",
            "display": "Vigil Postop Sentinel",
        },
        "recipient": [
            {
                # FHIR logical IDs allow only letters/digits/-/. so convert
                # our Python-snake-case enum (e.g. charge_nurse) to kebab-case
                # (charge-nurse) for the resource id. HAPI rejects underscores.
                "reference": f"PractitionerRole/{recipient_role.replace('_', '-')}",
                "display": role_display.get(recipient_role, recipient_role),
            }
        ],
        "payload": [{"contentString": narrative}],
    }

    if encounter_id:
        draft["encounter"] = {"reference": f"Encounter/{encounter_id}"}

    return draft


async def run(
    patient_id: str,
    vitals_result: dict[str, Any],
    risk_result: dict[str, Any],
    sepsis_result: dict[str, Any],
    recipient_role: str,
    sharp: FhirContext,
) -> str:
    """Execute generate_escalation_note and return JSON string."""
    async with tool_call_timer("generate_escalation_note", patient_id) as ctx:
        # Fetch patient + encounter context
        patient_name = f"Patient {patient_id}"
        encounter_id: str | None = None

        # Inherit synthetic-data marking from upstream screening results
        # — if the screens already used the fallback, this tool's output
        # must say so too even when the encounter fetch happens to
        # succeed (e.g., the test harness only mocks part of the path).
        upstream_synthetic = (
            vitals_result.get("data_source") == SYNTHETIC_DATA_SOURCE
            or risk_result.get("data_source") == SYNTHETIC_DATA_SOURCE
            or sepsis_result.get("data_source") == SYNTHETIC_DATA_SOURCE
        )
        data_source = (
            SYNTHETIC_DATA_SOURCE if upstream_synthetic else LIVE_DATA_SOURCE
        )

        try:
            async with FhirClient(sharp) as fhir:
                patient = await fhir.get_patient(patient_id)
                if patient.name:
                    name = patient.name[0]
                    given = " ".join(name.given) if name.given else ""
                    family = name.family or ""
                    patient_name = f"{given} {family}".strip() or patient_name

                encounter = await fhir.get_encounter(patient_id)
                if encounter:
                    encounter_id = encounter.id
        except FhirClientError as exc:
            # Auth-shaped failure → opt-in fallback to PT-007's
            # demographics so the SBAR prompt has a real name to use
            # instead of "Patient PT-007". Other FHIR errors fall
            # through to the existing default-name path.
            if is_fhir_auth_error(exc) and is_fallback_enabled():
                logger.warning(
                    "FHIR auth denied; using synthetic PT-007 demographics",
                    extra={"patient_id": patient_id, "error": str(exc)},
                )
                data_source = SYNTHETIC_DATA_SOURCE
                synthetic_patient = get_synthetic_patient()
                if synthetic_patient.name:
                    name = synthetic_patient.name[0]
                    given = " ".join(name.given) if name.given else ""
                    family = name.family or ""
                    patient_name = (
                        f"{given} {family}".strip() or patient_name
                    )
                synthetic_encounter = get_synthetic_encounter()
                if synthetic_encounter:
                    encounter_id = synthetic_encounter.id
            else:
                logger.warning(
                    "FHIR context fetch failed, proceeding with defaults",
                    extra={"patient_id": patient_id, "error": str(exc)},
                )

        severity = _determine_severity(
            vitals_result, risk_result, sepsis_result,
        )

        # Build LLM prompt
        prompt = _build_prompt(
            patient_id=patient_id,
            patient_name=patient_name,
            encounter_id=encounter_id,
            vitals_result=vitals_result,
            risk_result=risk_result,
            sepsis_result=sepsis_result,
            recipient_role=recipient_role,
            severity=severity,
        )

        # Call LLM — check cache first (I4)
        provider = get_provider()
        model_used = provider.name
        try:
            fhir_url = sharp.url if sharp else ""
            llm_output = await get_llm_cached(prompt, model_used, fhir_url, patient_id)
            cache_hit = llm_output is not None
            if llm_output is None:
                llm_output = await provider.complete(prompt, max_tokens=1024)
                await set_llm_cached(prompt, model_used, fhir_url, patient_id, llm_output)
            # Approximate token counts for observability
            prompt_tokens = 0 if cache_hit else len(prompt) // 4
            completion_tokens = len(llm_output) // 4
            await record_llm_call(
                provider=model_used.split("/")[0],
                model=model_used,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                patient_id=patient_id,
            )
        except LLMError as exc:
            logger.error(
                "LLM call failed for generate_escalation_note",
                extra={"patient_id": patient_id, "error": str(exc)},
            )
            ctx["status"] = ToolStatus.LLM_UNAVAILABLE
            # Return a template-based fallback
            sbar = SBAR(
                situation=(
                    f"Automated screening detected abnormalities for "
                    f"{patient_name} ({patient_id})."
                ),
                background="See attached screening results.",
                assessment=(
                    f"Risk band: {risk_result.get('risk_band', 'unknown')}. "
                    f"Sepsis suspected: {sepsis_result.get('sepsis_suspected', False)}."
                ),
                recommendation=(
                    "Review patient status. LLM narrative unavailable "
                    f"({exc}). Clinical evaluation recommended."
                ),
            )
            narrative = (
                f"S: {sbar.situation} "
                f"B: {sbar.background} "
                f"A: {sbar.assessment} "
                f"R: {sbar.recommendation}"
            )
            output = EscalationOutput(
                status=ToolStatus.LLM_UNAVAILABLE,
                patient_id=patient_id,
                sbar=sbar,
                narrative=narrative,
                severity=severity,
                recipient_role=recipient_role,
                communication_draft=_build_communication_draft(
                    patient_id, encounter_id, narrative,
                    severity, recipient_role,
                ),
                generated_at=datetime.now(UTC),
                model_used=model_used,
                data_source=data_source,
            )
            return output.model_dump_json()

        # Parse SBAR from LLM output
        sbar = _parse_sbar(llm_output)
        narrative = (
            f"S: {sbar.situation} "
            f"B: {sbar.background} "
            f"A: {sbar.assessment} "
            f"R: {sbar.recommendation}"
        )

        ctx["status"] = ToolStatus.OK

        logger.info(
            "generate_escalation_note complete",
            extra={
                "patient_id": patient_id,
                "severity": severity,
                "model_used": model_used,
            },
        )

        output = EscalationOutput(
            status=ToolStatus.OK,
            patient_id=patient_id,
            sbar=sbar,
            narrative=narrative,
            severity=severity,
            recipient_role=recipient_role,
            communication_draft=_build_communication_draft(
                patient_id, encounter_id, narrative,
                severity, recipient_role,
            ),
            generated_at=datetime.now(UTC),
            model_used=model_used,
            data_source=data_source,
        )
        return output.model_dump_json()
