"""MEWT — Modified Early Warning Trigger screening.

Deterministic rule engine that evaluates vital signs against MEWT thresholds
and a hemodynamic trend rule.

Thresholds sourced from:
- Shields LE et al. "Use of Maternal Early Warning Trigger tool reduces maternal
  morbidity." AJOG 2016;214(4):527.e1-527.e6 (CLINICAL_EVIDENCE §2.2)
- Singer M et al. "Sepsis-3." JAMA 2016;315(8):801-810 (CLINICAL_EVIDENCE §3.1)
- Subbe CP et al. "Validation of a modified Early Warning Score." QJM 2001 (§2.1)
- KDIGO AKI Work Group. Kidney Int Suppl 2012 (CLINICAL_EVIDENCE §5.1)

Hemodynamic trend rule (Vigil operational, CLINICAL_EVIDENCE §2.3):
  If SBP drops >=10% AND HR rises >=15% over any 2h window -> TRIGGERED
  regardless of absolute threshold crossings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Threshold tables
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Threshold:
    loinc: str
    label: str
    unit: str
    red_low: float | None  # severe low bound (< fires red)
    red_high: float | None  # severe high bound (> fires red)
    yellow_low: float | None  # non-severe low (< fires yellow)
    yellow_high: float | None  # non-severe high (> fires yellow)


# Postop MEWT thresholds — CLINICAL_EVIDENCE §2.3 table
POSTOP_THRESHOLDS: list[_Threshold] = [
    # SBP: <90 red, <100 yellow  (Singer 2016 qSOFA + Subbe 2001)
    _Threshold(
        "8480-6", "SBP", "mm[Hg]",
        red_low=90, red_high=None, yellow_low=100, yellow_high=None,
    ),
    # HR: >130 red (Shields 2016), >110 yellow
    _Threshold(
        "8867-4", "HR", "/min",
        red_low=None, red_high=130, yellow_low=None, yellow_high=110,
    ),
    # RR: >30 red (severe), >=22 yellow (qSOFA, Singer 2016)
    _Threshold("9279-1", "RR", "/min", red_low=None, red_high=30, yellow_low=None, yellow_high=22),
    # SpO2: <90 red (severe), <93 yellow (Shields 2016 MEWT)
    _Threshold("59408-5", "SpO2", "%", red_low=90, red_high=None, yellow_low=93, yellow_high=None),
    # Temp: >39.5 or <35 red, >38 or <36 yellow (CDC ASE / Sepsis-3)
    _Threshold("8310-5", "Temp", "Cel", red_low=35, red_high=39.5, yellow_low=36, yellow_high=38),
]

# Postpartum thresholds — HTN-tuned cutoffs for preeclampsia screening
POSTPARTUM_THRESHOLDS: list[_Threshold] = [
    _Threshold("8480-6", "SBP", "mm[Hg]", red_low=85, red_high=160, yellow_low=90, yellow_high=155),
    _Threshold("8462-4", "DBP", "mm[Hg]", red_low=45, red_high=110, yellow_low=50, yellow_high=105),
    _Threshold(
        "8867-4", "HR", "/min",
        red_low=None, red_high=130, yellow_low=None, yellow_high=110,
    ),
    _Threshold("9279-1", "RR", "/min", red_low=None, red_high=30, yellow_low=None, yellow_high=22),
    _Threshold("59408-5", "SpO2", "%", red_low=90, red_high=None, yellow_low=93, yellow_high=None),
    _Threshold("8310-5", "Temp", "Cel", red_low=35, red_high=39.5, yellow_low=36, yellow_high=38),
]


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class VitalBreach(BaseModel):
    """One vital that violated a MEWT threshold."""

    loinc: str
    label: str
    value: float
    unit: str
    threshold: str
    severity: Literal["yellow", "red"]
    observed_at: datetime


class MewtResult(BaseModel):
    """Result of MEWT screening."""

    score: int = Field(ge=0, description="Count of breached parameters")
    triggered: bool
    breaches: list[VitalBreach] = Field(default_factory=list)
    rationale: str = ""


# ---------------------------------------------------------------------------
# Vital reading type
# ---------------------------------------------------------------------------

@dataclass
class VitalReading:
    """A single vital sign observation."""

    loinc: str
    value: float
    unit: str
    timestamp: datetime


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

def _check_threshold(
    reading: VitalReading,
    threshold: _Threshold,
) -> VitalBreach | None:
    """Check a single reading against a threshold. Returns a breach or None."""
    val = reading.value

    # Red (severe) checks
    if threshold.red_low is not None and val < threshold.red_low:
        return VitalBreach(
            loinc=reading.loinc, label=threshold.label, value=val,
            unit=threshold.unit, threshold=f"<{threshold.red_low}",
            severity="red", observed_at=reading.timestamp,
        )
    if threshold.red_high is not None and val > threshold.red_high:
        return VitalBreach(
            loinc=reading.loinc, label=threshold.label, value=val,
            unit=threshold.unit, threshold=f">{threshold.red_high}",
            severity="red", observed_at=reading.timestamp,
        )

    # Yellow (non-severe) checks
    if threshold.yellow_low is not None and val < threshold.yellow_low:
        return VitalBreach(
            loinc=reading.loinc, label=threshold.label, value=val,
            unit=threshold.unit, threshold=f"<{threshold.yellow_low}",
            severity="yellow", observed_at=reading.timestamp,
        )
    if threshold.yellow_high is not None and val >= threshold.yellow_high:
        return VitalBreach(
            loinc=reading.loinc, label=threshold.label, value=val,
            unit=threshold.unit, threshold=f">{threshold.yellow_high}",
            severity="yellow", observed_at=reading.timestamp,
        )

    return None


def _check_hemodynamic_trend(
    vitals: list[VitalReading],
    window: timedelta = timedelta(hours=2),
) -> VitalBreach | None:
    """Hemodynamic trend rule (CLINICAL_EVIDENCE §2.3, Vigil operational).

    If SBP drops >=10% AND HR rises >=15% over any 2-hour window,
    return a synthetic breach. Thresholds are Vigil operational choices
    (not externally validated).
    """
    sbp_readings = sorted(
        [v for v in vitals if v.loinc == "8480-6"], key=lambda v: v.timestamp
    )
    hr_readings = sorted(
        [v for v in vitals if v.loinc == "8867-4"], key=lambda v: v.timestamp
    )

    if len(sbp_readings) < 2 or len(hr_readings) < 2:
        return None

    for i, sbp_early in enumerate(sbp_readings):
        for sbp_late in sbp_readings[i + 1 :]:
            dt = sbp_late.timestamp - sbp_early.timestamp
            if dt < timedelta(0) or dt > window:
                continue
            if sbp_early.value == 0:
                continue

            sbp_drop_pct = (sbp_early.value - sbp_late.value) / sbp_early.value * 100

            if sbp_drop_pct < 10:
                continue

            # Find HR pair in the same time window
            for j, hr_early in enumerate(hr_readings):
                for hr_late in hr_readings[j + 1 :]:
                    hr_dt = hr_late.timestamp - hr_early.timestamp
                    if hr_dt < timedelta(0) or hr_dt > window:
                        continue
                    if hr_early.value == 0:
                        continue

                    hr_rise_pct = (
                        (hr_late.value - hr_early.value) / hr_early.value * 100
                    )

                    if hr_rise_pct >= 15:
                        return VitalBreach(
                            loinc="TREND",
                            label="Hemodynamic Trend",
                            value=0,
                            unit="",
                            threshold=(
                                f"SBP -{sbp_drop_pct:.1f}% AND "
                                f"HR +{hr_rise_pct:.1f}% over "
                                f"{dt.total_seconds() / 3600:.1f}h"
                            ),
                            severity="red",
                            observed_at=sbp_late.timestamp,
                        )
    return None


def evaluate_mewt(
    vitals: list[VitalReading],
    trajectory: Literal["postop", "postpartum"] = "postop",
) -> MewtResult:
    """Run MEWT screening on a set of vital readings.

    Args:
        vitals: List of vital sign observations to evaluate.
        trajectory: Which threshold table to use.

    Returns:
        MewtResult with score, triggered flag, breaches, and rationale.
    """
    thresholds = POSTOP_THRESHOLDS if trajectory == "postop" else POSTPARTUM_THRESHOLDS
    threshold_map = {t.loinc: t for t in thresholds}

    breaches: list[VitalBreach] = []

    # Check each vital reading against absolute thresholds.
    # Keep the worst (highest-severity) breach per LOINC code.
    worst_by_loinc: dict[str, VitalBreach] = {}
    for reading in vitals:
        th = threshold_map.get(reading.loinc)
        if th is None:
            continue
        breach = _check_threshold(reading, th)
        if breach is not None:
            existing = worst_by_loinc.get(reading.loinc)
            if existing is None or (
                breach.severity == "red" and existing.severity == "yellow"
            ):
                worst_by_loinc[reading.loinc] = breach

    breaches = list(worst_by_loinc.values())

    # Hemodynamic trend rule
    trend_breach = _check_hemodynamic_trend(vitals)
    if trend_breach is not None:
        breaches.append(trend_breach)

    triggered = len(breaches) > 0
    score = len(breaches)

    parts: list[str] = []
    if not triggered:
        parts.append("All vitals within MEWT thresholds; no trend breach detected.")
    else:
        for b in breaches:
            if b.loinc == "TREND":
                parts.append(f"Hemodynamic trend rule fired: {b.threshold}")
            else:
                parts.append(f"{b.label} {b.value} {b.unit} breaches {b.threshold} ({b.severity})")

    return MewtResult(
        score=score,
        triggered=triggered,
        breaches=breaches,
        rationale="; ".join(parts),
    )
