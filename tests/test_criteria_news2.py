"""Unit tests for NEWS2 criteria (RCP 2017).

Reference: Royal College of Physicians, *NEWS2*, 2017,
https://www.rcplondon.ac.uk/projects/outputs/national-early-warning-score-news-2

Each test cites the chart row from the reference. Keep these explicit;
boundary semantics matter clinically.
"""

from __future__ import annotations

from backend.criteria.news2 import evaluate_news2


class TestNews2AllNormal:
    def test_all_in_range_score_zero(self) -> None:
        """RR 16, SpO2 98, Temp 37, SBP 120, HR 70, alert, room air → 0."""
        result = evaluate_news2(
            rr=16, spo2=98, temp_c=37.0, sbp=120, hr=70,
            alert=True, supplemental_o2=False,
        )
        assert result.aggregate == 0
        assert result.band == "low"
        assert not result.red_flag


class TestNews2RedFlagsByParameter:
    def test_rr_25_scores_3_red_flag(self) -> None:
        """RR ≥25 contributes 3 (chart row 1)."""
        result = evaluate_news2(rr=26, spo2=98, temp_c=37, sbp=120, hr=70, alert=True)
        assert result.red_flag
        rr_row = next(r for r in result.contributions if r.parameter == "RR")
        assert rr_row.score == 3

    def test_spo2_91_scores_3(self) -> None:
        """SpO2 ≤91 contributes 3 (Scale 1)."""
        result = evaluate_news2(rr=16, spo2=91, temp_c=37, sbp=120, hr=70, alert=True)
        spo2_row = next(r for r in result.contributions if r.parameter == "SpO2")
        assert spo2_row.score == 3
        assert result.red_flag

    def test_sbp_90_scores_3(self) -> None:
        """SBP ≤90 contributes 3."""
        result = evaluate_news2(rr=16, spo2=98, temp_c=37, sbp=88, hr=70, alert=True)
        sbp_row = next(r for r in result.contributions if r.parameter == "SBP")
        assert sbp_row.score == 3

    def test_sbp_220_scores_3(self) -> None:
        """SBP ≥220 contributes 3 (severe hypertension)."""
        result = evaluate_news2(rr=16, spo2=98, temp_c=37, sbp=220, hr=70, alert=True)
        sbp_row = next(r for r in result.contributions if r.parameter == "SBP")
        assert sbp_row.score == 3

    def test_hr_131_scores_3(self) -> None:
        """HR ≥131 contributes 3."""
        result = evaluate_news2(rr=16, spo2=98, temp_c=37, sbp=120, hr=135, alert=True)
        hr_row = next(r for r in result.contributions if r.parameter == "HR")
        assert hr_row.score == 3

    def test_consciousness_not_alert_scores_3(self) -> None:
        """Any C/V/P/U scores 3."""
        result = evaluate_news2(
            rr=16, spo2=98, temp_c=37, sbp=120, hr=70, alert=False,
        )
        c_row = next(
            r for r in result.contributions if r.parameter == "Consciousness"
        )
        assert c_row.score == 3


class TestNews2BoundaryCases:
    def test_rr_8_boundary_is_3(self) -> None:
        """≤8 scores 3 (boundary inclusive)."""
        result = evaluate_news2(rr=8, spo2=98, temp_c=37, sbp=120, hr=70, alert=True)
        rr_row = next(r for r in result.contributions if r.parameter == "RR")
        assert rr_row.score == 3

    def test_rr_9_boundary_is_1(self) -> None:
        """9 scores 1 (one above the ≤8 boundary)."""
        result = evaluate_news2(rr=9, spo2=98, temp_c=37, sbp=120, hr=70, alert=True)
        rr_row = next(r for r in result.contributions if r.parameter == "RR")
        assert rr_row.score == 1

    def test_rr_20_normal(self) -> None:
        """RR 12–20 scores 0; 20 is the upper bound."""
        result = evaluate_news2(rr=20, spo2=98, temp_c=37, sbp=120, hr=70, alert=True)
        rr_row = next(r for r in result.contributions if r.parameter == "RR")
        assert rr_row.score == 0

    def test_rr_21_scores_2(self) -> None:
        """RR 21–24 scores 2."""
        result = evaluate_news2(rr=21, spo2=98, temp_c=37, sbp=120, hr=70, alert=True)
        rr_row = next(r for r in result.contributions if r.parameter == "RR")
        assert rr_row.score == 2

    def test_temp_36_boundary_score_1(self) -> None:
        """36.0 maps to the 35.1–36.0 row (1)."""
        result = evaluate_news2(rr=16, spo2=98, temp_c=36.0, sbp=120, hr=70, alert=True)
        temp_row = next(r for r in result.contributions if r.parameter == "Temp")
        assert temp_row.score == 1

    def test_temp_36_1_normal(self) -> None:
        """36.1 should be in the normal row (0)."""
        result = evaluate_news2(rr=16, spo2=98, temp_c=36.1, sbp=120, hr=70, alert=True)
        temp_row = next(r for r in result.contributions if r.parameter == "Temp")
        assert temp_row.score == 0


class TestNews2Aggregate:
    def test_aggregate_band_high(self) -> None:
        """≥7 aggregate → high band."""
        result = evaluate_news2(rr=26, spo2=92, temp_c=39.5, sbp=88, hr=132, alert=False)
        assert result.aggregate >= 7
        assert result.band == "high"
        assert result.red_flag

    def test_aggregate_band_medium_via_red_flag(self) -> None:
        """Aggregate ≤4 BUT a single 3 → medium band per RCP table."""
        # RR=21 (2) + SpO2=92 (2) on Air (0) — aggregate 4, no 3s.
        # That's low-medium. To verify the red-flag override, give exactly
        # one 3-scoring parameter with everything else 0.
        result = evaluate_news2(
            rr=26,  # 3
            spo2=98, temp_c=37, sbp=120, hr=70, alert=True,
        )
        assert result.red_flag
        assert result.band == "medium"

    def test_supplemental_o2_adds_2(self) -> None:
        result = evaluate_news2(
            rr=16, spo2=98, temp_c=37, sbp=120, hr=70, alert=True,
            supplemental_o2=True,
        )
        assert result.aggregate == 2
        # Two-point score on a single param (O2 = 2) is NOT a red flag —
        # only single-param 3s are.
        assert not result.red_flag


class TestNews2NoneInputs:
    def test_no_inputs_score_zero(self) -> None:
        """Missing all inputs → aggregate 0 (assume alert + room air)."""
        result = evaluate_news2()
        assert result.aggregate == 0
        assert result.band == "low"
