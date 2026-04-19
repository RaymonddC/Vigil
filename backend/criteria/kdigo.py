"""KDIGO — Acute Kidney Injury staging by creatinine and urine output.

Source: KDIGO Acute Kidney Injury Work Group. "KDIGO Clinical Practice
Guideline for Acute Kidney Injury." Kidney International Supplements
2012;2(1):1-138. (CLINICAL_EVIDENCE §5.1)

AKI definition (any one of):
  - Increase in SCr >= 0.3 mg/dL within 48h
  - Increase in SCr >= 1.5x baseline within 7 days
  - Urine output < 0.5 mL/kg/h for >= 6 hours

Staging:
  Stage 1: SCr 1.5-1.9x baseline OR increase >= 0.3 mg/dL
            OR UO < 0.5 mL/kg/h for 6-12h
  Stage 2: SCr 2.0-2.9x baseline
            OR UO < 0.5 mL/kg/h for >= 12h
  Stage 3: SCr >= 3.0x baseline OR SCr >= 4.0 mg/dL OR initiation of RRT
            OR UO < 0.3 mL/kg/h for >= 24h OR anuria >= 12h
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class KdigoResult(BaseModel):
    """Result of KDIGO AKI staging."""

    stage: int = Field(ge=0, le=3, description="0 = no AKI, 1-3 = KDIGO stage")
    triggered: bool = Field(description="True when stage >= 1 (AKI detected)")
    criteria_met: list[str] = Field(default_factory=list)
    rationale: str = ""


def evaluate_kdigo(
    creatinine_current: float | None = None,
    creatinine_baseline: float | None = None,
    creatinine_48h_ago: float | None = None,
    urine_output_ml_kg_h: float | None = None,
    oliguria_hours: float | None = None,
    on_rrt: bool = False,
) -> KdigoResult:
    """Stage AKI using KDIGO criteria.

    Args:
        creatinine_current: Current serum creatinine in mg/dL. LOINC 2160-0.
        creatinine_baseline: Baseline SCr in mg/dL (pre-admission or 7-day prior).
        creatinine_48h_ago: SCr from 48 hours ago in mg/dL (for acute-rise criterion).
        urine_output_ml_kg_h: Average urine output in mL/kg/h.
        oliguria_hours: Duration of oliguria (UO < threshold) in hours.
        on_rrt: Whether renal replacement therapy has been initiated.

    Returns:
        KdigoResult with stage 0-3.
    """
    stage = 0
    criteria: list[str] = []

    # --- Creatinine-based staging ---
    if (
        creatinine_current is not None
        and creatinine_baseline is not None
        and creatinine_baseline > 0
    ):
        ratio = creatinine_current / creatinine_baseline

        if ratio >= 3.0 or creatinine_current >= 4.0:
            stage = max(stage, 3)
            criteria.append(
                f"SCr {creatinine_current:.1f} is {ratio:.1f}x baseline "
                f"{creatinine_baseline:.1f} (>=3.0x or >=4.0 mg/dL)"
            )
        elif ratio >= 2.0:
            stage = max(stage, 2)
            criteria.append(
                f"SCr {creatinine_current:.1f} is {ratio:.1f}x baseline "
                f"{creatinine_baseline:.1f} (2.0-2.9x)"
            )
        elif ratio >= 1.5:
            stage = max(stage, 1)
            criteria.append(
                f"SCr {creatinine_current:.1f} is {ratio:.1f}x baseline "
                f"{creatinine_baseline:.1f} (1.5-1.9x)"
            )

    # Acute rise >= 0.3 mg/dL within 48h
    if creatinine_current is not None and creatinine_48h_ago is not None:
        delta = round(creatinine_current - creatinine_48h_ago, 4)
        if delta >= 0.3:
            stage = max(stage, 1)
            criteria.append(
                f"SCr rise {delta:.1f} mg/dL in 48h (>= 0.3)"
            )

    # --- Urine-output-based staging ---
    if urine_output_ml_kg_h is not None and oliguria_hours is not None:
        if urine_output_ml_kg_h < 0.3 and oliguria_hours >= 24:
            stage = max(stage, 3)
            criteria.append(
                f"UO {urine_output_ml_kg_h:.2f} mL/kg/h < 0.3 for {oliguria_hours:.0f}h (>=24h)"
            )
        elif urine_output_ml_kg_h == 0 and oliguria_hours >= 12:
            stage = max(stage, 3)
            criteria.append(f"Anuria for {oliguria_hours:.0f}h (>=12h)")
        elif urine_output_ml_kg_h < 0.5 and oliguria_hours >= 12:
            stage = max(stage, 2)
            criteria.append(
                f"UO {urine_output_ml_kg_h:.2f} mL/kg/h < 0.5 for {oliguria_hours:.0f}h (>=12h)"
            )
        elif urine_output_ml_kg_h < 0.5 and oliguria_hours >= 6:
            stage = max(stage, 1)
            criteria.append(
                f"UO {urine_output_ml_kg_h:.2f} mL/kg/h < 0.5 for {oliguria_hours:.0f}h (>=6h)"
            )

    # --- RRT ---
    if on_rrt:
        stage = max(stage, 3)
        criteria.append("Renal replacement therapy initiated")

    triggered = stage >= 1
    if not criteria:
        rationale = "No KDIGO AKI criteria met."
    else:
        rationale = f"KDIGO Stage {stage}; " + "; ".join(criteria)

    return KdigoResult(
        stage=stage,
        triggered=triggered,
        criteria_met=criteria,
        rationale=rationale,
    )
