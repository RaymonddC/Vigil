"""Table-driven tests for criteria rule modules.

Test data sourced from SYNTHETIC_DATA_SPEC §2.1-2.4 and CLINICAL_EVIDENCE.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.criteria.kdigo import evaluate_kdigo
from backend.criteria.mewt import VitalReading, evaluate_mewt
from backend.criteria.qsofa import evaluate_qsofa
from backend.criteria.sirs import evaluate_sirs

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

T0 = datetime(2026, 4, 15, 10, 0, 0, tzinfo=UTC)


def _vitals_at(
    t: datetime,
    sbp: float,
    dbp: float,
    hr: float,
    rr: float,
    spo2: float,
    temp: float,
    urine: float,
) -> list[VitalReading]:
    """Build a list of VitalReading for one timepoint."""
    return [
        VitalReading(loinc="8480-6", value=sbp, unit="mm[Hg]", timestamp=t),
        VitalReading(loinc="8462-4", value=dbp, unit="mm[Hg]", timestamp=t),
        VitalReading(loinc="8867-4", value=hr, unit="/min", timestamp=t),
        VitalReading(loinc="9279-1", value=rr, unit="/min", timestamp=t),
        VitalReading(loinc="59408-5", value=spo2, unit="%", timestamp=t),
        VitalReading(loinc="8310-5", value=temp, unit="Cel", timestamp=t),
        VitalReading(loinc="9192-6", value=urine, unit="mL/h", timestamp=t),
    ]


# ===================================================================
# MEWT Tests
# ===================================================================


class TestMewtStable:
    """MEWT on stable vitals (SYNTHETIC_DATA_SPEC §2.1 PT-001)."""

    def test_stable_t0_not_triggered(self):
        vitals = _vitals_at(T0, sbp=122, dbp=78, hr=74, rr=16, spo2=98, temp=36.8, urine=50)
        result = evaluate_mewt(vitals)
        assert not result.triggered
        assert result.score == 0
        assert result.breaches == []

    def test_stable_all_timepoints_not_triggered(self):
        """All 6 timepoints for stable trajectory should be NORMAL."""
        stable_data = [
            (T0, 122, 78, 74, 16, 98, 36.8, 50),
            (T0 + timedelta(hours=1), 120, 76, 72, 16, 98, 36.9, 48),
            (T0 + timedelta(hours=2), 118, 75, 74, 15, 99, 37.0, 52),
            (T0 + timedelta(hours=4), 121, 77, 76, 16, 98, 37.0, 45),
            (T0 + timedelta(hours=6), 119, 76, 72, 15, 98, 36.9, 50),
            (T0 + timedelta(hours=8), 120, 78, 74, 16, 99, 37.1, 48),
        ]
        all_vitals: list[VitalReading] = []
        for row in stable_data:
            all_vitals.extend(_vitals_at(*row))
        result = evaluate_mewt(all_vitals)
        assert not result.triggered


class TestMewtDeteriorating:
    """MEWT on deteriorating vitals (SYNTHETIC_DATA_SPEC §2.2 PT-007)."""

    def test_t0_not_triggered(self):
        vitals = _vitals_at(T0, sbp=130, dbp=82, hr=76, rr=16, spo2=98, temp=37.0, urine=50)
        result = evaluate_mewt(vitals)
        assert not result.triggered

    def test_t2_trend_rule_fires(self):
        """PT-007 T+0h -> T+2h: SBP 130->114 = -12.3%, HR 76->92 = +21.1%.

        Per CLINICAL_EVIDENCE §2.3, this fires the hemodynamic trend rule
        (SBP drop >=10% AND HR rise >=15% over 2h window).
        """
        vitals = (
            _vitals_at(T0, sbp=130, dbp=82, hr=76, rr=16, spo2=98, temp=37.0, urine=50)
            + _vitals_at(
                T0 + timedelta(hours=2),
                sbp=114, dbp=72, hr=92, rr=18, spo2=96, temp=37.2, urine=35,
            )
        )
        result = evaluate_mewt(vitals)
        assert result.triggered
        # Should have exactly the trend breach (no absolute thresholds crossed)
        trend_breaches = [b for b in result.breaches if b.loinc == "TREND"]
        assert len(trend_breaches) == 1
        assert "SBP -12.3%" in trend_breaches[0].threshold
        assert "HR +21.1%" in trend_breaches[0].threshold
        assert trend_breaches[0].severity == "red"

    def test_t4_absolute_thresholds_cross(self):
        """PT-007 T+4h: SBP 102, HR 100, RR 20 — HR crosses >110? No, HR=100.
        But check SBP < 100? No, SBP=102. With trend from T+0h still fires.
        """
        vitals = (
            _vitals_at(T0, sbp=130, dbp=82, hr=76, rr=16, spo2=98, temp=37.0, urine=50)
            + _vitals_at(
                T0 + timedelta(hours=2),
                sbp=114, dbp=72, hr=92, rr=18, spo2=96, temp=37.2, urine=35,
            )
            + _vitals_at(
                T0 + timedelta(hours=4),
                sbp=102, dbp=64, hr=100, rr=20, spo2=95, temp=37.3, urine=26,
            )
        )
        result = evaluate_mewt(vitals)
        assert result.triggered

    def test_t6_frank_decompensation(self):
        """PT-007 T+6h: SBP 94 (<100 yellow), HR 108, RR 22 (>=22 yellow)."""
        vitals = _vitals_at(
            T0 + timedelta(hours=6),
            sbp=94, dbp=58, hr=108, rr=22, spo2=94, temp=37.4, urine=18,
        )
        result = evaluate_mewt(vitals)
        assert result.triggered
        loinc_codes = {b.loinc for b in result.breaches}
        assert "8480-6" in loinc_codes  # SBP < 100
        assert "9279-1" in loinc_codes  # RR >= 22

    def test_t8_severe(self):
        """PT-007 T+8h: SBP 88 (<90 red), HR 116 (>110 yellow), RR 23, SpO2 93 (<93 yellow)."""
        vitals = _vitals_at(
            T0 + timedelta(hours=8),
            sbp=88, dbp=54, hr=116, rr=23, spo2=93, temp=37.5, urine=12,
        )
        result = evaluate_mewt(vitals)
        assert result.triggered
        red_breaches = [b for b in result.breaches if b.severity == "red"]
        assert any(b.loinc == "8480-6" for b in red_breaches)  # SBP < 90 is red


class TestMewtSepsis:
    """MEWT on sepsis onset vitals (SYNTHETIC_DATA_SPEC §2.3 PT-009)."""

    def test_t4_sepsis_onset(self):
        """PT-009 T+4h: SBP 94, HR 118, RR 24, SpO2 94, Temp 38.8."""
        vitals = _vitals_at(
            T0 + timedelta(hours=4),
            sbp=94, dbp=58, hr=118, rr=24, spo2=94, temp=38.8, urine=22,
        )
        result = evaluate_mewt(vitals)
        assert result.triggered
        loincs = {b.loinc for b in result.breaches}
        assert "8480-6" in loincs  # SBP < 100
        assert "8867-4" in loincs  # HR > 110
        assert "9279-1" in loincs  # RR >= 22
        assert "8310-5" in loincs  # Temp > 38


class TestMewtPostpartum:
    """MEWT on PPH vitals (SYNTHETIC_DATA_SPEC §2.4 PT-010), postpartum trajectory."""

    def test_t2_pph_emergency(self):
        """PT-010 T+2h: SBP 88, HR 124, RR 22. Postpartum thresholds.

        SBP 88 < 90 (yellow, postpartum yellow_low=90),
        HR 124 > 110 (yellow), RR 22 >= 22 (yellow).
        """
        vitals = _vitals_at(
            T0 + timedelta(hours=2),
            sbp=88, dbp=52, hr=124, rr=22, spo2=96, temp=36.6, urine=18,
        )
        result = evaluate_mewt(vitals, trajectory="postpartum")
        assert result.triggered
        assert result.score >= 3  # SBP, HR, RR all breach


class TestMewtTrendEdgeCases:
    """Edge cases for the hemodynamic trend rule."""

    def test_sbp_drops_but_hr_stable_no_trigger(self):
        """SBP drops 15% but HR only rises 5% — should NOT trigger."""
        vitals = (
            _vitals_at(T0, sbp=130, dbp=80, hr=76, rr=16, spo2=98, temp=37.0, urine=50)
            + _vitals_at(
                T0 + timedelta(hours=2),
                sbp=110, dbp=70, hr=80, rr=16, spo2=98, temp=37.0, urine=50,
            )
        )
        result = evaluate_mewt(vitals)
        trend_breaches = [b for b in result.breaches if b.loinc == "TREND"]
        assert len(trend_breaches) == 0

    def test_hr_rises_but_sbp_stable_no_trigger(self):
        """HR rises 20% but SBP only drops 3% — should NOT trigger."""
        vitals = (
            _vitals_at(T0, sbp=130, dbp=80, hr=76, rr=16, spo2=98, temp=37.0, urine=50)
            + _vitals_at(
                T0 + timedelta(hours=2),
                sbp=126, dbp=78, hr=92, rr=16, spo2=98, temp=37.0, urine=50,
            )
        )
        result = evaluate_mewt(vitals)
        trend_breaches = [b for b in result.breaches if b.loinc == "TREND"]
        assert len(trend_breaches) == 0

    def test_window_exceeded_no_trigger(self):
        """SBP/HR trend meets thresholds but over 3h window — should NOT trigger
        because window limit is 2h."""
        vitals = (
            _vitals_at(T0, sbp=130, dbp=80, hr=76, rr=16, spo2=98, temp=37.0, urine=50)
            + _vitals_at(
                T0 + timedelta(hours=3),
                sbp=114, dbp=72, hr=92, rr=16, spo2=98, temp=37.0, urine=50,
            )
        )
        result = evaluate_mewt(vitals)
        trend_breaches = [b for b in result.breaches if b.loinc == "TREND"]
        assert len(trend_breaches) == 0

    def test_single_reading_no_trend(self):
        """Only one timepoint — trend rule cannot fire."""
        vitals = _vitals_at(T0, sbp=90, dbp=60, hr=120, rr=25, spo2=91, temp=38.5, urine=20)
        result = evaluate_mewt(vitals)
        # Absolute thresholds may fire but trend should not
        trend_breaches = [b for b in result.breaches if b.loinc == "TREND"]
        assert len(trend_breaches) == 0

    def test_empty_vitals(self):
        result = evaluate_mewt([])
        assert not result.triggered
        assert result.score == 0


# ===================================================================
# qSOFA Tests
# ===================================================================


class TestQsofa:
    """qSOFA scoring (CLINICAL_EVIDENCE §3.1, Singer 2016)."""

    def test_all_normal_score_0(self):
        result = evaluate_qsofa(sbp=120, rr=16, gcs=15)
        assert result.score == 0
        assert not result.triggered

    def test_rr_only_score_1(self):
        result = evaluate_qsofa(sbp=120, rr=24, gcs=15)
        assert result.score == 1
        assert not result.triggered
        assert result.components["rr_ge_22"]
        assert not result.components["sbp_le_100"]

    def test_sbp_only_score_1(self):
        result = evaluate_qsofa(sbp=95, rr=16, gcs=15)
        assert result.score == 1
        assert not result.triggered
        assert result.components["sbp_le_100"]

    def test_rr_and_sbp_score_2_triggered(self):
        """PT-009 T+4h: RR 24 >= 22, SBP 94 <= 100 => qSOFA=2."""
        result = evaluate_qsofa(sbp=94, rr=24, gcs=15)
        assert result.score == 2
        assert result.triggered

    def test_all_three_score_3(self):
        result = evaluate_qsofa(sbp=85, rr=26, gcs=12)
        assert result.score == 3
        assert result.triggered

    def test_altered_mental_flag(self):
        result = evaluate_qsofa(sbp=120, rr=16, altered_mental=True)
        assert result.score == 1
        assert result.components["altered_mental"]

    def test_gcs_14_counts_as_altered(self):
        result = evaluate_qsofa(sbp=120, rr=16, gcs=14)
        assert result.components["altered_mental"]

    def test_gcs_15_not_altered(self):
        result = evaluate_qsofa(sbp=120, rr=16, gcs=15)
        assert not result.components["altered_mental"]

    def test_sbp_exactly_100(self):
        """SBP <= 100 boundary: 100 should be included."""
        result = evaluate_qsofa(sbp=100, rr=16, gcs=15)
        assert result.components["sbp_le_100"]

    def test_rr_exactly_22(self):
        """RR >= 22 boundary: 22 should be included."""
        result = evaluate_qsofa(sbp=120, rr=22, gcs=15)
        assert result.components["rr_ge_22"]

    def test_rr_21_not_triggered(self):
        result = evaluate_qsofa(sbp=120, rr=21, gcs=15)
        assert not result.components["rr_ge_22"]

    def test_none_values_score_0(self):
        result = evaluate_qsofa()
        assert result.score == 0
        assert not result.triggered

    def test_pt001_stable(self):
        """PT-001 stable: SBP 122, RR 16 => qSOFA=0."""
        result = evaluate_qsofa(sbp=122, rr=16, gcs=15)
        assert result.score == 0

    def test_pt007_t6_deteriorating(self):
        """PT-007 T+6h: SBP 94, RR 22 => qSOFA=2."""
        result = evaluate_qsofa(sbp=94, rr=22, gcs=15)
        assert result.score == 2
        assert result.triggered


# ===================================================================
# SIRS Tests
# ===================================================================


class TestSirs:
    """SIRS 2-of-4 criteria (Bone 1992)."""

    def test_all_normal_score_0(self):
        result = evaluate_sirs(temp=37.0, hr=72, rr=16, wbc=8.0)
        assert result.score == 0
        assert not result.triggered

    def test_two_criteria_triggered(self):
        """PT-009 T+2h: Temp 38.6 (>38), HR 105 (>90) => SIRS=2."""
        result = evaluate_sirs(temp=38.6, hr=105, rr=22, wbc=10.5)
        assert result.score >= 2
        assert result.triggered

    def test_pt009_t4h_all_four(self):
        """PT-009 T+4h: Temp 38.8, HR 118, RR 24, WBC 18.4 => SIRS=4."""
        result = evaluate_sirs(temp=38.8, hr=118, rr=24, wbc=18.4)
        assert result.score == 4
        assert result.triggered

    def test_temp_low_fires(self):
        result = evaluate_sirs(temp=35.5, hr=72, rr=16, wbc=8.0)
        assert result.components["temp_abnormal"]

    def test_wbc_low_fires(self):
        result = evaluate_sirs(temp=37.0, hr=72, rr=16, wbc=3.5)
        assert result.components["wbc_abnormal"]

    def test_bands_alone_fires(self):
        result = evaluate_sirs(temp=37.0, hr=72, rr=16, wbc=7.0, band_pct=12.0)
        assert result.components["wbc_abnormal"]

    def test_single_criterion_not_triggered(self):
        result = evaluate_sirs(temp=38.5, hr=72, rr=16, wbc=8.0)
        assert result.score == 1
        assert not result.triggered

    def test_pt001_stable(self):
        """PT-001 stable: Temp 36.8, HR 74, RR 16, WBC 8.1 => SIRS=0."""
        result = evaluate_sirs(temp=36.8, hr=74, rr=16, wbc=8.1)
        assert result.score == 0

    def test_none_values(self):
        result = evaluate_sirs()
        assert result.score == 0
        assert not result.triggered

    def test_boundary_temp_exactly_38(self):
        """Temp must be > 38, not >= 38."""
        result = evaluate_sirs(temp=38.0, hr=72, rr=16, wbc=8.0)
        assert not result.components["temp_abnormal"]

    def test_boundary_hr_exactly_90(self):
        """HR must be > 90, not >= 90."""
        result = evaluate_sirs(temp=37.0, hr=90, rr=16, wbc=8.0)
        assert not result.components["hr_gt_90"]

    def test_boundary_rr_exactly_20(self):
        """RR must be > 20, not >= 20."""
        result = evaluate_sirs(temp=37.0, hr=72, rr=20, wbc=8.0)
        assert not result.components["rr_gt_20"]


# ===================================================================
# KDIGO Tests
# ===================================================================


class TestKdigo:
    """KDIGO AKI staging (CLINICAL_EVIDENCE §5.1)."""

    def test_no_aki(self):
        result = evaluate_kdigo(
            creatinine_current=0.9,
            creatinine_baseline=0.9,
        )
        assert result.stage == 0
        assert not result.triggered

    def test_stage_1_ratio(self):
        """SCr 1.5x baseline => Stage 1."""
        result = evaluate_kdigo(
            creatinine_current=1.5,
            creatinine_baseline=1.0,
        )
        assert result.stage == 1
        assert result.triggered

    def test_stage_1_acute_rise(self):
        """SCr rise >= 0.3 in 48h => Stage 1."""
        result = evaluate_kdigo(
            creatinine_current=1.2,
            creatinine_48h_ago=0.9,
        )
        assert result.stage == 1
        assert result.triggered

    def test_stage_2_ratio(self):
        """SCr 2.0-2.9x baseline => Stage 2."""
        result = evaluate_kdigo(
            creatinine_current=2.0,
            creatinine_baseline=1.0,
        )
        assert result.stage == 2
        assert result.triggered

    def test_stage_3_ratio(self):
        """SCr >= 3.0x baseline => Stage 3."""
        result = evaluate_kdigo(
            creatinine_current=3.0,
            creatinine_baseline=1.0,
        )
        assert result.stage == 3

    def test_stage_3_absolute(self):
        """SCr >= 4.0 => Stage 3 regardless of baseline."""
        result = evaluate_kdigo(
            creatinine_current=4.2,
            creatinine_baseline=2.5,
        )
        assert result.stage == 3

    def test_stage_3_rrt(self):
        """RRT initiation => Stage 3."""
        result = evaluate_kdigo(on_rrt=True)
        assert result.stage == 3

    def test_stage_1_uo(self):
        """UO < 0.5 for 6-12h => Stage 1."""
        result = evaluate_kdigo(
            urine_output_ml_kg_h=0.4,
            oliguria_hours=8,
        )
        assert result.stage == 1

    def test_stage_2_uo(self):
        """UO < 0.5 for >= 12h => Stage 2."""
        result = evaluate_kdigo(
            urine_output_ml_kg_h=0.4,
            oliguria_hours=14,
        )
        assert result.stage == 2

    def test_stage_3_uo(self):
        """UO < 0.3 for >= 24h => Stage 3."""
        result = evaluate_kdigo(
            urine_output_ml_kg_h=0.2,
            oliguria_hours=24,
        )
        assert result.stage == 3

    def test_stage_3_anuria(self):
        """Anuria for >= 12h => Stage 3."""
        result = evaluate_kdigo(
            urine_output_ml_kg_h=0.0,
            oliguria_hours=12,
        )
        assert result.stage == 3

    def test_no_data(self):
        """No inputs => stage 0."""
        result = evaluate_kdigo()
        assert result.stage == 0
        assert not result.triggered

    def test_pt007_t4h_deteriorating(self):
        """PT-007 T+4h: creatinine 1.2, baseline 1.0 => ratio 1.2, no AKI."""
        result = evaluate_kdigo(
            creatinine_current=1.2,
            creatinine_baseline=1.0,
        )
        assert result.stage == 0  # 1.2x not >= 1.5x

    def test_pt009_t8h_sepsis_creatinine(self):
        """PT-009 T+8h: creatinine 1.9, baseline 0.9 => 2.1x => Stage 2."""
        result = evaluate_kdigo(
            creatinine_current=1.9,
            creatinine_baseline=0.9,
        )
        assert result.stage == 2
        assert result.triggered

    def test_higher_of_cr_and_uo_wins(self):
        """When both criteria suggest different stages, highest wins."""
        result = evaluate_kdigo(
            creatinine_current=1.5,
            creatinine_baseline=1.0,
            urine_output_ml_kg_h=0.4,
            oliguria_hours=14,
        )
        assert result.stage == 2  # UO stage 2 > Cr stage 1
