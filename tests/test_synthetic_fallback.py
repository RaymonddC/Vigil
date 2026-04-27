"""Unit tests for the synthetic-FHIR fallback module.

Verifies that ``backend/mcp_server/synthetic_fallback.py``:

  1. Reads ``VIGIL_SYNTHETIC_FALLBACK`` correctly (truthy / falsy / unset).
  2. Loads PT-007's bundle and exposes the right resource counts.
  3. Returns Observations sorted newest-first and time-shifted so the
     latest sample lands shortly before "now" (so MEWT lookback windows
     find the data regardless of when ``data/seed_hapi.py`` was last run).
  4. Filters Observations by category (vital-signs vs. laboratory).
  5. Detects FHIR auth errors (401/403) but not generic FHIR errors.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.fhir.client import FhirClientError, is_fhir_auth_error
from backend.mcp_server import synthetic_fallback as sf


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    """Clear the bundle cache between tests so each test gets a fresh load."""
    sf.reset_for_tests()
    yield
    sf.reset_for_tests()


class TestEnvFlag:
    def test_env_unset_disables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(sf.VIGIL_SYNTHETIC_FALLBACK_ENV, raising=False)
        assert sf.is_fallback_enabled() is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "YES", "on"])
    def test_truthy_values_enable(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv(sf.VIGIL_SYNTHETIC_FALLBACK_ENV, value)
        assert sf.is_fallback_enabled() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "  "])
    def test_falsy_values_disable(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv(sf.VIGIL_SYNTHETIC_FALLBACK_ENV, value)
        assert sf.is_fallback_enabled() is False


class TestBundleLoading:
    def test_patient_resource_present(self) -> None:
        patient = sf.get_synthetic_patient()
        assert patient.id == "PT-007"
        assert patient.name, "synthetic patient must carry a name"

    def test_encounter_resource_present(self) -> None:
        encounter = sf.get_synthetic_encounter()
        assert encounter is not None
        assert encounter.id == "ENC-PT-007"

    def test_conditions_present_and_active(self) -> None:
        conditions = sf.get_synthetic_conditions()
        # PT-007 ships with T2DM + CKD3 — both active.
        assert len(conditions) >= 2
        for cond in conditions:
            assert cond.clinicalStatus is not None

    def test_medication_administrations_present(self) -> None:
        meds = sf.get_synthetic_medication_administrations()
        # PT-007 ships with the pre-op cefazolin only.
        assert len(meds) >= 1
        first = meds[0]
        assert first.status == "completed"
        assert first.medicationCodeableConcept is not None


class TestObservationSorting:
    def test_returns_non_empty(self) -> None:
        obs = sf.get_synthetic_observations()
        assert len(obs) > 0

    def test_sorted_newest_first(self) -> None:
        obs = sf.get_synthetic_observations()
        timestamps = [
            o.effectiveDateTime
            for o in obs
            if o.effectiveDateTime is not None
        ]
        # Strictly non-increasing — matches HAPI's _sort=-date contract.
        assert timestamps == sorted(timestamps, reverse=True)

    def test_filter_by_vital_signs_category(self) -> None:
        vitals = sf.get_synthetic_observations(category="vital-signs")
        assert vitals, "PT-007 must include vital-signs Observations"
        for o in vitals:
            assert o.category_code == "vital-signs"

    def test_filter_by_laboratory_category(self) -> None:
        labs = sf.get_synthetic_observations(category="laboratory")
        assert labs, "PT-007 must include laboratory Observations"
        for o in labs:
            assert o.category_code == "laboratory"


class TestTimestampRebasing:
    def test_latest_observation_is_recent(self) -> None:
        """The newest Observation must land within ~10 min of 'now'.

        Rebasing anchors the bundle's max sample to ``now - 5min``;
        allow ±5 min slack for clock drift between ``datetime.now()``
        calls inside the rebase + outside it.
        """
        obs = sf.get_synthetic_observations()
        latest = obs[0].effectiveDateTime
        assert latest is not None
        now = datetime.now(UTC)
        delta = abs(now - latest)
        assert delta < timedelta(minutes=10), (
            f"latest obs {latest} is {delta} from now {now}"
        )

    def test_relative_offsets_preserved(self) -> None:
        """Two observations originally 8h apart remain 8h apart."""
        obs = sf.get_synthetic_observations()
        timestamps = [
            o.effectiveDateTime
            for o in obs
            if o.effectiveDateTime is not None
        ]
        # PT-007 trajectory spans T0..T+8h, so total spread should be ~8h.
        spread = max(timestamps) - min(timestamps)
        assert timedelta(hours=7, minutes=30) <= spread <= timedelta(
            hours=8, minutes=30
        ), f"expected ~8h spread, got {spread}"


class TestAuthErrorDetection:
    """Narrow mode (env flag OFF): only 401/403 trigger fallback."""

    def test_403_is_auth_error(self, monkeypatch) -> None:
        monkeypatch.delenv("VIGIL_SYNTHETIC_FALLBACK", raising=False)
        exc = FhirClientError("forbidden", status_code=403)
        assert is_fhir_auth_error(exc) is True

    def test_401_is_auth_error(self, monkeypatch) -> None:
        monkeypatch.delenv("VIGIL_SYNTHETIC_FALLBACK", raising=False)
        exc = FhirClientError("unauthorised", status_code=401)
        assert is_fhir_auth_error(exc) is True

    def test_500_is_not_auth_error(self, monkeypatch) -> None:
        monkeypatch.delenv("VIGIL_SYNTHETIC_FALLBACK", raising=False)
        exc = FhirClientError("server error", status_code=500)
        assert is_fhir_auth_error(exc) is False

    def test_404_is_not_auth_error(self, monkeypatch) -> None:
        monkeypatch.delenv("VIGIL_SYNTHETIC_FALLBACK", raising=False)
        exc = FhirClientError("not found", status_code=404)
        assert is_fhir_auth_error(exc) is False

    def test_unrelated_exception_is_not_auth_error(self, monkeypatch) -> None:
        monkeypatch.delenv("VIGIL_SYNTHETIC_FALLBACK", raising=False)
        assert is_fhir_auth_error(ValueError("boom")) is False


class TestAuthErrorDetectionDemoMode:
    """Demo mode (env flag ON): any FhirClientError triggers fallback so
    PO's launchpad always renders something coherent regardless of which
    failure mode their FHIR proxy hits (403 anonymous, 422 bad workspace,
    503 transient)."""

    def test_403_triggers_in_demo_mode(self, monkeypatch) -> None:
        monkeypatch.setenv("VIGIL_SYNTHETIC_FALLBACK", "true")
        assert is_fhir_auth_error(FhirClientError("forbidden", status_code=403)) is True

    def test_422_triggers_in_demo_mode(self, monkeypatch) -> None:
        monkeypatch.setenv("VIGIL_SYNTHETIC_FALLBACK", "true")
        assert is_fhir_auth_error(FhirClientError("unprocessable", status_code=422)) is True

    def test_500_triggers_in_demo_mode(self, monkeypatch) -> None:
        monkeypatch.setenv("VIGIL_SYNTHETIC_FALLBACK", "true")
        assert is_fhir_auth_error(FhirClientError("server error", status_code=500)) is True

    def test_non_fhir_exception_does_not_trigger(self, monkeypatch) -> None:
        monkeypatch.setenv("VIGIL_SYNTHETIC_FALLBACK", "true")
        assert is_fhir_auth_error(ValueError("boom")) is False


class TestDisclosureText:
    def test_disclosure_mentions_demo(self) -> None:
        text = sf.synthetic_disclosure()
        # Disclosure must be honest — never claim live data.
        assert "demo" in text.lower() or "synthetic" in text.lower()
        assert "FHIR" in text


class TestCachingBehaviour:
    def test_reset_for_tests_reloads(self) -> None:
        # Touch the cache once, then reset, then re-fetch — must succeed.
        first_count = len(sf.get_synthetic_observations())
        sf.reset_for_tests()
        second_count = len(sf.get_synthetic_observations())
        assert first_count == second_count
