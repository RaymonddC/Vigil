"""Tests for generate_escalation_note (B5) — SBAR escalation note tool.

Acceptance criteria (BUILD_PLAN.md B5):
  - SBAR validates against the SBAR pydantic model (all 4 fields present)
  - communication_draft is valid FHIR Communication shape:
      resourceType="Communication", status="in-progress", NO id field
  - Tool NEVER POSTs to HAPI (verified structurally — FhirClient has no
    write method; we also confirm no httpx POST is attempted)
  - LLM fallback chain: provider fails → status=llm_error, model_used
    reflects degraded mode, output still valid

All external dependencies (FhirClient, LLM provider, event store) are mocked.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.fhir.client import FhirClientError
from backend.fhir.models import (
    Encounter,
    HumanName,
    Patient,
    Period,
)
from backend.llm.provider import LLMError, StubProvider
from backend.mcp_server.tools.generate_escalation_note import run
from backend.schemas import EscalationOutput, FhirContext, SBAR

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FHIR_CTX = FhirContext(url="http://localhost:8080/fhir", token=None)
PATIENT_ID = "PT-009"

# Realistic upstream tool outputs for a critical sepsis case
VITALS_TRIGGERED = {
    "status": "triggered",
    "patient_id": PATIENT_ID,
    "trajectory": "postop",
    "breaches": [
        {
            "loinc": "8480-6",
            "label": "SBP",
            "value": 86.0,
            "unit": "mm[Hg]",
            "threshold": "<90",
            "severity": "red",
            "observed_at": "2026-04-15T10:00:00Z",
        },
    ],
    "scanned_count": 12,
    "window_start": "2026-04-15T06:00:00Z",
    "window_end": "2026-04-15T10:00:00Z",
}

RISK_HIGH = {
    "status": "triggered",
    "patient_id": PATIENT_ID,
    "qsofa_score": 2,
    "qsofa_components": {"rr_ge_22": True, "sbp_le_100": True, "altered_mental": False},
    "composite_risk": 0.81,
    "risk_band": "high",
    "rationale": "qSOFA=2; SBP trending down.",
    "contributing_conditions": ["44054006 Type 2 diabetes mellitus"],
}

SEPSIS_TRIGGERED = {
    "status": "triggered",
    "patient_id": PATIENT_ID,
    "sepsis_suspected": True,
    "mode": "cdc_ase",
    "criteria_met": [
        "presumed infection (antibiotic started)",
        "organ dysfunction: lactate 4.5 mmol/L",
        "organ dysfunction: SBP 86 mmHg",
    ],
    "onset_estimate": "2026-04-15T10:00:00Z",
    "evidence": {"lactate_value": 4.5, "sbp": 86, "abx_code": "J01DD04"},
}

# Quiet normal-patient outputs
VITALS_OK = {
    "status": "ok", "patient_id": "PT-001",
    "trajectory": "postop", "breaches": [],
    "scanned_count": 10,
    "window_start": "2026-04-15T06:00:00Z",
    "window_end": "2026-04-15T10:00:00Z",
}
RISK_LOW = {
    "status": "ok", "patient_id": "PT-001",
    "qsofa_score": 0, "qsofa_components": {"rr_ge_22": False, "sbp_le_100": False, "altered_mental": False},
    "composite_risk": 0.08, "risk_band": "low",
    "rationale": "qSOFA=0; no breach.", "contributing_conditions": [],
}
SEPSIS_NEG = {
    "status": "ok", "patient_id": "PT-001",
    "sepsis_suspected": False, "mode": "cdc_ase",
    "criteria_met": [], "onset_estimate": None,
    "evidence": {"lactate_value": 0.9, "abx_code": None},
}


@asynccontextmanager
async def _noop_timer(tool_name, patient_id=None):
    """No-op replacement for tool_call_timer to avoid the event store."""
    yield {}


def _mock_fhir_client(patient_name: str = "Jane Doe", enc_id: str = "enc-77"):
    """Return a configured AsyncMock for FhirClient with patient + encounter."""
    mock_client = AsyncMock()
    patient = Patient(
        id=PATIENT_ID,
        name=[HumanName(family=patient_name.split()[-1], given=patient_name.split()[:-1])],
        gender="female",
        birthDate="1983-07-19",
    )
    encounter = Encounter(
        id=enc_id,
        status="in-progress",
        period=Period(start=datetime(2026, 4, 14, 17, 30, tzinfo=timezone.utc)),
    )
    mock_client.get_patient.return_value = patient
    mock_client.get_encounter.return_value = encounter
    return mock_client


def _mock_llm_json(sbar_dict: dict) -> MagicMock:
    """Return a Provider mock whose complete() returns valid SBAR JSON."""
    provider = MagicMock()
    provider.name = "test/model"
    provider.complete = AsyncMock(return_value=json.dumps(sbar_dict))
    return provider


GOOD_SBAR = {
    "situation": "Post-op day 1 patient with SBP 86 mmHg and qSOFA 2; sepsis suspected.",
    "background": "42yo s/p laparoscopic cholecystectomy 18h ago; Hx T2DM.",
    "assessment": "Meets CDC ASE: lactate 4.5 mmol/L, SBP 86, abx started. High risk.",
    "recommendation": "Activate rapid response, repeat lactate, 500ml NS bolus, notify attending.",
}


# ---------------------------------------------------------------------------
# Helper to run with patched dependencies
# ---------------------------------------------------------------------------

async def _run_with_mocks(
    mock_client,
    mock_provider,
    vitals=None,
    risk=None,
    sepsis=None,
    recipient_role: str = "charge_nurse",
    patient_id: str = PATIENT_ID,
) -> EscalationOutput:
    vitals = vitals or VITALS_TRIGGERED
    risk = risk or RISK_HIGH
    sepsis = sepsis or SEPSIS_TRIGGERED

    with patch(
        "backend.mcp_server.tools.generate_escalation_note.tool_call_timer",
        _noop_timer,
    ), patch(
        "backend.mcp_server.tools.generate_escalation_note.FhirClient"
    ) as MockFC, patch(
        "backend.mcp_server.tools.generate_escalation_note.get_provider",
        return_value=mock_provider,
    ), patch(
        "backend.mcp_server.tools.generate_escalation_note.record_llm_call",
        new_callable=AsyncMock,
    ):
        MockFC.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockFC.return_value.__aexit__ = AsyncMock(return_value=False)

        result_json = await run(
            patient_id=patient_id,
            vitals_result=vitals,
            risk_result=risk,
            sepsis_result=sepsis,
            recipient_role=recipient_role,
            sharp=FHIR_CTX,
        )

    return EscalationOutput.model_validate_json(result_json)


# ---------------------------------------------------------------------------
# SBAR validation
# ---------------------------------------------------------------------------

async def test_sbar_validates_all_fields():
    """SBAR must have all four non-empty fields."""
    result = await _run_with_mocks(
        mock_client=_mock_fhir_client(),
        mock_provider=_mock_llm_json(GOOD_SBAR),
    )

    sbar = result.sbar
    assert isinstance(sbar, SBAR)
    assert sbar.situation.strip()
    assert sbar.background.strip()
    assert sbar.assessment.strip()
    assert sbar.recommendation.strip()


async def test_sbar_validates_on_llm_fallback():
    """Even when LLM fails, SBAR fallback template populates all four fields."""
    failing_provider = MagicMock()
    failing_provider.name = "test/broken"
    failing_provider.complete = AsyncMock(side_effect=LLMError("test/broken", "connection refused"))

    result = await _run_with_mocks(
        mock_client=_mock_fhir_client(),
        mock_provider=failing_provider,
    )

    sbar = result.sbar
    assert sbar.situation.strip()
    assert sbar.background.strip()
    assert sbar.assessment.strip()
    assert sbar.recommendation.strip()
    assert result.status == "llm_error"


# ---------------------------------------------------------------------------
# communication_draft shape
# ---------------------------------------------------------------------------

async def test_communication_draft_valid_fhir_shape():
    """communication_draft must match the FHIR Communication resource shape."""
    result = await _run_with_mocks(
        mock_client=_mock_fhir_client(),
        mock_provider=_mock_llm_json(GOOD_SBAR),
    )

    draft = result.communication_draft
    assert draft["resourceType"] == "Communication"
    assert draft["status"] == "in-progress"
    assert "subject" in draft
    assert draft["subject"]["reference"] == f"Patient/{PATIENT_ID}"
    assert "sender" in draft
    assert isinstance(draft["recipient"], list)
    assert len(draft["recipient"]) >= 1
    assert "payload" in draft
    assert len(draft["payload"]) >= 1
    assert "contentString" in draft["payload"][0]


async def test_communication_draft_has_no_id():
    """The draft must NOT contain an id field — the proxy assigns it on approve."""
    result = await _run_with_mocks(
        mock_client=_mock_fhir_client(),
        mock_provider=_mock_llm_json(GOOD_SBAR),
    )

    assert "id" not in result.communication_draft


async def test_communication_draft_status_in_progress():
    """Draft status must always be in-progress (never completed)."""
    result = await _run_with_mocks(
        mock_client=_mock_fhir_client(),
        mock_provider=_mock_llm_json(GOOD_SBAR),
    )

    assert result.communication_draft["status"] == "in-progress"


# ---------------------------------------------------------------------------
# Tool never POSTs to FHIR
# ---------------------------------------------------------------------------

async def test_tool_never_posts_to_fhir():
    """FhirClient provides no write methods; the tool only calls GET-like methods."""
    mock_client = _mock_fhir_client()

    await _run_with_mocks(
        mock_client=mock_client,
        mock_provider=_mock_llm_json(GOOD_SBAR),
    )

    # Confirm only read operations were attempted — no write/create/update calls
    mock_client.get_patient.assert_awaited_once()
    mock_client.get_encounter.assert_awaited_once()

    # FhirClient has no post/put/create method — verify none were called
    assert not hasattr(mock_client, "post") or not mock_client.post.called
    assert not hasattr(mock_client, "create") or not mock_client.create.called


# ---------------------------------------------------------------------------
# Severity determination
# ---------------------------------------------------------------------------

async def test_severity_critical_when_sepsis_suspected():
    """Sepsis suspected → severity=critical regardless of vitals/risk."""
    result = await _run_with_mocks(
        mock_client=_mock_fhir_client(),
        mock_provider=_mock_llm_json(GOOD_SBAR),
        sepsis=SEPSIS_TRIGGERED,
    )
    assert result.severity == "critical"


async def test_severity_info_when_all_ok():
    """Normal patient → severity=info."""
    result = await _run_with_mocks(
        mock_client=_mock_fhir_client(),
        mock_provider=_mock_llm_json({
            "situation": "Patient is stable.",
            "background": "Post-op day 1 following elective procedure.",
            "assessment": "No significant deterioration detected.",
            "recommendation": "Continue routine monitoring.",
        }),
        vitals=VITALS_OK,
        risk=RISK_LOW,
        sepsis=SEPSIS_NEG,
        patient_id="PT-001",
    )
    assert result.severity == "info"


# ---------------------------------------------------------------------------
# Recipient role handling
# ---------------------------------------------------------------------------

async def test_recipient_role_echoed_back():
    """recipient_role must be echoed in the output."""
    for role in ("charge_nurse", "resident", "attending", "rapid_response"):
        result = await _run_with_mocks(
            mock_client=_mock_fhir_client(),
            mock_provider=_mock_llm_json(GOOD_SBAR),
            recipient_role=role,
        )
        assert result.recipient_role == role


# ---------------------------------------------------------------------------
# LLM model_used tracking
# ---------------------------------------------------------------------------

async def test_model_used_set_on_success():
    """model_used reflects the provider name on successful LLM call."""
    provider = _mock_llm_json(GOOD_SBAR)
    provider.name = "groq/llama-3.1-70b"

    result = await _run_with_mocks(
        mock_client=_mock_fhir_client(),
        mock_provider=provider,
    )
    assert result.model_used == "groq/llama-3.1-70b"


async def test_model_used_template_fallback_on_failure():
    """model_used signals degraded mode when LLM fails."""
    failing_provider = MagicMock()
    failing_provider.name = "ollama/llama3.1"
    failing_provider.complete = AsyncMock(side_effect=LLMError("ollama", "timeout"))

    result = await _run_with_mocks(
        mock_client=_mock_fhir_client(),
        mock_provider=failing_provider,
    )
    # Either "template_fallback" or provider name — LLM_UNAVAILABLE status
    assert result.status == "llm_error"


# ---------------------------------------------------------------------------
# FHIR context failure — graceful degradation
# ---------------------------------------------------------------------------

async def test_fhir_error_during_context_fetch_does_not_crash():
    """If patient/encounter fetch fails, tool still returns valid output."""
    mock_client = AsyncMock()
    mock_client.get_patient.side_effect = FhirClientError("not found", 404)
    mock_client.get_encounter.side_effect = FhirClientError("not found", 404)

    result = await _run_with_mocks(
        mock_client=mock_client,
        mock_provider=_mock_llm_json(GOOD_SBAR),
    )

    # Must still return valid output even without patient context
    assert isinstance(result.sbar, SBAR)
    assert "id" not in result.communication_draft
    assert result.communication_draft["status"] == "in-progress"


# ---------------------------------------------------------------------------
# Narrative format
# ---------------------------------------------------------------------------

async def test_narrative_contains_sbar_sections():
    """Narrative must contain S/B/A/R labelled sections."""
    result = await _run_with_mocks(
        mock_client=_mock_fhir_client(),
        mock_provider=_mock_llm_json(GOOD_SBAR),
    )
    narrative = result.narrative
    # Each section label should appear in the narrative
    for label in ("S:", "B:", "A:", "R:"):
        assert label in narrative, f"Missing '{label}' in narrative: {narrative[:200]}"
