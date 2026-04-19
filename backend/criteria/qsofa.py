"""qSOFA — Quick Sequential Organ Failure Assessment.

Deterministic bedside score: 0-3 points from three criteria.

Source: Singer M et al. "The Third International Consensus Definitions for
Sepsis and Septic Shock (Sepsis-3)." JAMA 2016;315(8):801-810.
(CLINICAL_EVIDENCE §3.1)

Criteria:
  - Respiratory rate >= 22 /min  (1 point)
  - Altered mentation (GCS < 15) (1 point)
  - Systolic BP <= 100 mmHg      (1 point)

Score >= 2 => suspect sepsis at bedside.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class QsofaResult(BaseModel):
    """Result of qSOFA scoring."""

    score: int = Field(ge=0, le=3)
    triggered: bool = Field(
        description="True when score >= 2 (suspect sepsis at bedside)"
    )
    components: dict[str, bool] = Field(
        description="Individual criterion results: rr_ge_22, sbp_le_100, altered_mental"
    )
    rationale: str = ""


def evaluate_qsofa(
    sbp: float | None = None,
    rr: float | None = None,
    gcs: int | None = None,
    altered_mental: bool = False,
) -> QsofaResult:
    """Compute qSOFA score from vital values.

    Args:
        sbp: Systolic blood pressure in mmHg. LOINC 8480-6.
        rr: Respiratory rate in breaths/min. LOINC 9279-1.
        gcs: Glasgow Coma Scale (3-15). If < 15, altered mentation = True.
        altered_mental: Direct flag for altered mentation (overrides gcs if True).

    Returns:
        QsofaResult with score 0-3, triggered if >= 2.
    """
    # RR >= 22 (Singer 2016, Sepsis-3)
    rr_ge_22 = rr is not None and rr >= 22

    # SBP <= 100 (Singer 2016, Sepsis-3)
    sbp_le_100 = sbp is not None and sbp <= 100

    # Altered mentation: GCS < 15 or direct flag
    is_altered = altered_mental or (gcs is not None and gcs < 15)

    components = {
        "rr_ge_22": rr_ge_22,
        "sbp_le_100": sbp_le_100,
        "altered_mental": is_altered,
    }

    score = sum(components.values())
    triggered = score >= 2

    parts: list[str] = []
    if rr_ge_22:
        parts.append(f"RR {rr} >= 22")
    if sbp_le_100:
        parts.append(f"SBP {sbp} <= 100")
    if is_altered:
        parts.append("Altered mentation")
    if not parts:
        parts.append("No qSOFA criteria met")

    rationale = f"qSOFA={score}; " + "; ".join(parts)

    return QsofaResult(
        score=score,
        triggered=triggered,
        components=components,
        rationale=rationale,
    )
