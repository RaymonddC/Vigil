"""SIRS — Systemic Inflammatory Response Syndrome (2-of-4 fallback).

Deterministic rule engine for SIRS criteria, used as a fallback when lab data
is too sparse for CDC ASE screening.

Source: American College of Chest Physicians/Society of Critical Care Medicine
Consensus Conference, 1992. Bone RC et al. "Definitions for sepsis and organ
failure." Chest 1992;101(6):1644-1655.

Also referenced in Sepsis-3 (Singer 2016) as the predecessor definition that
qSOFA aims to replace at bedside.

Criteria (any 2 of 4 = SIRS positive):
  1. Temperature > 38 C or < 36 C        (LOINC 8310-5)
  2. Heart rate > 90 /min                 (LOINC 8867-4)
  3. Respiratory rate > 20 /min           (LOINC 9279-1)
  4. WBC > 12,000 or < 4,000 /uL         (LOINC 6690-2)
     OR > 10% immature band forms
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SirsResult(BaseModel):
    """Result of SIRS screening."""

    score: int = Field(ge=0, le=4)
    triggered: bool = Field(description="True when score >= 2 (SIRS positive)")
    components: dict[str, bool] = Field(
        description="Individual criterion results"
    )
    rationale: str = ""


def evaluate_sirs(
    temp: float | None = None,
    hr: float | None = None,
    rr: float | None = None,
    wbc: float | None = None,
    band_pct: float | None = None,
) -> SirsResult:
    """Compute SIRS score from vital and lab values.

    Args:
        temp: Body temperature in Celsius. LOINC 8310-5.
        hr: Heart rate in beats/min. LOINC 8867-4.
        rr: Respiratory rate in breaths/min. LOINC 9279-1.
        wbc: WBC count in 10^3/uL. LOINC 6690-2.
        band_pct: Percentage of immature band forms. Optional.

    Returns:
        SirsResult with score 0-4, triggered if >= 2.
    """
    # Temp > 38 C or < 36 C (Bone 1992)
    temp_abnormal = temp is not None and (temp > 38 or temp < 36)

    # HR > 90 /min (Bone 1992)
    hr_elevated = hr is not None and hr > 90

    # RR > 20 /min (Bone 1992)
    rr_elevated = rr is not None and rr > 20

    # WBC > 12 or < 4 (10^3/uL), or bands > 10% (Bone 1992)
    wbc_abnormal = False
    if wbc is not None:
        wbc_abnormal = wbc > 12 or wbc < 4
    if not wbc_abnormal and band_pct is not None:
        wbc_abnormal = band_pct > 10

    components = {
        "temp_abnormal": temp_abnormal,
        "hr_gt_90": hr_elevated,
        "rr_gt_20": rr_elevated,
        "wbc_abnormal": wbc_abnormal,
    }

    score = sum(components.values())
    triggered = score >= 2

    parts: list[str] = []
    if temp_abnormal:
        parts.append(f"Temp {temp} C (>38 or <36)")
    if hr_elevated:
        parts.append(f"HR {hr} > 90")
    if rr_elevated:
        parts.append(f"RR {rr} > 20")
    if wbc_abnormal:
        if wbc is not None and (wbc > 12 or wbc < 4):
            parts.append(f"WBC {wbc} (>12 or <4)")
        elif band_pct is not None:
            parts.append(f"Bands {band_pct}% > 10%")
    if not parts:
        parts.append("No SIRS criteria met")

    rationale = f"SIRS={score}/4; " + "; ".join(parts)

    return SirsResult(
        score=score,
        triggered=triggered,
        components=components,
        rationale=rationale,
    )
