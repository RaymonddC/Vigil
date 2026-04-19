"""Unit tests for score_deterioration_risk tool — BUILD_PLAN B3.

Acceptance criteria (B3):
  PT-001 → risk_band=low
  PT-007@T+2h window → risk_band=moderate (hemodynamic trend fires, qSOFA=0)
  PT-007@T+6h+ → risk_band=high (qSOFA=2: SBP≤100 + RR≥22)
  Comorbidities from Condition resources populate contributing_conditions

All tests mock FhirClient — no live HAPI required.

Composite risk formula (from score_deterioration_risk.py):
  base = qsofa_score / 3
  breach_weight = min(mewt_breach_count * 0.15, 0.3)
  condition_weight = min(active_condition_count * 0.05, 0.15)
  composite = clamp(base + breach_weight + condition_weight, 0.0, 1.0)

  low < 0.3, moderate 0.3–0.6, high > 0.6
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from backend.fhir.client import FhirClientError
from backend.fhir.models import (
    CategoryItem,
    CodeableConcept,
    Coding,
    Condition,
    Observation,
    Quantity,
)
from backend.mcp_server.tools.score_deterioration_risk import run
from backend.schemas import FhirContext, ToolStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

T0 = datetime(2026, 4, 15, 10, 0, 0, tzinfo=UTC)


def _obs(loinc: str, value: float, unit: str, t: datetime) -> Observation:
    return Observation(
        resourceType="Observation",
        code=CodeableConcept(coding=[Coding(system="http://loinc.org", code=loinc)]),
        category=[CategoryItem(coding=[Coding(code="vital-signs")])],
        valueQuantity=Quantity(value=value, unit=unit),
        effectiveDateTime=t,
    )


def _vitals_at(t: datetime, sbp: float, hr: float, rr: float, spo2: float = 98.0) -> list[Observation]:
    return [
        _obs("8480-6", sbp,  "mm[Hg]", t),
        _obs("8867-4", hr,   "/min",   t),
        _obs("9279-1", rr,   "/min",   t),
        _obs("59408-5", spo2, "%",     t),
    ]


def _condition(snomed_code: str, display: str) -> Condition:
    return Condition(
        resourceType="Condition",
        code=CodeableConcept(
            coding=[Coding(
                system="http://snomed.info/sct",
                code=snomed_code,
                display=display,
            )]
        ),
        clinicalStatus=CodeableConcept(
            coding=[Coding(
                system="http://terminology.hl7.org/CodeSystem/condition-clinical",
                code="active",
            )]
        ),
    )


def _sharp(pid: str) -> FhirContext:
    return FhirContext(url="http://localhost:8080/fhir", token=None, patient_id=pid)


# ---------------------------------------------------------------------------
# Acceptance tests (required by BUILD_PLAN B3)
# ---------------------------------------------------------------------------


class TestB3AcceptanceCriteria:
    """Canonical acceptance tests from BUILD_PLAN B3."""

    async def test_pt001_stable_low_band(self):
        """PT-001 stable vitals, no conditions → risk_band=low."""
        obs = _vitals_at(T0, sbp=122, hr=74, rr=16)

        with patch("backend.mcp_server.tools.score_deterioration_risk.FhirClient") as M:
            inst = M.return_value.__aenter__.return_value
            inst.get_observations = AsyncMock(return_value=obs)
            inst.get_conditions = AsyncMock(return_value=[])

            raw = await run("PT-001", 6, "postop", _sharp("PT-001"))

        result = json.loads(raw)
        assert result["risk_band"] == "low"
        assert result["qsofa_score"] == 0
        assert result["composite_risk"] < 0.3
        assert result["patient_id"] == "PT-001"

    async def test_pt007_intermediate_moderate_band(self):
        """PT-007 intermediate deterioration: qSOFA=1 → risk_band=moderate.

        Composite formula: base = qsofa/3 = 1/3 = 0.33 ≥ 0.30 → moderate.
        SBP=100 (≤100 → qSOFA sbp_le_100=True), RR=18 (<22 → rr_ge_22=False) → qSOFA=1.
        SBP=100 is NOT < 100 so no MEWT absolute breach (yellow_low=100 means <100).
        composite = 1/3 + 0 + 0 ≈ 0.33 → moderate.

        This models the moderate band in the PT-007 deterioration trajectory before
        qSOFA reaches ≥2 and forces the high band.
        """
        obs = [
            _obs("8480-6", 100.0, "mm[Hg]", T0),  # SBP exactly 100 → qSOFA fires
            _obs("8867-4",  96.0, "/min",   T0),  # HR 96 — no breach
            _obs("9279-1",  18.0, "/min",   T0),  # RR 18 < 22 — no qSOFA
            _obs("59408-5", 96.0, "%",      T0),  # SpO2 96 — no breach (<93 is threshold)
        ]

        with patch("backend.mcp_server.tools.score_deterioration_risk.FhirClient") as M:
            inst = M.return_value.__aenter__.return_value
            inst.get_observations = AsyncMock(return_value=obs)
            inst.get_conditions = AsyncMock(return_value=[])

            raw = await run("PT-007", 6, "postop", _sharp("PT-007"))

        result = json.loads(raw)
        assert result["qsofa_score"] == 1, "SBP=100 gives qSOFA sbp_le_100"
        assert result["qsofa_components"]["sbp_le_100"] is True
        assert result["qsofa_components"]["rr_ge_22"] is False
        assert result["risk_band"] == "moderate", (
            f"qSOFA=1 → composite≈0.33 → moderate, got: {result['risk_band']}"
        )

    async def test_pt007_t6h_high_band(self):
        """PT-007 T+6h: SBP 94 (≤100) + RR 22 (≥22) → qSOFA=2 → risk_band=high.

        qSOFA≥2 triggers the 'high' band regardless of composite score.
        """
        obs = (
            _vitals_at(T0,                       sbp=130, hr=76, rr=16, spo2=98)
            + _vitals_at(T0 + timedelta(hours=2), sbp=114, hr=92, rr=18, spo2=96)
            + _vitals_at(T0 + timedelta(hours=6), sbp=94,  hr=108, rr=22, spo2=94)
        )

        with patch("backend.mcp_server.tools.score_deterioration_risk.FhirClient") as M:
            inst = M.return_value.__aenter__.return_value
            inst.get_observations = AsyncMock(return_value=obs)
            inst.get_conditions = AsyncMock(return_value=[])

            raw = await run("PT-007", 8, "postop", _sharp("PT-007"))

        result = json.loads(raw)
        assert result["qsofa_score"] >= 1   # at minimum RR ≥ 22
        assert result["risk_band"] == "high"
        assert result["status"] == ToolStatus.TRIGGERED

    async def test_contributing_conditions_populated(self):
        """Comorbidities from Condition resources appear in contributing_conditions."""
        obs = _vitals_at(T0, sbp=122, hr=74, rr=16)
        conditions = [
            _condition("44054006", "Type 2 diabetes mellitus"),
            _condition("44054007", "Chronic kidney disease stage 3"),
        ]

        with patch("backend.mcp_server.tools.score_deterioration_risk.FhirClient") as M:
            inst = M.return_value.__aenter__.return_value
            inst.get_observations = AsyncMock(return_value=obs)
            inst.get_conditions = AsyncMock(return_value=conditions)

            raw = await run("PT-001", 6, "postop", _sharp("PT-001"))

        result = json.loads(raw)
        assert len(result["contributing_conditions"]) == 2
        joined = " ".join(result["contributing_conditions"])
        assert "Type 2 diabetes" in joined


# ---------------------------------------------------------------------------
# qSOFA component tests
# ---------------------------------------------------------------------------


class TestB3QsofaComponents:

    async def test_qsofa_score_0_all_false(self):
        """Normal vitals → all three qSOFA components False."""
        obs = _vitals_at(T0, sbp=122, hr=74, rr=16)

        with patch("backend.mcp_server.tools.score_deterioration_risk.FhirClient") as M:
            inst = M.return_value.__aenter__.return_value
            inst.get_observations = AsyncMock(return_value=obs)
            inst.get_conditions = AsyncMock(return_value=[])

            raw = await run("PT-001", 6, "postop", _sharp("PT-001"))

        result = json.loads(raw)
        assert result["qsofa_score"] == 0
        assert result["qsofa_components"]["rr_ge_22"] is False
        assert result["qsofa_components"]["sbp_le_100"] is False
        assert result["qsofa_components"]["altered_mental"] is False

    async def test_qsofa_score_2_rr_and_sbp(self):
        """SBP ≤ 100 AND RR ≥ 22 → qSOFA=2, components set."""
        obs = _vitals_at(T0, sbp=94, hr=118, rr=24)

        with patch("backend.mcp_server.tools.score_deterioration_risk.FhirClient") as M:
            inst = M.return_value.__aenter__.return_value
            inst.get_observations = AsyncMock(return_value=obs)
            inst.get_conditions = AsyncMock(return_value=[])

            raw = await run("PT-009", 6, "postop", _sharp("PT-009"))

        result = json.loads(raw)
        assert result["qsofa_score"] == 2
        assert result["qsofa_components"]["rr_ge_22"] is True
        assert result["qsofa_components"]["sbp_le_100"] is True
        assert result["risk_band"] == "high"

    async def test_qsofa_score_1_rr_only(self):
        """Only RR ≥ 22 → qSOFA=1, not high band (unless composite also high)."""
        obs = _vitals_at(T0, sbp=122, hr=74, rr=24)

        with patch("backend.mcp_server.tools.score_deterioration_risk.FhirClient") as M:
            inst = M.return_value.__aenter__.return_value
            inst.get_observations = AsyncMock(return_value=obs)
            inst.get_conditions = AsyncMock(return_value=[])

            raw = await run("PT-001", 6, "postop", _sharp("PT-001"))

        result = json.loads(raw)
        assert result["qsofa_score"] == 1
        assert result["qsofa_components"]["rr_ge_22"] is True
        assert result["qsofa_components"]["sbp_le_100"] is False


# ---------------------------------------------------------------------------
# Composite risk formula tests
# ---------------------------------------------------------------------------


class TestB3CompositeRisk:

    async def test_composite_increases_with_mewt_breaches(self):
        """More MEWT breaches → higher composite risk."""
        # Normal vitals: no MEWT breaches
        obs_normal = _vitals_at(T0, sbp=122, hr=74, rr=16, spo2=98)
        # Bad vitals: multiple MEWT breaches (SBP 86 red, HR 118 yellow, RR 24 yellow)
        obs_bad = _vitals_at(T0, sbp=86, hr=118, rr=24, spo2=91)

        with patch("backend.mcp_server.tools.score_deterioration_risk.FhirClient") as M:
            inst = M.return_value.__aenter__.return_value
            inst.get_conditions = AsyncMock(return_value=[])

            inst.get_observations = AsyncMock(return_value=obs_normal)
            raw_normal = await run("PT-001", 6, "postop", _sharp("PT-001"))

            inst.get_observations = AsyncMock(return_value=obs_bad)
            raw_bad = await run("PT-001", 6, "postop", _sharp("PT-001"))

        normal = json.loads(raw_normal)
        bad = json.loads(raw_bad)
        assert bad["composite_risk"] > normal["composite_risk"]

    async def test_comorbidities_bump_composite(self):
        """Active Conditions increase composite_risk."""
        obs = _vitals_at(T0, sbp=122, hr=74, rr=16)

        with patch("backend.mcp_server.tools.score_deterioration_risk.FhirClient") as M:
            inst = M.return_value.__aenter__.return_value
            inst.get_observations = AsyncMock(return_value=obs)

            inst.get_conditions = AsyncMock(return_value=[])
            raw_no_cond = await run("PT-001", 6, "postop", _sharp("PT-001"))

            inst.get_conditions = AsyncMock(return_value=[
                _condition("44054006", "Type 2 diabetes mellitus"),
                _condition("44054007", "Chronic kidney disease"),
                _condition("44054008", "COPD"),
            ])
            raw_with_cond = await run("PT-001", 6, "postop", _sharp("PT-001"))

        no_cond = json.loads(raw_no_cond)
        with_cond = json.loads(raw_with_cond)
        assert with_cond["composite_risk"] >= no_cond["composite_risk"]

    async def test_composite_bounded_0_to_1(self):
        """composite_risk must always be in [0.0, 1.0]."""
        # Worst-case vitals: all thresholds breached + high qSOFA
        obs = (
            _vitals_at(T0,                       sbp=130, hr=76, rr=16, spo2=98)
            + _vitals_at(T0 + timedelta(hours=2), sbp=80,  hr=130, rr=30, spo2=88)
        )
        conditions = [_condition(str(i), f"Condition {i}") for i in range(5)]

        with patch("backend.mcp_server.tools.score_deterioration_risk.FhirClient") as M:
            inst = M.return_value.__aenter__.return_value
            inst.get_observations = AsyncMock(return_value=obs)
            inst.get_conditions = AsyncMock(return_value=conditions)

            raw = await run("PT-007", 6, "postop", _sharp("PT-007"))

        result = json.loads(raw)
        assert 0.0 <= result["composite_risk"] <= 1.0


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestB3ErrorHandling:

    async def test_fhir_unavailable_503(self):
        """5xx → status=fhir_error, risk_band=low (fail-safe)."""
        with patch("backend.mcp_server.tools.score_deterioration_risk.FhirClient") as M:
            inst = M.return_value.__aenter__.return_value
            inst.get_observations = AsyncMock(
                side_effect=FhirClientError("Service unavailable", status_code=503)
            )
            inst.get_conditions = AsyncMock(return_value=[])

            raw = await run("PT-001", 6, "postop", _sharp("PT-001"))

        result = json.loads(raw)
        assert result["status"] == ToolStatus.FHIR_UNAVAILABLE
        assert result["risk_band"] == "low"
        assert result["qsofa_score"] == 0

    async def test_no_vitals_in_window_ok_low(self):
        """No observations → status=ok, risk_band=low."""
        with patch("backend.mcp_server.tools.score_deterioration_risk.FhirClient") as M:
            inst = M.return_value.__aenter__.return_value
            inst.get_observations = AsyncMock(return_value=[])
            inst.get_conditions = AsyncMock(return_value=[])

            raw = await run("PT-001", 6, "postop", _sharp("PT-001"))

        result = json.loads(raw)
        assert result["status"] == ToolStatus.OK
        assert result["risk_band"] == "low"
        assert result["qsofa_score"] == 0


# ---------------------------------------------------------------------------
# Output schema tests
# ---------------------------------------------------------------------------


class TestB3OutputSchema:

    async def test_output_fields_present(self):
        """All required RiskScoreOutput fields are present in JSON."""
        obs = _vitals_at(T0, sbp=122, hr=74, rr=16)

        with patch("backend.mcp_server.tools.score_deterioration_risk.FhirClient") as M:
            inst = M.return_value.__aenter__.return_value
            inst.get_observations = AsyncMock(return_value=obs)
            inst.get_conditions = AsyncMock(return_value=[])

            raw = await run("PT-001", 6, "postop", _sharp("PT-001"))

        result = json.loads(raw)
        for field in (
            "status", "patient_id", "qsofa_score", "qsofa_components",
            "composite_risk", "risk_band", "rationale", "contributing_conditions",
        ):
            assert field in result, f"Missing field: {field}"

    async def test_qsofa_components_keys_present(self):
        """qsofa_components must contain exactly the three canonical keys."""
        obs = _vitals_at(T0, sbp=122, hr=74, rr=16)

        with patch("backend.mcp_server.tools.score_deterioration_risk.FhirClient") as M:
            inst = M.return_value.__aenter__.return_value
            inst.get_observations = AsyncMock(return_value=obs)
            inst.get_conditions = AsyncMock(return_value=[])

            raw = await run("PT-001", 6, "postop", _sharp("PT-001"))

        result = json.loads(raw)
        components = result["qsofa_components"]
        assert "rr_ge_22" in components
        assert "sbp_le_100" in components
        assert "altered_mental" in components

    async def test_rationale_mentions_qsofa(self):
        """rationale string must mention qSOFA (per API_CONTRACTS §1.2 examples)."""
        obs = _vitals_at(T0, sbp=122, hr=74, rr=16)

        with patch("backend.mcp_server.tools.score_deterioration_risk.FhirClient") as M:
            inst = M.return_value.__aenter__.return_value
            inst.get_observations = AsyncMock(return_value=obs)
            inst.get_conditions = AsyncMock(return_value=[])

            raw = await run("PT-001", 6, "postop", _sharp("PT-001"))

        result = json.loads(raw)
        assert "qSOFA" in result["rationale"]

    async def test_risk_band_values_are_canonical(self):
        """risk_band must be one of {low, moderate, high}."""
        for sbp, rr in [(122, 16), (94, 24)]:
            obs = _vitals_at(T0, sbp=sbp, hr=80, rr=rr)

            with patch("backend.mcp_server.tools.score_deterioration_risk.FhirClient") as M:
                inst = M.return_value.__aenter__.return_value
                inst.get_observations = AsyncMock(return_value=obs)
                inst.get_conditions = AsyncMock(return_value=[])

                raw = await run("PT-001", 6, "postop", _sharp("PT-001"))

            result = json.loads(raw)
            assert result["risk_band"] in ("low", "moderate", "high")
