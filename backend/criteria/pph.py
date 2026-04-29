"""PPH — Postpartum hemorrhage staging (CMQCC OB Hemorrhage Toolkit v3.0).

Deterministic staging engine for postpartum hemorrhage. The 0–3 stages
match the California Maternal Quality Care Collaborative (CMQCC) OB
Hemorrhage Toolkit v3.0 readiness/recognition/response framework.

Sources:
- CMQCC OB Hemorrhage Toolkit v3.0 (2022).
  URL: https://www.cmqcc.org/resources-tool-kits/toolkits/ob-hemorrhage-toolkit
- ACOG Practice Bulletin No. 183: *Postpartum Hemorrhage*. Obstetrics &
  Gynecology, 130(4):e168–e186 (October 2017). PubMed 28937571.
  URL: https://www.acog.org/clinical/clinical-guidance/practice-bulletin/articles/2017/10/postpartum-hemorrhage
- ACOG Committee Opinion 794: *Quantitative Blood Loss in Obstetric
  Hemorrhage* (Dec 2019). Visual EBL inflates ~30% — we surface a caveat
  when EBL is missing and we degrade to shock-index-only.

Stage thresholds (CMQCC v3.0):
  Stage 0 (no PPH yet):    EBL <500 mL vag / <1000 mL CS, SI <0.9.
  Stage 1 (initial PPH):   EBL 500–1000 mL vag / 1000–1500 CS, OR SI ≥0.9.
  Stage 2 (continued PPH): EBL 1000–1500 mL, OR ≥2 uterotonics given,
                           OR SI ≥1.0.
  Stage 3 (severe PPH):    EBL ≥1500 mL, OR SI ≥1.4, OR fibrinogen
                           <200 mg/dL, OR clinical instability.

Shock index = HR / SBP. Lab cutoff for fibrinogen reflects the
acquired-coagulopathy-of-PPH literature embedded in CMQCC v3.0.

Recommended actions are returned VERBATIM from CMQCC — do NOT have an
LLM rewrite them. The canonical wording is what clinicians expect.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PphResult(BaseModel):
    """Result of CMQCC postpartum hemorrhage staging."""

    stage: int = Field(ge=0, le=3)
    triggers: list[str]
    shock_index: float | None
    recommended_actions: list[str]
    ebl_caveat: str | None = Field(
        default=None,
        description=(
            "Set when EBL is unmeasured and staging degraded to "
            "shock-index-only per ACOG CO 794."
        ),
    )
    rationale: str = ""


# ---------------------------------------------------------------------------
# CMQCC stage-action ladder — verbatim, NOT generated.
# Source: CMQCC OB Hemorrhage Toolkit v3.0, Obstetric Hemorrhage Care
# Guidelines: Checklist Format Tables 1–4. URLs in module docstring.
# ---------------------------------------------------------------------------

_STAGE_0_ACTIONS: list[str] = [
    "Active management of third stage of labor (oxytocin, fundal massage)",
    "Quantitative blood loss measurement (gravimetric + graduated)",
    "Continue routine vital-sign monitoring",
]

_STAGE_1_ACTIONS: list[str] = [
    "Increase IV access (2 large-bore IVs); LR/NS bolus",
    "Administer second uterotonic (methergine OR misoprostol OR carboprost)",
    "Type and crossmatch 2 units PRBCs",
    "Frequent vital-sign + EBL reassessment (q 5–15 min)",
    "Notify charge nurse, OB attending, and anesthesia",
]

_STAGE_2_ACTIONS: list[str] = [
    "Mobilize team — OB, anesthesia, blood bank, OR/IR on standby",
    "Transfuse 2 units PRBCs empirically; consider FFP 1:1 ratio",
    "Continue uterotonic ladder (carboprost / misoprostol if not given)",
    "Prepare intrauterine balloon tamponade (Bakri) or B-Lynch if surgical",
    "Send STAT CBC, fibrinogen, PT/INR, ABG with lactate",
]

_STAGE_3_ACTIONS: list[str] = [
    "Activate massive transfusion protocol (1:1:1 PRBC:FFP:platelets)",
    "Mobilize OR/IR for surgical/embolization control",
    "Consider tranexamic acid 1 g IV (within 3 h of onset)",
    "Replace fibrinogen if <200 mg/dL (cryoprecipitate or fibrinogen concentrate)",
    "Consider hysterectomy if bleeding refractory; involve critical care",
]


def _actions_for_stage(stage: int) -> list[str]:
    """Return the verbatim CMQCC action ladder for the resolved stage."""
    if stage == 0:
        return list(_STAGE_0_ACTIONS)
    if stage == 1:
        return list(_STAGE_1_ACTIONS)
    if stage == 2:
        return list(_STAGE_2_ACTIONS)
    return list(_STAGE_3_ACTIONS)


# ---------------------------------------------------------------------------
# Stage thresholds — kept as private constants so a reviewer can check
# the numbers against CMQCC v3.0 Table 1 in one glance.
# ---------------------------------------------------------------------------

_EBL_STAGE1_VAG = 500
_EBL_STAGE1_CS = 1000
_EBL_STAGE2_MIN = 1000
_EBL_STAGE3_MIN = 1500

_SI_STAGE1 = 0.9
_SI_STAGE2 = 1.0
_SI_STAGE3 = 1.4

_FIBRINOGEN_STAGE3 = 200.0  # mg/dL


def _shock_index(hr: float | None, sbp: float | None) -> float | None:
    if hr is None or sbp is None or sbp <= 0:
        return None
    return round(hr / sbp, 2)


def evaluate_pph(
    cumulative_ebl_ml: float | None = None,
    delivery_route: Literal["vaginal", "cesarean", "unknown"] = "vaginal",
    hr: float | None = None,
    sbp: float | None = None,
    fibrinogen_mg_dl: float | None = None,
    uterotonics_given: int = 0,
    clinical_instability: bool = False,
) -> PphResult:
    """Stage postpartum hemorrhage per CMQCC OB Hemorrhage Toolkit v3.0.

    Args:
        cumulative_ebl_ml: Cumulative quantitative blood loss in mL.
            ACOG QBL preferred; visual EBL inflates ~30% (ACOG CO 794).
            ``None`` → degrade to shock-index-only with caveat.
        delivery_route: Vaginal vs cesarean — adjusts Stage-1 EBL cutoff.
        hr: Heart rate (/min).
        sbp: Systolic BP (mmHg).
        fibrinogen_mg_dl: Plasma fibrinogen (LOINC 3255-7).
        uterotonics_given: Count of uterotonic agents administered.
        clinical_instability: True iff bedside team has called instability
            (e.g. dropping mental status, persistent bleeding despite
            initial ladder). Vigil never auto-detects this — it must be
            explicitly passed in.

    Returns:
        PphResult with stage 0–3 and the verbatim CMQCC action list.
    """
    triggers: list[str] = []
    stage = 0

    si = _shock_index(hr, sbp)

    # --- Stage 3 evaluation (highest stage wins) ---
    if cumulative_ebl_ml is not None and cumulative_ebl_ml >= _EBL_STAGE3_MIN:
        stage = max(stage, 3)
        triggers.append(
            f"EBL {cumulative_ebl_ml:.0f} mL ≥{_EBL_STAGE3_MIN} (Stage 3)"
        )
    if si is not None and si >= _SI_STAGE3:
        stage = max(stage, 3)
        triggers.append(f"Shock index {si:.2f} ≥{_SI_STAGE3} (Stage 3)")
    if (
        fibrinogen_mg_dl is not None
        and fibrinogen_mg_dl < _FIBRINOGEN_STAGE3
    ):
        stage = max(stage, 3)
        triggers.append(
            f"Fibrinogen {fibrinogen_mg_dl:.0f} mg/dL <{int(_FIBRINOGEN_STAGE3)} (Stage 3)"
        )
    if clinical_instability:
        stage = max(stage, 3)
        triggers.append("Clinical instability (Stage 3)")

    # --- Stage 2 evaluation ---
    if (
        cumulative_ebl_ml is not None
        and cumulative_ebl_ml >= _EBL_STAGE2_MIN
        and cumulative_ebl_ml < _EBL_STAGE3_MIN
    ):
        stage = max(stage, 2)
        triggers.append(
            f"EBL {cumulative_ebl_ml:.0f} mL "
            f"in {_EBL_STAGE2_MIN}–{_EBL_STAGE3_MIN - 1} (Stage 2)"
        )
    if si is not None and _SI_STAGE2 <= si < _SI_STAGE3:
        stage = max(stage, 2)
        triggers.append(f"Shock index {si:.2f} ≥{_SI_STAGE2} (Stage 2)")
    if uterotonics_given >= 2 and stage < 3:
        stage = max(stage, 2)
        triggers.append(
            f"≥2 uterotonics given ({uterotonics_given}) (Stage 2)"
        )

    # --- Stage 1 evaluation ---
    stage1_ebl_cutoff = (
        _EBL_STAGE1_CS if delivery_route == "cesarean" else _EBL_STAGE1_VAG
    )
    stage1_ebl_upper = _EBL_STAGE2_MIN
    if (
        cumulative_ebl_ml is not None
        and stage1_ebl_cutoff <= cumulative_ebl_ml < stage1_ebl_upper
    ):
        stage = max(stage, 1)
        triggers.append(
            f"EBL {cumulative_ebl_ml:.0f} mL "
            f"≥{stage1_ebl_cutoff} ({delivery_route}) (Stage 1)"
        )
    if si is not None and _SI_STAGE1 <= si < _SI_STAGE2:
        stage = max(stage, 1)
        triggers.append(f"Shock index {si:.2f} ≥{_SI_STAGE1} (Stage 1)")

    # --- EBL-missing caveat ---
    ebl_caveat: str | None = None
    if cumulative_ebl_ml is None:
        ebl_caveat = (
            "EBL unmeasured — staging from shock index only. Visual EBL "
            "inflates ~30% (ACOG Committee Opinion 794); request "
            "quantitative blood loss measurement (gravimetric + "
            "graduated collection)."
        )

    actions = _actions_for_stage(stage)

    rationale_parts: list[str] = [f"CMQCC Stage {stage}"]
    if triggers:
        rationale_parts.append("; ".join(triggers))
    elif stage == 0:
        rationale_parts.append("no PPH triggers met")
    rationale = ". ".join(rationale_parts)

    return PphResult(
        stage=stage,
        triggers=triggers,
        shock_index=si,
        recommended_actions=actions,
        ebl_caveat=ebl_caveat,
        rationale=rationale,
    )
