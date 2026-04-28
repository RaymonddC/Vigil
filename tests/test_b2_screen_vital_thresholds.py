"""Unit tests for screen_vital_thresholds tool — BUILD_PLAN B2.

Acceptance criteria (B2):
  PT-001 → status=ok, breaches=[]
  PT-007@T+2h → status=triggered (hemodynamic trend rule: SBP −12.3%, HR +21.1%)
  PT-009@T+4h → status=triggered (absolute threshold breaches)

All tests mock FhirClient — no live HAPI required.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from backend.fhir.client import FhirClientError
from backend.fhir.models import CategoryItem, CodeableConcept, Coding, Observation, Quantity
from backend.mcp_server import synthetic_fallback as sf
from backend.mcp_server.tools.screen_vital_thresholds import run
from backend.schemas import FhirContext, ToolStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

T0 = datetime(2026, 4, 15, 10, 0, 0, tzinfo=UTC)
SHARP_BASE = FhirContext(url="http://localhost:8080/fhir", token=None, patient_id=None)


def _obs(loinc: str, value: float, unit: str, t: datetime) -> Observation:
    return Observation(
        resourceType="Observation",
        code=CodeableConcept(
            coding=[Coding(system="http://loinc.org", code=loinc)]
        ),
        category=[CategoryItem(coding=[Coding(code="vital-signs")])],
        valueQuantity=Quantity(value=value, unit=unit),
        effectiveDateTime=t,
    )


def _vitals_at(
    t: datetime,
    sbp: float,
    dbp: float,
    hr: float,
    rr: float,
    spo2: float,
    temp: float,
) -> list[Observation]:
    """Build a full vital-signs snapshot at a single timepoint."""
    return [
        _obs("8480-6", sbp,  "mm[Hg]", t),  # SBP
        _obs("8462-4", dbp,  "mm[Hg]", t),  # DBP
        _obs("8867-4", hr,   "/min",   t),  # HR
        _obs("9279-1", rr,   "/min",   t),  # RR
        _obs("59408-5", spo2, "%",     t),  # SpO2
        _obs("8310-5", temp, "Cel",    t),  # Temp
    ]


def _sharp(pid: str) -> FhirContext:
    return FhirContext(url="http://localhost:8080/fhir", token=None, patient_id=pid)


def _mock_client(observations: list[Observation]):
    """Return a context manager patch that yields a FhirClient mock."""
    return patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient")


# ---------------------------------------------------------------------------
# Acceptance tests (required by BUILD_PLAN B2)
# ---------------------------------------------------------------------------


class TestB2AcceptanceCriteria:
    """Canonical acceptance tests from BUILD_PLAN B2."""

    async def test_pt001_status_ok_empty_breaches(self):
        """PT-001 stable vitals → status=ok, breaches=[]."""
        obs = _vitals_at(T0, sbp=122, dbp=78, hr=74, rr=16, spo2=98, temp=36.8)

        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(return_value=obs)

            raw = await run("PT-001", 240, "postop", _sharp("PT-001"))

        result = json.loads(raw)
        assert result["status"] == ToolStatus.OK
        assert result["patient_id"] == "PT-001"
        assert result["breaches"] == []
        assert result["scanned_count"] == len(obs)

    async def test_pt007_t2h_trend_rule_triggered(self):
        """PT-007 T0→T+2h: SBP drops 12.3%, HR rises 21.1% → TRIGGERED (trend rule).

        Per CLINICAL_EVIDENCE §2.3: hemodynamic trend rule fires when SBP drops
        >=10% AND HR rises >=15% within any 2-hour window.
        """
        obs = (
            _vitals_at(T0,                     sbp=130, dbp=82, hr=76, rr=16, spo2=98, temp=37.0)
            + _vitals_at(T0 + timedelta(hours=2), sbp=114, dbp=72, hr=92, rr=18, spo2=96, temp=37.2)
        )

        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(return_value=obs)

            raw = await run("PT-007", 240, "postop", _sharp("PT-007"))

        result = json.loads(raw)
        assert result["status"] == ToolStatus.TRIGGERED
        trend_breaches = [b for b in result["breaches"] if b["loinc"] == "TREND"]
        assert len(trend_breaches) == 1, "hemodynamic trend breach must be present"
        assert trend_breaches[0]["severity"] == "red"
        assert "SBP" in trend_breaches[0]["threshold"]

    async def test_pt009_t4h_absolute_thresholds_triggered(self):
        """PT-009 T+4h absolute thresholds: SBP 94, HR 118, RR 24, Temp 38.8 → TRIGGERED.

        Expects at minimum SBP and HR absolute threshold breaches.
        """
        obs = _vitals_at(
            T0 + timedelta(hours=4),
            sbp=94, dbp=58, hr=118, rr=24, spo2=94, temp=38.8,
        )

        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(return_value=obs)

            raw = await run("PT-009", 480, "postop", _sharp("PT-009"))

        result = json.loads(raw)
        assert result["status"] == ToolStatus.TRIGGERED
        loincs = {b["loinc"] for b in result["breaches"]}
        assert "8480-6" in loincs, "SBP breach expected"
        assert "8867-4" in loincs, "HR breach expected"


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestB2ErrorHandling:

    async def test_fhir_unavailable_503(self):
        """5xx FHIR error → status=fhir_error, breaches=[], scanned_count=0."""
        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(
                side_effect=FhirClientError("Service unavailable", status_code=503)
            )

            raw = await run("PT-001", 240, "postop", _sharp("PT-001"))

        result = json.loads(raw)
        assert result["status"] == ToolStatus.FHIR_UNAVAILABLE
        assert result["breaches"] == []
        assert result["scanned_count"] == 0

    async def test_fhir_error_404(self):
        """404 → status=fhir_error (B2 maps all FHIR errors to FHIR_UNAVAILABLE per §1.1)."""
        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(
                side_effect=FhirClientError("Not found", status_code=404)
            )

            raw = await run("PT-999", 240, "postop", _sharp("PT-999"))

        result = json.loads(raw)
        # §1.1 error handling: "FHIR fetch fails → status=fhir_error".
        # The implementation maps all FhirClientError → FHIR_UNAVAILABLE ("fhir_error").
        assert result["status"] == ToolStatus.FHIR_UNAVAILABLE

    async def test_no_vitals_in_window_ok(self):
        """Empty observation list → status=ok, scanned_count=0.

        Per API_CONTRACTS §1.1: 'No vitals in window: status=ok with scanned_count=0.'
        """
        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(return_value=[])

            raw = await run("PT-001", 240, "postop", _sharp("PT-001"))

        result = json.loads(raw)
        assert result["status"] == ToolStatus.OK
        assert result["scanned_count"] == 0
        assert result["breaches"] == []

    async def test_observations_missing_value_skipped(self):
        """Observations without valueQuantity are silently skipped."""
        good = _obs("8480-6", 122.0, "mm[Hg]", T0)
        bad = Observation(
            resourceType="Observation",
            code=CodeableConcept(coding=[Coding(system="http://loinc.org", code="8867-4")]),
            # no valueQuantity
        )

        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(
                return_value=[good, bad]
            )

            raw = await run("PT-001", 240, "postop", _sharp("PT-001"))

        result = json.loads(raw)
        # Only 1 observation counted — the bad one is skipped
        assert result["scanned_count"] == 1


# ---------------------------------------------------------------------------
# Output schema tests
# ---------------------------------------------------------------------------


class TestB2OutputSchema:

    async def test_output_fields_present(self):
        """All required ScreenVitalsOutput fields are present in JSON."""
        obs = _vitals_at(T0, sbp=122, dbp=78, hr=74, rr=16, spo2=98, temp=36.8)

        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(return_value=obs)

            raw = await run("PT-001", 240, "postop", _sharp("PT-001"))

        result = json.loads(raw)
        for field in ("status", "patient_id", "trajectory", "breaches", "scanned_count",
                      "window_start", "window_end"):
            assert field in result, f"Missing field: {field}"

    async def test_trajectory_echoed(self):
        """trajectory field echoes the input value."""
        obs = _vitals_at(T0, sbp=122, dbp=78, hr=74, rr=16, spo2=98, temp=36.8)

        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(return_value=obs)

            raw = await run("PT-001", 240, "postpartum", _sharp("PT-001"))

        result = json.loads(raw)
        assert result["trajectory"] == "postpartum"

    async def test_patient_id_echoed(self):
        """patient_id field echoes the resolved patient ID."""
        obs = _vitals_at(T0, sbp=122, dbp=78, hr=74, rr=16, spo2=98, temp=36.8)

        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(return_value=obs)

            raw = await run("PT-007", 240, "postop", _sharp("PT-007"))

        result = json.loads(raw)
        assert result["patient_id"] == "PT-007"

    async def test_window_timestamps_are_iso(self):
        """window_start and window_end are ISO 8601 strings."""
        obs = _vitals_at(T0, sbp=122, dbp=78, hr=74, rr=16, spo2=98, temp=36.8)

        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(return_value=obs)

            raw = await run("PT-001", 60, "postop", _sharp("PT-001"))

        result = json.loads(raw)
        # Should parse without error
        datetime.fromisoformat(result["window_start"])
        datetime.fromisoformat(result["window_end"])


# ---------------------------------------------------------------------------
# Postpartum trajectory tests
# ---------------------------------------------------------------------------


class TestB2PostpartumTrajectory:

    async def test_sbp_high_postpartum_red_breach(self):
        """SBP 162 mmHg exceeds postpartum red_high threshold (160) → TRIGGERED, red breach."""
        obs = _vitals_at(T0, sbp=162, dbp=112, hr=100, rr=22, spo2=95, temp=37.0)

        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(return_value=obs)

            raw = await run("PT-010", 240, "postpartum", _sharp("PT-010"))

        result = json.loads(raw)
        assert result["status"] == ToolStatus.TRIGGERED
        sbp_breaches = [b for b in result["breaches"] if b["loinc"] == "8480-6"]
        assert sbp_breaches, "SBP breach must be present"
        assert sbp_breaches[0]["severity"] == "red"

    async def test_postpartum_normal_sbp_120_ok(self):
        """SBP 120 is within postpartum normal range → status=ok."""
        obs = _vitals_at(T0, sbp=120, dbp=78, hr=74, rr=16, spo2=98, temp=36.8)

        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(return_value=obs)

            raw = await run("PT-010", 240, "postpartum", _sharp("PT-010"))

        result = json.loads(raw)
        assert result["status"] == ToolStatus.OK


# ---------------------------------------------------------------------------
# Breach detail tests
# ---------------------------------------------------------------------------


class TestB2BreachDetails:

    async def test_breach_fields_present(self):
        """VitalBreach contains all required fields."""
        # SBP 86 fires red breach (<90)
        obs = [_obs("8480-6", 86.0, "mm[Hg]", T0)]

        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(return_value=obs)

            raw = await run("PT-007", 240, "postop", _sharp("PT-007"))

        result = json.loads(raw)
        assert result["status"] == ToolStatus.TRIGGERED
        breach = result["breaches"][0]
        for field in ("loinc", "label", "value", "unit", "threshold", "severity", "observed_at"):
            assert field in breach, f"Breach missing field: {field}"

    async def test_sbp_red_threshold(self):
        """SBP 86 < 90 → red breach with threshold '<90'."""
        obs = [_obs("8480-6", 86.0, "mm[Hg]", T0)]

        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(return_value=obs)

            raw = await run("PT-007", 240, "postop", _sharp("PT-007"))

        result = json.loads(raw)
        sbp_breach = next(b for b in result["breaches"] if b["loinc"] == "8480-6")
        assert sbp_breach["severity"] == "red"
        assert "<90" in sbp_breach["threshold"]
        assert sbp_breach["value"] == pytest.approx(86.0)

    async def test_data_source_defaults_to_fhir(self):
        """Live FHIR fetch tags the result with data_source='fhir'."""
        obs = _vitals_at(T0, sbp=122, dbp=78, hr=74, rr=16, spo2=98, temp=36.8)

        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(return_value=obs)

            raw = await run("PT-001", 240, "postop", _sharp("PT-001"))

        result = json.loads(raw)
        assert result["data_source"] == "fhir"

    async def test_worst_breach_per_loinc_reported(self):
        """When two readings exist for same LOINC, worst (red) breach is reported."""
        # Two SBP readings: one yellow (95), one red (86)
        obs = [
            _obs("8480-6", 95.0, "mm[Hg]", T0),                     # yellow (<100)
            _obs("8480-6", 86.0, "mm[Hg]", T0 + timedelta(minutes=30)),  # red (<90)
        ]

        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(return_value=obs)

            raw = await run("PT-007", 240, "postop", _sharp("PT-007"))

        result = json.loads(raw)
        sbp_breaches = [b for b in result["breaches"] if b["loinc"] == "8480-6"]
        assert len(sbp_breaches) == 1, "Only one breach per LOINC (worst)"
        assert sbp_breaches[0]["severity"] == "red"


# ---------------------------------------------------------------------------
# Synthetic-fallback tests — auth errors trigger PT-007 trajectory load
# ---------------------------------------------------------------------------


class TestB2SyntheticFallback:
    """When FHIR returns 401/403 AND VIGIL_SYNTHETIC_FALLBACK is set,
    the tool transparently falls back to PT-007 and tags the result."""

    async def test_403_with_env_uses_synthetic(self, monkeypatch):
        monkeypatch.setenv("VIGIL_SYNTHETIC_FALLBACK", "true")
        sf.reset_for_tests()

        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(
                side_effect=FhirClientError(
                    "Insufficient scope access", status_code=403
                )
            )

            raw = await run("PT-007", 240, "postop", _sharp("PT-007"))

        result = json.loads(raw)
        assert result["data_source"] == "synthetic_demo"
        # PT-007 is the deteriorating trajectory — must trigger the
        # MEWT trend rule, never status='fhir_error'.
        assert result["status"] == ToolStatus.TRIGGERED
        assert result["scanned_count"] > 0
        assert len(result["breaches"]) >= 1

    async def test_403_without_env_returns_error_envelope(self, monkeypatch):
        """Default-off: 403 still surfaces as fhir_error when env not set."""
        monkeypatch.delenv("VIGIL_SYNTHETIC_FALLBACK", raising=False)
        sf.reset_for_tests()

        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(
                side_effect=FhirClientError(
                    "Insufficient scope access", status_code=403
                )
            )

            raw = await run("PT-007", 240, "postop", _sharp("PT-007"))

        result = json.loads(raw)
        assert result["status"] == ToolStatus.FHIR_UNAVAILABLE
        assert result["data_source"] == "fhir"

    async def test_500_with_env_uses_synthetic_in_demo_mode(self, monkeypatch):
        """In demo mode, ANY FhirClientError (including 5xx) flips to
        synthetic so PO's launchpad always renders something coherent.
        With the env flag OFF (production default) this test's twin
        ``test_500_without_env_does_not_use_synthetic`` confirms 5xx still
        propagates as ``fhir_error``."""
        monkeypatch.setenv("VIGIL_SYNTHETIC_FALLBACK", "true")
        sf.reset_for_tests()

        with patch("backend.mcp_server.tools.screen_vital_thresholds.FhirClient") as M:
            M.return_value.__aenter__.return_value.get_observations = AsyncMock(
                side_effect=FhirClientError("server boom", status_code=503)
            )

            raw = await run("PT-007", 240, "postop", _sharp("PT-007"))

        result = json.loads(raw)
        assert result["data_source"] == "synthetic_demo"
        # PT-007's bundled trajectory has SBP < 90 + HR > 110, so the
        # screen should trigger.
        assert result["status"] == ToolStatus.TRIGGERED
