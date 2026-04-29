"""Treatment-conflict rule engine — physiology-aware drug safety scanner.

Given a snapshot of the patient's vitals/labs/conditions plus the drugs
they have on board (active MedicationAdministration in the recent past
+ active MedicationRequest), this module flags conflicts that should
make a downstream order-writing agent pause.

Five rules ship in v1:

  1. NSAID + AKI                    — KDIGO 2012 §4.4.1, AGS Beers 2023.
  2. β-blocker + bradycardia/hypotension — 2017 ACC/AHA hypertension
                                       guideline (Whelton, Hypertension
                                       2018;71:e13).
  3. ACE-I/ARB + hyperkalemia       — KDIGO 2024 BP-in-CKD §4.3 + Beers 2023.
  4. Opioid + respiratory depression — ASPMN guideline (Jungquist, Pain
                                       Manag Nurs 2020;21:7).
  5. Anticoagulant + Hgb drop /
     active-bleeding suspicion       — ASH 2018 VTE Anticoagulation
                                       guideline (Witt, Blood Adv 2018;
                                       2:3257).

All rules are deterministic — no LLM. Each rule carries a citation
anchor (linked to ``docs/CLINICAL_EVIDENCE.md`` "Treatment Conflict
Rules") and a verbatim mitigation string. The chat-friendly prose is
layered downstream (in the A2A skill handler) on top of the structured
verdict this module returns.

References:
- KDIGO 2012 AKI §4.4.1: avoid nephrotoxic agents.
  https://kdigo.org/wp-content/uploads/2016/10/KDIGO-2012-AKI-Guideline-English.pdf
- AGS 2023 Beers Criteria: avoid NSAIDs + ACE-I/ARB in elderly with
  reduced kidney function. J Am Geriatr Soc 2023.
  https://agsjournals.onlinelibrary.wiley.com/doi/10.1111/jgs.18372
- 2017 ACC/AHA hypertension guideline (Whelton et al, Hypertension 2018;
  71:e13). https://www.ahajournals.org/doi/10.1161/HYP.0000000000000065
- KDIGO 2024 BP-in-CKD §4.3: monitor K+ on RAAS inhibitors.
  https://kdigo.org/guidelines/blood-pressure-in-ckd/
- ASPMN guideline on monitoring for opioid-induced advancing sedation
  and respiratory depression (Jungquist CR et al, Pain Manag Nurs 2020;
  21:7). https://pubmed.ncbi.nlm.nih.gov/31785972/
- ASH 2018 VTE Anticoagulation guideline (Witt DM et al, Blood Adv 2018;
  2:3257). https://ashpublications.org/bloodadvances/article/2/22/3257/15700
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.fhir.models import (
    MedicationAdministration,
    MedicationRequest,
    Observation,
)

# ---------------------------------------------------------------------------
# Drug-class lookup tables — display-name keywords (case-insensitive
# substring match against MedicationAdministration / MedicationRequest's
# medicationCodeableConcept.coding[].display). Keep these short and
# targeted; we are not trying to be a full RxNorm formulary.
# Order matters only for tests' readability — match is membership.
# ---------------------------------------------------------------------------

NSAIDS: tuple[str, ...] = (
    "ibuprofen", "ketorolac", "naproxen", "celecoxib", "diclofenac",
    "indomethacin", "meloxicam", "aspirin",
)

BETA_BLOCKERS: tuple[str, ...] = (
    "metoprolol", "atenolol", "propranolol", "carvedilol",
    "bisoprolol", "esmolol", "labetalol",
)

ACE_ARB: tuple[str, ...] = (
    "lisinopril", "enalapril", "ramipril", "losartan", "valsartan",
    "irbesartan", "candesartan", "captopril",
)

OPIOIDS: tuple[str, ...] = (
    "morphine", "oxycodone", "hydrocodone", "fentanyl",
    "hydromorphone", "codeine", "tramadol", "buprenorphine",
)

ANTICOAGULANTS: tuple[str, ...] = (
    "heparin", "enoxaparin", "warfarin", "apixaban", "rivaroxaban",
    "dabigatran", "edoxaban", "fondaparinux",
)

# Active-medication window: an administration is counted as "currently on
# board" if it landed within this window. MedicationRequest with
# status=active is always counted regardless of authoredOn.
_ACTIVE_ADMIN_WINDOW_HOURS = 12

# Opioid + respiratory-depression window — ASPMN 2020 §5 recommends
# reassessment at 15-30 min, 1h, 2h, 4h post-administration. We use 4h
# as the conservative outer envelope.
_OPIOID_RR_WINDOW_HOURS = 4

# LOINC codes used for physiology lookups.
_LOINC_HR = "8867-4"
_LOINC_SBP = "8480-6"
_LOINC_SPO2 = "59408-5"
_LOINC_RR = "9279-1"
_LOINC_K = "2823-3"          # Potassium [Moles/volume] in Serum or Plasma
_LOINC_HGB = "718-7"          # Hemoglobin [Mass/volume] in Blood
_LOINC_CREATININE = "2160-0"


# ---------------------------------------------------------------------------
# Public output shape
# ---------------------------------------------------------------------------


@dataclass
class TreatmentConflictRow:
    """One conflict row produced by ``evaluate_treatment_conflicts``."""

    rule_id: str
    severity: str  # "critical" | "warning"
    drug_class: str
    drug_display: str
    physiology_summary: str
    citation_anchor: str
    mitigation: str
    safe_alternatives: list[str]


@dataclass
class ConflictReport:
    """Aggregate report returned by the engine."""

    conflicts: list[TreatmentConflictRow] = field(default_factory=list)
    safe_alternatives: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers — drug discovery, latest-obs lookup
# ---------------------------------------------------------------------------


def _coding_display(cc: Any) -> str:
    """Return a flat lowercase display string from a CodeableConcept-shaped obj.

    Tolerates both the live FHIR-model objects (``cc.coding[].display``)
    and dict-shaped fallbacks. Prefers ``cc.text`` when present (humans
    read that — it's typically the dispensed product label); falls back
    to the first ``coding[].display`` only when no text is set. Returns
    "" when the input is missing both.
    """
    if cc is None:
        return ""
    text = getattr(cc, "text", None)
    if text is None and isinstance(cc, dict):
        text = cc.get("text")
    if isinstance(text, str) and text:
        return text.lower()
    coding = getattr(cc, "coding", None)
    if coding is None and isinstance(cc, dict):
        coding = cc.get("coding")
    if isinstance(coding, list):
        for c in coding:
            disp = getattr(c, "display", None)
            if disp is None and isinstance(c, dict):
                disp = c.get("display")
            if isinstance(disp, str) and disp:
                return disp.lower()
    return ""


def _matches_class(display: str, keywords: tuple[str, ...]) -> str | None:
    """Return the first matching keyword from ``keywords`` if any appears in display."""
    for kw in keywords:
        if kw in display:
            return kw
    return None


def _admin_display(ma: MedicationAdministration) -> str:
    """Lowercase display string for a MedicationAdministration."""
    return _coding_display(ma.medicationCodeableConcept)


def _request_display(mr: MedicationRequest) -> str:
    """Lowercase display string for a MedicationRequest.

    Falls back to ``medicationReference.display`` if no codeableConcept.
    """
    disp = _coding_display(mr.medicationCodeableConcept)
    if disp:
        return disp
    if mr.medicationReference and mr.medicationReference.display:
        return mr.medicationReference.display.lower()
    return ""


def _active_administrations(
    admins: list[MedicationAdministration],
    now: datetime,
) -> list[MedicationAdministration]:
    """Filter to administrations completed/in-progress within the active window."""
    cutoff = now - timedelta(hours=_ACTIVE_ADMIN_WINDOW_HOURS)
    out: list[MedicationAdministration] = []
    for ma in admins:
        if ma.status not in ("completed", "in-progress", "active"):
            continue
        if ma.effectiveDateTime is not None and ma.effectiveDateTime < cutoff:
            continue
        out.append(ma)
    return out


def _active_requests(
    requests: list[MedicationRequest],
) -> list[MedicationRequest]:
    """Filter MedicationRequest to active/on-hold orders."""
    return [
        mr for mr in requests
        if (mr.status or "").lower() in ("active", "on-hold")
    ]


def _find_drug(
    admins: list[MedicationAdministration],
    requests: list[MedicationRequest],
    keywords: tuple[str, ...],
    now: datetime,
) -> tuple[str | None, str, str]:
    """Return (matched_keyword, display_text, source) for first hit, else (None, "", "").

    Searches active MedicationRequest first (forward-looking, the order
    is queued), then recently-administered MedicationAdministration.
    ``source`` is ``"order"`` or ``"administration"``.
    """
    for mr in _active_requests(requests):
        disp = _request_display(mr)
        kw = _matches_class(disp, keywords)
        if kw:
            return kw, disp, "order"
    for ma in _active_administrations(admins, now):
        disp = _admin_display(ma)
        kw = _matches_class(disp, keywords)
        if kw:
            return kw, disp, "administration"
    return None, "", ""


def _latest_obs_value(
    observations: list[Observation], loinc: str,
) -> tuple[float | None, datetime | None]:
    """Return (value, ts) of the most recent Observation matching loinc."""
    candidates = [
        o for o in observations
        if o.loinc_code == loinc
        and o.valueQuantity
        and o.valueQuantity.value is not None
    ]
    if not candidates:
        return None, None
    candidates.sort(
        key=lambda o: o.effectiveDateTime
        or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    obs = candidates[0]
    return float(obs.valueQuantity.value), obs.effectiveDateTime  # type: ignore[union-attr]


def _hgb_drop(observations: list[Observation]) -> tuple[float | None, float | None, float | None]:
    """Return (current_hgb, baseline_hgb, drop_g_dl).

    Baseline = lowest Hgb in the past 7 days excluding the current
    sample, OR the value 24h prior if we have one. Drop = baseline -
    current (positive => drop). When the patient has only one Hgb sample,
    everything returns None (no drop computable).
    """
    hgbs = [
        o for o in observations
        if o.loinc_code == _LOINC_HGB
        and o.valueQuantity
        and o.valueQuantity.value is not None
        and o.effectiveDateTime is not None
    ]
    if len(hgbs) < 2:
        return (
            float(hgbs[0].valueQuantity.value) if hgbs else None,  # type: ignore[union-attr]
            None,
            None,
        )
    hgbs.sort(key=lambda o: o.effectiveDateTime)  # type: ignore[arg-type]
    current_obs = hgbs[-1]
    current = float(current_obs.valueQuantity.value)  # type: ignore[union-attr]

    cutoff = current_obs.effectiveDateTime - timedelta(days=7)  # type: ignore[operator]
    historical = [
        o for o in hgbs[:-1]
        if o.effectiveDateTime is not None
        and o.effectiveDateTime >= cutoff
    ]
    if not historical:
        return current, None, None
    # Highest historical Hgb in the past 7 days = best proxy for "before
    # the bleed started". Using max (not earliest) catches drops even
    # when the patient was already trending down.
    historical.sort(
        key=lambda o: float(o.valueQuantity.value), reverse=True,  # type: ignore[union-attr]
    )
    baseline = float(historical[0].valueQuantity.value)  # type: ignore[union-attr]
    drop = round(baseline - current, 2)
    return current, baseline, drop


# ---------------------------------------------------------------------------
# Rule severity helpers
# ---------------------------------------------------------------------------


def _bb_severity(hr: float | None, sbp: float | None) -> str:
    """β-blocker rule: critical if HR<50 or SBP<85, else warning."""
    if (hr is not None and hr < 50) or (sbp is not None and sbp < 85):
        return "critical"
    return "warning"


def _ace_severity(k: float | None) -> str:
    """ACE-I/ARB rule: critical if K+>=6.0, else warning."""
    if k is not None and k >= 6.0:
        return "critical"
    return "warning"


def _anticoag_severity(
    current_hgb: float | None, drop: float | None,
) -> str:
    """Anticoagulant rule: critical if drop>=3.0 or current<8.0, else warning."""
    if drop is not None and drop >= 3.0:
        return "critical"
    if current_hgb is not None and current_hgb < 8.0:
        return "critical"
    return "warning"


# ---------------------------------------------------------------------------
# Public engine
# ---------------------------------------------------------------------------


def evaluate_treatment_conflicts(
    observations: list[Observation],
    medication_administrations: list[MedicationAdministration],
    medication_requests: list[MedicationRequest],
    kdigo_stage: int = 0,
    now: datetime | None = None,
) -> ConflictReport:
    """Evaluate the 5 treatment-conflict rules and return a structured report.

    Args:
        observations: All Observations (vitals + labs) for the patient.
        medication_administrations: MedicationAdministration history.
        medication_requests: MedicationRequest list (active + queued).
        kdigo_stage: KDIGO AKI stage (0–3) computed by ``evaluate_kdigo``
            from the same observations. Pass 0 if not staged.
        now: Override for "now" — useful in tests. Defaults to
            ``datetime.now(UTC)``.

    Returns:
        :class:`ConflictReport` with conflicts list, safe-alternatives
        de-duplicated across rules, and a debug evidence dict.
    """
    when = now or datetime.now(UTC)
    conflicts: list[TreatmentConflictRow] = []
    evidence: dict[str, Any] = {
        "kdigo_stage": kdigo_stage,
        "active_window_hours": _ACTIVE_ADMIN_WINDOW_HOURS,
    }

    hr, _ = _latest_obs_value(observations, _LOINC_HR)
    sbp, _ = _latest_obs_value(observations, _LOINC_SBP)
    spo2, _ = _latest_obs_value(observations, _LOINC_SPO2)
    rr, _ = _latest_obs_value(observations, _LOINC_RR)
    k, _ = _latest_obs_value(observations, _LOINC_K)
    current_hgb, baseline_hgb, hgb_drop = _hgb_drop(observations)
    evidence.update(
        hr=hr, sbp=sbp, spo2=spo2, rr=rr, k=k,
        hgb_current=current_hgb, hgb_baseline=baseline_hgb, hgb_drop=hgb_drop,
    )

    # --- Rule 1: NSAID + AKI ---
    # KDIGO stage >= 1 (AKI present) + active/recent NSAID = critical.
    nsaid_kw, nsaid_disp, nsaid_src = _find_drug(
        medication_administrations, medication_requests, NSAIDS, when,
    )
    if nsaid_kw and kdigo_stage >= 1:
        conflicts.append(TreatmentConflictRow(
            rule_id="nsaid_aki",
            severity="critical",
            drug_class="NSAID",
            drug_display=nsaid_disp or nsaid_kw,
            physiology_summary=(
                f"KDIGO stage {kdigo_stage} AKI present"
            ),
            citation_anchor=(
                "KDIGO 2012 §4.4.1; AGS Beers Criteria 2023"
            ),
            mitigation=(
                "Consider acetaminophen, gabapentin, or "
                "regional/local analgesia; if NSAID required, "
                "monitor SCr q24h, hold ACE-I/ARB."
            ),
            safe_alternatives=[
                "acetaminophen", "gabapentin",
                "regional/local anaesthesia",
            ],
        ))

    # --- Rule 2: β-blocker + bradycardia/hypotension ---
    # HR<55 OR SBP<90 + active β-blocker.
    bb_kw, bb_disp, bb_src = _find_drug(
        medication_administrations, medication_requests, BETA_BLOCKERS, when,
    )
    bb_physio_trigger = (hr is not None and hr < 55) or (
        sbp is not None and sbp < 90
    )
    if bb_kw and bb_physio_trigger:
        sev = _bb_severity(hr, sbp)
        physio_bits: list[str] = []
        if hr is not None and hr < 55:
            physio_bits.append(f"HR {hr:.0f} <55")
        if sbp is not None and sbp < 90:
            physio_bits.append(f"SBP {sbp:.0f} <90")
        conflicts.append(TreatmentConflictRow(
            rule_id="bblocker_brady_hypo",
            severity=sev,
            drug_class="β-blocker",
            drug_display=bb_disp or bb_kw,
            physiology_summary=", ".join(physio_bits),
            citation_anchor=(
                "2017 ACC/AHA hypertension guideline (Whelton, "
                "Hypertension 2018;71:e13)"
            ),
            mitigation=(
                "Hold next dose, recheck HR/BP in 30 min; consider "
                "rate reduction or alternative agent."
            ),
            safe_alternatives=[
                "rate reduction", "ivabradine (if HF on guideline rx)",
                "alternative anti-anginal",
            ],
        ))

    # --- Rule 3: ACE-I/ARB + hyperkalemia ---
    # K+ >= 5.5 mmol/L + active ACE-I/ARB.
    ace_kw, ace_disp, ace_src = _find_drug(
        medication_administrations, medication_requests, ACE_ARB, when,
    )
    if ace_kw and k is not None and k >= 5.5:
        sev = _ace_severity(k)
        conflicts.append(TreatmentConflictRow(
            rule_id="ace_arb_hyperk",
            severity=sev,
            drug_class="ACE-I/ARB",
            drug_display=ace_disp or ace_kw,
            physiology_summary=f"K+ {k:.1f} mmol/L >=5.5",
            citation_anchor=(
                "KDIGO 2024 BP-in-CKD §4.3; AGS Beers 2023"
            ),
            mitigation=(
                "Hold ACE-I/ARB; treat hyperkalemia per ED algorithm; "
                "recheck K+ q4h until <5.0."
            ),
            safe_alternatives=[
                "calcium-channel blocker", "thiazide",
                "hydralazine + nitrate (HFrEF if intolerant)",
            ],
        ))

    # --- Rule 4: Opioid + respiratory depression ---
    # SpO2<92% OR RR<12 within 4h of most-recent opioid.
    opioid_kw, opioid_disp, opioid_src = _find_drug(
        medication_administrations, medication_requests, OPIOIDS, when,
    )
    # Tighten the window for the opioid rule — only ADMINISTRATIONS in
    # the last 4h count for the "post-dose monitoring" trigger. A queued
    # MedicationRequest alone does not yet imply respiratory depression
    # unless physiology is already trending bad.
    opioid_recent_admin: MedicationAdministration | None = None
    rr_window = when - timedelta(hours=_OPIOID_RR_WINDOW_HOURS)
    for ma in medication_administrations:
        if ma.status not in ("completed", "in-progress", "active"):
            continue
        disp = _admin_display(ma)
        if not _matches_class(disp, OPIOIDS):
            continue
        if ma.effectiveDateTime is None or ma.effectiveDateTime < rr_window:
            continue
        opioid_recent_admin = ma
        break
    physio_bad = (spo2 is not None and spo2 < 92) or (
        rr is not None and rr < 12
    )
    if opioid_kw and physio_bad and (
        opioid_recent_admin is not None or opioid_src == "order"
    ):
        physio_bits = []
        if spo2 is not None and spo2 < 92:
            physio_bits.append(f"SpO2 {spo2:.0f}% <92")
        if rr is not None and rr < 12:
            physio_bits.append(f"RR {rr:.0f} <12")
        conflicts.append(TreatmentConflictRow(
            rule_id="opioid_resp_depression",
            severity="critical",
            drug_class="opioid",
            drug_display=opioid_disp or opioid_kw,
            physiology_summary=", ".join(physio_bits),
            citation_anchor=(
                "ASPMN 2020 (Jungquist, Pain Manag Nurs 2020;21:7)"
            ),
            mitigation=(
                "Hold next opioid dose; consider naloxone if RR <8; "
                "supplement O2; reassess sedation Pasero score q15 min."
            ),
            safe_alternatives=[
                "scheduled acetaminophen", "regional block",
                "non-opioid multimodal analgesia",
            ],
        ))

    # --- Rule 5: Anticoagulant + Hgb drop / active-bleeding suspicion ---
    # Hgb drop >=2.0 g/dL + active anticoagulant.
    ac_kw, ac_disp, ac_src = _find_drug(
        medication_administrations, medication_requests, ANTICOAGULANTS, when,
    )
    if ac_kw and hgb_drop is not None and hgb_drop >= 2.0:
        sev = _anticoag_severity(current_hgb, hgb_drop)
        conflicts.append(TreatmentConflictRow(
            rule_id="anticoag_hgb_drop",
            severity=sev,
            drug_class="anticoagulant",
            drug_display=ac_disp or ac_kw,
            physiology_summary=(
                f"Hgb dropped {hgb_drop:.1f} g/dL "
                f"({baseline_hgb:.1f}→{current_hgb:.1f})"
            ),
            citation_anchor=(
                "ASH 2018 VTE Anticoagulation guideline (Witt, "
                "Blood Adv 2018;2:3257)"
            ),
            mitigation=(
                "Hold anticoagulant; type & screen + CBC stat; "
                "consider reversal agent if drop >3 g/dL or "
                "hemodynamic compromise."
            ),
            safe_alternatives=[
                "mechanical VTE prophylaxis (SCDs)",
                "reversal agent (if reversal indicated)",
            ],
        ))

    # De-duplicate safe alternatives across rules, preserving order.
    seen: set[str] = set()
    safe_alts: list[str] = []
    for c in conflicts:
        for alt in c.safe_alternatives:
            if alt not in seen:
                seen.add(alt)
                safe_alts.append(alt)

    return ConflictReport(
        conflicts=conflicts,
        safe_alternatives=safe_alts,
        evidence=evidence,
    )
