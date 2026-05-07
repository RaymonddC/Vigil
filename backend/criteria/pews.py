"""PEWS — Paediatric Early Warning Score (age-banded).

Brighton/Cardiff PEWS variant: each of HR, RR, SpO2 contributes 0-3
points based on age-band-specific normal ranges. Aggregate ≥3 (or any
single parameter ≥3) triggers an urgent paediatric review.

Sources:
- Monaghan A. *Detecting and managing deterioration in children.*
  Paediatric Nursing 2005;17(1):32-35.
  https://journals.rcni.com/paediatric-care/detecting-and-managing-deterioration-in-children-pn2005.02.17.1.32.c511
- Roland D, Oliver A, Edwards ED, et al. *Use of paediatric early
  warning systems in Great Britain.* Arch Dis Child 2014;99:26-29.
  https://adc.bmj.com/content/99/1/26
- RCPCH Paediatric Early Warning System (PEWS) — National launch 2023.
  https://www.rcpch.ac.uk/work-we-do/quality-improvement-patient-safety/system-wide-deterioration-pews

Vigil uses a simplified 4-band age stratification. Production
deployment would extend to NHS England's national PEWS chart when it
finalises age groupings (currently in roll-out per RCPCH 2023).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _AgeBand:
    """Age-banded normal ranges (lower/upper) per vital."""
    label: str
    age_min_yr: float
    age_max_yr: float
    hr_low: int
    hr_high: int
    rr_low: int
    rr_high: int
    spo2_low: int  # below this scores >=1


# Age bands — values are mid-range normal cutoffs from RCPCH 2023 PEWS
# chart and Monaghan 2005. A value in [low, high] scores 0; outside by
# 10% scores 1; outside by 25% scores 2; outside by 40%+ scores 3.
_BANDS: list[_AgeBand] = [
    # Infant <1y
    _AgeBand("infant", 0.0, 1.0, hr_low=110, hr_high=160, rr_low=30, rr_high=60, spo2_low=95),
    # Toddler 1-4y
    _AgeBand("toddler", 1.0, 5.0, hr_low=90, hr_high=140, rr_low=20, rr_high=40, spo2_low=95),
    # School-age 5-11y
    _AgeBand("school_age", 5.0, 12.0, hr_low=70, hr_high=120, rr_low=18, rr_high=30, spo2_low=95),
    # Adolescent 12-17y (PEWS upper bound; 18+ uses adult MEWT)
    _AgeBand("adolescent", 12.0, 18.0, hr_low=60, hr_high=110, rr_low=12, rr_high=20, spo2_low=95),
]


def _band_for_age(age_years: float) -> _AgeBand | None:
    for b in _BANDS:
        if b.age_min_yr <= age_years < b.age_max_yr:
            return b
    return None


def _score_one_value(
    value: float,
    low: int,
    high: int,
    is_low_concerning: bool = True,
    is_high_concerning: bool = True,
) -> int:
    """Score 0-3 based on how far value is from the [low, high] band.

    Mirrors the ordinal grading used in published PEWS variants: a
    deviation of 10-25% scores 1, 25-40% scores 2, >40% scores 3. The
    direction-of-concerning args let SpO2 (low-concerning only) reuse
    the same primitive as HR/RR (both directions concerning).
    """
    if low <= value <= high:
        return 0
    if value < low and is_low_concerning:
        deviation = (low - value) / low if low > 0 else 0
    elif value > high and is_high_concerning:
        deviation = (value - high) / high if high > 0 else 0
    else:
        return 0
    if deviation < 0.10:
        return 0
    if deviation < 0.25:
        return 1
    if deviation < 0.40:
        return 2
    return 3


@dataclass
class PewsResult:
    age_years: float
    age_band: str
    hr_score: int
    rr_score: int
    spo2_score: int
    aggregate: int
    red_flag: bool          # any single parameter ≥3
    triggered: bool         # aggregate ≥3 OR red flag
    rationale: str


def evaluate_pews(
    age_years: float,
    hr: float | None = None,
    rr: float | None = None,
    spo2: float | None = None,
) -> PewsResult:
    """Score PEWS for a paediatric patient.

    Returns a PewsResult with per-parameter scores, aggregate, and a
    triggered flag (aggregate ≥3 OR any single parameter scoring 3).
    Missing parameters score 0 — deliberately conservative; a real
    deployment would refuse to score with insufficient inputs.
    """
    band = _band_for_age(age_years)
    if band is None:
        return PewsResult(
            age_years=age_years,
            age_band="out_of_range",
            hr_score=0, rr_score=0, spo2_score=0,
            aggregate=0, red_flag=False, triggered=False,
            rationale=(
                f"Age {age_years:.1f}y outside PEWS range (0-18y). "
                "Use adult MEWT/NEWS2 instead."
            ),
        )

    hr_s = _score_one_value(hr, band.hr_low, band.hr_high) if hr is not None else 0
    rr_s = _score_one_value(rr, band.rr_low, band.rr_high) if rr is not None else 0
    spo2_s = (
        _score_one_value(
            spo2, band.spo2_low, 100,
            is_low_concerning=True, is_high_concerning=False,
        )
        if spo2 is not None else 0
    )

    agg = hr_s + rr_s + spo2_s
    red = max(hr_s, rr_s, spo2_s) >= 3
    triggered = agg >= 3 or red

    rationale_parts: list[str] = [
        f"PEWS band: {band.label} ({band.age_min_yr:.0f}-{band.age_max_yr:.0f}y).",
    ]
    if hr is not None:
        rationale_parts.append(
            f"HR {hr:.0f} (normal {band.hr_low}-{band.hr_high}) → {hr_s}"
        )
    if rr is not None:
        rationale_parts.append(
            f"RR {rr:.0f} (normal {band.rr_low}-{band.rr_high}) → {rr_s}"
        )
    if spo2 is not None:
        rationale_parts.append(
            f"SpO2 {spo2:.0f}% (≥{band.spo2_low}) → {spo2_s}"
        )

    return PewsResult(
        age_years=age_years,
        age_band=band.label,
        hr_score=hr_s,
        rr_score=rr_s,
        spo2_score=spo2_s,
        aggregate=agg,
        red_flag=red,
        triggered=triggered,
        rationale=" ".join(rationale_parts),
    )
