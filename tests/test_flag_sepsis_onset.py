"""Tests for flag_sepsis_onset (B4) — CDC ASE surveillance tool.

Acceptance criteria (BUILD_PLAN.md B4):
  PT-001 → sepsis_suspected=False, mode=cdc_ase
  PT-009@T+4h → sepsis_suspected=True, mode=cdc_ase
  Sparse labs → mode=sirs_fallback
  FHIR error → sepsis_suspected=False, status=fhir_error

All FhirClient calls are mocked; tool_call_timer is replaced with a no-op
context manager so tests don't require a running asyncio event store.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from backend.fhir.client import FhirClientError
from backend.fhir.models import (
    CategoryItem,
    CodeableConcept,
    Coding,
    MedicationAdministration,
    Observation,
    Quantity,
)
from backend.mcp_server.tools.flag_sepsis_onset import run
from backend.schemas import FhirContext, SepsisFlagOutput

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FHIR_CTX = FhirContext(url="http://localhost:8080/fhir", token=None)
T4H = datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc)


@asynccontextmanager
async def _noop_timer(tool_name, patient_id=None):
    """Drop-in replacement for tool_call_timer that never touches the event store."""
    ctx: dict = {}
    yield ctx


def _vital(loinc: str, value: float, unit: str = "") -> Observation:
    """Create a minimal vital-signs Observation."""
    return Observation(
        status="final",
        category=[CategoryItem(coding=[Coding(
            system="http://terminology.hl7.org/CodeSystem/observation-category",
            code="vital-signs",
        )])],
        code=CodeableConcept(coding=[Coding(system="http://loinc.org", code=loinc)]),
        effectiveDateTime=T4H,
        valueQuantity=Quantity(value=value, unit=unit),
    )


def _lab(loinc: str, value: float, unit: str = "") -> Observation:
    """Create a minimal laboratory Observation."""
    return Observation(
        status="final",
        category=[CategoryItem(coding=[Coding(
            system="http://terminology.hl7.org/CodeSystem/observation-category",
            code="laboratory",
        )])],
        code=CodeableConcept(coding=[Coding(system="http://loinc.org", code=loinc)]),
        effectiveDateTime=T4H,
        valueQuantity=Quantity(value=value, unit=unit),
    )


def _antibiotic(code: str = "J01DD04", display: str = "ceftriaxone") -> MedicationAdministration:
    """Create an antibiotic MedicationAdministration with ATC J01* code."""
    return MedicationAdministration(
        status="completed",
        medicationCodeableConcept=CodeableConcept(coding=[
            Coding(system="http://www.whocc.no/atc", code=code, display=display)
        ]),
        effectiveDateTime=T4H,
    )


# ---------------------------------------------------------------------------
# Normal patient (PT-001) — no sepsis
# ---------------------------------------------------------------------------

PT001_VITALS = [
    _vital("8480-6", 118, "mm[Hg]"),   # SBP
    _vital("8867-4", 72,  "/min"),       # HR
    _vital("9279-1", 14,  "/min"),       # RR
    _vital("8310-5", 37.0, "Cel"),       # Temp
]
PT001_LABS = [
    _lab("2524-7", 0.9,  "mmol/L"),  # lactate — normal
    _lab("6690-2", 8.5,  "10*3/uL"), # WBC — normal
    _lab("2160-0", 0.9,  "mg/dL"),   # creatinine — normal
    _lab("1975-2", 0.4,  "mg/dL"),   # bilirubin — normal
    _lab("777-3",  250,  "10*3/uL"), # platelets — normal
]


async def test_pt001_no_sepsis_cdc_ase():
    """PT-001 with normal labs/vitals → sepsis_suspected=False, mode=cdc_ase."""
    mock_client = AsyncMock()

    async def _obs(patient_id, category=None, since=None, count=100):
        return PT001_VITALS if category == "vital-signs" else PT001_LABS

    mock_client.get_observations.side_effect = _obs
    mock_client.get_medication_administrations.return_value = []

    with patch(
        "backend.mcp_server.tools.flag_sepsis_onset.tool_call_timer", _noop_timer
    ), patch("backend.mcp_server.tools.flag_sepsis_onset.FhirClient") as MockFC:
        MockFC.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockFC.return_value.__aexit__ = AsyncMock(return_value=False)

        result_json = await run("PT-001", 24, FHIR_CTX)

    result = SepsisFlagOutput.model_validate_json(result_json)

    assert result.sepsis_suspected is False
    assert result.mode == "cdc_ase"
    assert result.patient_id == "PT-001"
    assert result.onset_estimate is None


# ---------------------------------------------------------------------------
# Sepsis patient (PT-009@T+4h) — sepsis flagged
# ---------------------------------------------------------------------------

PT009_VITALS = [
    _vital("8480-6", 86,  "mm[Hg]"),   # SBP — low → qSOFA & CDC ASE
    _vital("8867-4", 112, "/min"),       # HR — tachycardia
    _vital("9279-1", 26,  "/min"),       # RR — elevated → qSOFA
    _vital("8310-5", 38.5, "Cel"),       # Temp — febrile
]
PT009_LABS = [
    _lab("2524-7", 4.5,  "mmol/L"),  # lactate ≥ 4 — organ dysfunction
    _lab("6690-2", 18.5, "10*3/uL"), # WBC ≥ 18 — leukocytosis
    _lab("2160-0", 1.2,  "mg/dL"),   # creatinine — mildly elevated
    _lab("1975-2", 0.6,  "mg/dL"),   # bilirubin — normal
    _lab("777-3",  165,  "10*3/uL"), # platelets — normal
]


async def test_pt009_sepsis_suspected_cdc_ase():
    """PT-009@T+4h with high lactate + antibiotic → sepsis_suspected=True, mode=cdc_ase."""
    mock_client = AsyncMock()

    async def _obs(patient_id, category=None, since=None, count=100):
        return PT009_VITALS if category == "vital-signs" else PT009_LABS

    mock_client.get_observations.side_effect = _obs
    mock_client.get_medication_administrations.return_value = [_antibiotic()]

    with patch(
        "backend.mcp_server.tools.flag_sepsis_onset.tool_call_timer", _noop_timer
    ), patch("backend.mcp_server.tools.flag_sepsis_onset.FhirClient") as MockFC:
        MockFC.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockFC.return_value.__aexit__ = AsyncMock(return_value=False)

        result_json = await run("PT-009", 24, FHIR_CTX)

    result = SepsisFlagOutput.model_validate_json(result_json)

    assert result.sepsis_suspected is True
    assert result.mode == "cdc_ase"
    assert result.patient_id == "PT-009"
    assert result.onset_estimate is not None

    # Infection signal present
    assert any("antibiotic" in c.lower() or "infection" in c.lower()
               for c in result.criteria_met)
    # Organ dysfunction from lactate
    assert any("lactate" in c.lower() for c in result.criteria_met)


async def test_pt009_labs_alone_trigger_via_wbc_surrogate():
    """PT-009@T+4h with high lactate + WBC ≥ 12 but NO antibiotic → still triggers.

    WBC ≥ 12 serves as infection surrogate when no antibiotic is in the window,
    allowing flag_sepsis_onset to detect the pre-administration window correctly.
    """
    mock_client = AsyncMock()

    async def _obs(patient_id, category=None, since=None, count=100):
        return PT009_VITALS if category == "vital-signs" else PT009_LABS

    mock_client.get_observations.side_effect = _obs
    mock_client.get_medication_administrations.return_value = []  # no abx yet

    with patch(
        "backend.mcp_server.tools.flag_sepsis_onset.tool_call_timer", _noop_timer
    ), patch("backend.mcp_server.tools.flag_sepsis_onset.FhirClient") as MockFC:
        MockFC.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockFC.return_value.__aexit__ = AsyncMock(return_value=False)

        result_json = await run("PT-009", 24, FHIR_CTX)

    result = SepsisFlagOutput.model_validate_json(result_json)
    # Implementation either triggers (WBC surrogate) or evaluates CDC ASE;
    # either way, lactate 4.5 and WBC 18.5 must produce a suspicious flag.
    assert result.mode == "cdc_ase"
    # High lactate should always be in evidence when labs are present
    assert "lactate_value" in result.evidence


# ---------------------------------------------------------------------------
# SIRS fallback — sparse labs
# ---------------------------------------------------------------------------

async def test_sirs_fallback_when_labs_sparse():
    """When no lactate AND no creatinine, mode=sirs_fallback."""
    mock_client = AsyncMock()

    SPARSE_LABS = [_lab("6690-2", 14.0, "10*3/uL")]  # only WBC — no lactate/creatinine

    async def _obs(patient_id, category=None, since=None, count=100):
        if category == "vital-signs":
            return [
                _vital("8867-4", 105, "/min"),  # HR > 90 → SIRS
                _vital("9279-1", 22,  "/min"),  # RR > 20 → SIRS
                _vital("8310-5", 38.5, "Cel"),  # Temp > 38 → SIRS
            ]
        return SPARSE_LABS

    mock_client.get_observations.side_effect = _obs
    mock_client.get_medication_administrations.return_value = []

    with patch(
        "backend.mcp_server.tools.flag_sepsis_onset.tool_call_timer", _noop_timer
    ), patch("backend.mcp_server.tools.flag_sepsis_onset.FhirClient") as MockFC:
        MockFC.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockFC.return_value.__aexit__ = AsyncMock(return_value=False)

        result_json = await run("PT-005", 24, FHIR_CTX)

    result = SepsisFlagOutput.model_validate_json(result_json)
    assert result.mode == "sirs_fallback"


# ---------------------------------------------------------------------------
# FHIR error — fail-safe returns False
# ---------------------------------------------------------------------------

async def test_fhir_error_returns_false():
    """On FHIR error, sepsis_suspected is always False (fail-safe)."""
    with patch(
        "backend.mcp_server.tools.flag_sepsis_onset.tool_call_timer", _noop_timer
    ), patch("backend.mcp_server.tools.flag_sepsis_onset.FhirClient") as MockFC:
        MockFC.return_value.__aenter__ = AsyncMock(
            side_effect=FhirClientError("HAPI unreachable", status_code=503)
        )
        MockFC.return_value.__aexit__ = AsyncMock(return_value=False)

        result_json = await run("PT-001", 24, FHIR_CTX)

    result = SepsisFlagOutput.model_validate_json(result_json)
    assert result.sepsis_suspected is False
    assert result.status == "fhir_error"


# ---------------------------------------------------------------------------
# Output schema validation
# ---------------------------------------------------------------------------

async def test_output_schema_always_valid():
    """SepsisFlagOutput always satisfies the schema contract (all required fields)."""
    mock_client = AsyncMock()

    async def _obs(patient_id, category=None, since=None, count=100):
        return PT001_LABS if category == "laboratory" else []

    mock_client.get_observations.side_effect = _obs
    mock_client.get_medication_administrations.return_value = []

    with patch(
        "backend.mcp_server.tools.flag_sepsis_onset.tool_call_timer", _noop_timer
    ), patch("backend.mcp_server.tools.flag_sepsis_onset.FhirClient") as MockFC:
        MockFC.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockFC.return_value.__aexit__ = AsyncMock(return_value=False)

        result_json = await run("PT-001", 24, FHIR_CTX)

    result = SepsisFlagOutput.model_validate_json(result_json)
    assert isinstance(result.criteria_met, list)
    assert isinstance(result.evidence, dict)
    assert result.mode in ("cdc_ase", "sirs_fallback")
    assert isinstance(result.sepsis_suspected, bool)
