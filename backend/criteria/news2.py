"""NEWS2 — National Early Warning Score 2 (Royal College of Physicians 2017).

Deterministic chart-based score: each of 7 parameters contributes 0-3
points. The aggregate maps to a clinical-response band; a SINGLE
parameter scoring 3 is a "red flag" per RCP guidance — it triggers an
urgent response even if the aggregate is low.

Source: Royal College of Physicians. *National Early Warning Score
(NEWS) 2: Standardising the assessment of acute-illness severity in
the NHS.* Updated report of a working party. London: RCP, 2017.
URL: https://www.rcplondon.ac.uk/projects/outputs/national-early-warning-score-news-2

Parameter chart (RCP 2017, Table 1 - reproduced verbatim):

  Respiratory rate (/min):
    ≤8       → 3
    9–11     → 1
    12–20    → 0
    21–24    → 2
    ≥25      → 3

  SpO2 — Scale 1 (default, no hypercapnic resp failure):
    ≤91      → 3
    92–93    → 2
    94–95    → 1
    ≥96      → 0
  (Vigil uses Scale 1 only; Scale 2 is gated to chronic
  hypercapnic-resp-failure patients and is out of scope.)

  Supplemental O2 (Air vs Oxygen):
    Air      → 0
    Oxygen   → 2

  Temperature (°C):
    ≤35.0       → 3
    35.1–36.0   → 1
    36.1–38.0   → 0
    38.1–39.0   → 1
    ≥39.1       → 2

  Systolic BP (mmHg):
    ≤90        → 3
    91–100     → 2
    101–110    → 1
    111–219    → 0
    ≥220       → 3

  Heart rate (/min):
    ≤40       → 3
    41–50     → 1
    51–90     → 0
    91–110    → 1
    111–130   → 2
    ≥131      → 3

  Consciousness (ACVPU):
    Alert        → 0
    Confusion / V / P / U → 3

Aggregate banding (RCP 2017, Table 2):
  0      → low (12-hourly observation, ward-based)
  1–4    → low-medium (4–6 hourly)
  3 in any single parameter → medium (1-hourly + urgent ward review)
  5–6    → medium (1-hourly + urgent review)
  ≥7     → high (continuous monitoring + critical-care review)
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class News2ParamScore(BaseModel):
    """Single-parameter NEWS2 score row."""

    parameter: str
    value: float | None
    score: int = Field(ge=0, le=3)


class News2Result(BaseModel):
    """Result of NEWS2 scoring."""

    aggregate: int = Field(ge=0, le=20)
    band: str = Field(description="low | low-medium | medium | high")
    red_flag: bool = Field(
        description="True iff any single parameter contributes 3 points",
    )
    contributions: list[News2ParamScore]
    rationale: str = ""


# ---------------------------------------------------------------------------
# Per-parameter chart helpers — small, table-driven, unit-tested
# individually so the boundary semantics are obvious to a reviewer.
# ---------------------------------------------------------------------------


def _score_rr(rr: float | None) -> int:
    if rr is None:
        return 0
    if rr <= 8:
        return 3
    if rr <= 11:
        return 1
    if rr <= 20:
        return 0
    if rr <= 24:
        return 2
    return 3


def _score_spo2_scale1(spo2: float | None) -> int:
    if spo2 is None:
        return 0
    if spo2 <= 91:
        return 3
    if spo2 <= 93:
        return 2
    if spo2 <= 95:
        return 1
    return 0


def _score_o2(supplemental_o2: bool) -> int:
    return 2 if supplemental_o2 else 0


def _score_temp(temp_c: float | None) -> int:
    if temp_c is None:
        return 0
    if temp_c <= 35.0:
        return 3
    if temp_c <= 36.0:
        return 1
    if temp_c <= 38.0:
        return 0
    if temp_c <= 39.0:
        return 1
    return 2


def _score_sbp(sbp: float | None) -> int:
    if sbp is None:
        return 0
    if sbp <= 90:
        return 3
    if sbp <= 100:
        return 2
    if sbp <= 110:
        return 1
    if sbp >= 220:
        return 3
    return 0


def _score_hr(hr: float | None) -> int:
    if hr is None:
        return 0
    if hr <= 40:
        return 3
    if hr <= 50:
        return 1
    if hr <= 90:
        return 0
    if hr <= 110:
        return 1
    if hr <= 130:
        return 2
    return 3


def _score_consciousness(alert: bool | None) -> int:
    """0 if Alert (or unknown — assume alert), 3 if any new C/V/P/U."""
    if alert is None or alert:
        return 0
    return 3


def _band(aggregate: int, red_flag: bool) -> str:
    """RCP 2017 Table 2 — aggregate-to-band mapping with red-flag override."""
    if aggregate >= 7:
        return "high"
    if aggregate >= 5 or red_flag:
        return "medium"
    if aggregate >= 1:
        return "low-medium"
    return "low"


# ---------------------------------------------------------------------------
# Public scorer
# ---------------------------------------------------------------------------


def evaluate_news2(
    rr: float | None = None,
    spo2: float | None = None,
    supplemental_o2: bool = False,
    temp_c: float | None = None,
    sbp: float | None = None,
    hr: float | None = None,
    alert: bool | None = None,
) -> News2Result:
    """Score NEWS2 from latest vital values.

    Args:
        rr: Respiratory rate (/min).
        spo2: Oxygen saturation (%, Scale 1).
        supplemental_o2: True iff patient is on supplemental oxygen.
        temp_c: Body temperature (°C).
        sbp: Systolic BP (mmHg).
        hr: Heart rate (/min).
        alert: True if Alert on ACVPU. False if any C/V/P/U.
            None → assume Alert (no penalty).

    Returns:
        News2Result with aggregate 0–20, band, red-flag, per-parameter rows.
    """
    rows = [
        News2ParamScore(parameter="RR", value=rr, score=_score_rr(rr)),
        News2ParamScore(
            parameter="SpO2", value=spo2, score=_score_spo2_scale1(spo2)
        ),
        News2ParamScore(
            parameter="SupplementalO2",
            value=1.0 if supplemental_o2 else 0.0,
            score=_score_o2(supplemental_o2),
        ),
        News2ParamScore(
            parameter="Temp", value=temp_c, score=_score_temp(temp_c)
        ),
        News2ParamScore(parameter="SBP", value=sbp, score=_score_sbp(sbp)),
        News2ParamScore(parameter="HR", value=hr, score=_score_hr(hr)),
        News2ParamScore(
            parameter="Consciousness",
            value=None,
            score=_score_consciousness(alert),
        ),
    ]

    aggregate = sum(r.score for r in rows)
    red_flag = any(r.score == 3 for r in rows)
    band = _band(aggregate, red_flag)

    parts: list[str] = [f"NEWS2={aggregate} ({band})"]
    threes = [r.parameter for r in rows if r.score == 3]
    if threes:
        parts.append("red flag from " + ", ".join(threes))
    rationale = "; ".join(parts)

    return News2Result(
        aggregate=aggregate,
        band=band,
        red_flag=red_flag,
        contributions=rows,
        rationale=rationale,
    )
