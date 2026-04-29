"""Unit tests for CMQCC postpartum hemorrhage staging.

Reference: CMQCC OB Hemorrhage Toolkit v3.0 (2022),
https://www.cmqcc.org/resources-tool-kits/toolkits/ob-hemorrhage-toolkit
ACOG Practice Bulletin 183 (2017), PubMed 28937571.
"""

from __future__ import annotations

from backend.criteria.pph import evaluate_pph


class TestPphStage0:
    def test_no_triggers_stage_0(self) -> None:
        """EBL <500, SI <0.9, fibrinogen ok → stage 0."""
        result = evaluate_pph(
            cumulative_ebl_ml=300.0,
            delivery_route="vaginal",
            hr=80,
            sbp=120,
            fibrinogen_mg_dl=350.0,
            uterotonics_given=1,
        )
        assert result.stage == 0
        assert not result.triggers
        # Action ladder is active management for stage 0.
        assert any(
            "active management" in a.lower() for a in result.recommended_actions
        )


class TestPphStage1:
    def test_vag_ebl_500_at_lower_bound(self) -> None:
        """Vaginal EBL exactly 500 mL → Stage 1."""
        result = evaluate_pph(
            cumulative_ebl_ml=500.0,
            delivery_route="vaginal",
            hr=90,
            sbp=110,
        )
        assert result.stage == 1
        # Triggers list must reference the threshold.
        assert any("500" in t and "Stage 1" in t for t in result.triggers)

    def test_cesarean_ebl_700_below_cs_threshold_stage_0(self) -> None:
        """Cesarean Stage 1 cutoff is 1000, not 500 — 700 mL after CS does
        NOT trigger Stage 1 by EBL alone."""
        result = evaluate_pph(
            cumulative_ebl_ml=700.0,
            delivery_route="cesarean",
            hr=80,
            sbp=120,
        )
        # No EBL trigger and SI < 0.9 → stage 0.
        assert result.stage == 0

    def test_shock_index_0_9_stage_1(self) -> None:
        """SI exactly 0.9 → Stage 1."""
        result = evaluate_pph(
            cumulative_ebl_ml=400.0,
            hr=99,
            sbp=110,
        )
        # 99/110 = 0.9
        assert result.shock_index == 0.9
        assert result.stage == 1


class TestPphStage2:
    def test_ebl_1000_to_1500_stage_2(self) -> None:
        """EBL 1200 vag → stage 2."""
        result = evaluate_pph(
            cumulative_ebl_ml=1200.0,
            delivery_route="vaginal",
            hr=110,
            sbp=110,
        )
        assert result.stage == 2

    def test_two_uterotonics_stage_2(self) -> None:
        """≥2 uterotonics → Stage 2 even if EBL borderline."""
        result = evaluate_pph(
            cumulative_ebl_ml=600.0,
            delivery_route="vaginal",
            hr=85,
            sbp=110,
            uterotonics_given=2,
        )
        assert result.stage == 2

    def test_si_1_0_stage_2(self) -> None:
        """SI in [1.0, 1.4) → Stage 2."""
        result = evaluate_pph(
            cumulative_ebl_ml=600.0,
            hr=110,
            sbp=110,
        )
        assert result.shock_index == 1.0
        assert result.stage == 2


class TestPphStage3:
    def test_ebl_1500_stage_3(self) -> None:
        """EBL ≥1500 → Stage 3 regardless of route."""
        result = evaluate_pph(
            cumulative_ebl_ml=1600.0,
            delivery_route="vaginal",
            hr=120,
            sbp=110,
        )
        assert result.stage == 3
        # Must offer the verbatim "massive transfusion" line.
        assert any(
            "massive transfusion" in a.lower()
            for a in result.recommended_actions
        )

    def test_si_1_4_stage_3(self) -> None:
        """SI ≥1.4 → Stage 3."""
        result = evaluate_pph(
            cumulative_ebl_ml=800.0,
            hr=140,
            sbp=100,
        )
        # 140/100 = 1.4 → triggers Stage 3 by SI
        assert result.stage == 3

    def test_pt010_demo_trajectory_stage_3(self) -> None:
        """PT-010 peak: EBL 2050, HR 132, SBP 82, fib 175 → Stage 3."""
        result = evaluate_pph(
            cumulative_ebl_ml=2050.0,
            delivery_route="vaginal",
            hr=132,
            sbp=82,
            fibrinogen_mg_dl=175.0,
        )
        assert result.stage == 3
        # All three Stage-3 triggers should fire.
        joined = " | ".join(result.triggers).lower()
        assert "ebl" in joined
        assert "shock index" in joined
        assert "fibrinogen" in joined

    def test_fibrinogen_below_200_stage_3(self) -> None:
        """Fibrinogen <200 → Stage 3 even with mild EBL/SI."""
        result = evaluate_pph(
            cumulative_ebl_ml=600.0,
            hr=95,
            sbp=110,
            fibrinogen_mg_dl=180.0,
        )
        assert result.stage == 3

    def test_clinical_instability_stage_3(self) -> None:
        """Bedside instability flag → Stage 3."""
        result = evaluate_pph(
            cumulative_ebl_ml=300.0,
            hr=80,
            sbp=120,
            clinical_instability=True,
        )
        assert result.stage == 3


class TestPphEblMissing:
    def test_no_ebl_caveat_present(self) -> None:
        """EBL=None → caveat about visual inflation is set."""
        result = evaluate_pph(
            cumulative_ebl_ml=None,
            hr=120,
            sbp=100,
        )
        assert result.ebl_caveat is not None
        assert "ACOG" in result.ebl_caveat
        # SI 1.2 → Stage 2 from SI alone.
        assert result.stage == 2

    def test_no_ebl_no_si_returns_stage_0(self) -> None:
        """No EBL and no HR/SBP → stage 0 + caveat."""
        result = evaluate_pph()
        assert result.stage == 0
        assert result.ebl_caveat is not None


class TestPphActionLadder:
    def test_actions_are_verbatim_for_stage(self) -> None:
        """The action lists must be the exact CMQCC strings — no LLM."""
        s0 = evaluate_pph(cumulative_ebl_ml=200, hr=80, sbp=120)
        s3 = evaluate_pph(cumulative_ebl_ml=2000, hr=130, sbp=85)
        assert s0.recommended_actions != s3.recommended_actions
        # Stage 3 must include MTP and tranexamic acid lines verbatim.
        assert any(
            "tranexamic" in a.lower() for a in s3.recommended_actions
        )
        assert any(
            "1:1:1" in a for a in s3.recommended_actions
        )
