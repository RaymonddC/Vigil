"""Demo-mode synthetic FHIR fallback.

When the live FHIR server rejects our SHARP-authenticated read (typically
a 403 from Prompt Opinion's workspace because no SMART-scoped bearer
token is injected), MCP tools transparently fall back to a bundled
synthetic patient (PT-007's deteriorating-postop trajectory in
``data/patients/PT-007.json``). The trajectory feeds the same
deterministic rule engines (MEWT, qSOFA, KDIGO, CDC ASE) the live path
uses, so the screens return real clinical reasoning rather than empty
``fhir_error`` envelopes.

Every fallback response is tagged ``data_source="synthetic_demo"`` so
the agent's chat-friendly reply can disclose the substitution honestly
rather than pretending the data came from the workspace's FHIR server.

Disabled by default; opt-in via ``VIGIL_SYNTHETIC_FALLBACK=true``.
Production deployments against a real FHIR server must NOT enable this —
it's an explicit demo affordance.

Timestamp rebasing
------------------
PT-007's bundled ``effectiveDateTime`` values are anchored to whenever
``data/seed_hapi.py`` was last run. To keep the rule-engine windows
(MEWT lookback, 2-hour trend rule, ``_ABX_EMPIRIC_WINDOW_HOURS``)
producing the trajectory's intended breaches regardless of the bundle's
calendar age, every returned resource has its timestamps shifted so the
most-recent observation lands ~5 minutes before "now". The relative
offsets between sample points (T0, T+1h, T+2h, T+4h, T+6h, T+8h) are
preserved exactly — the trajectory shape is unchanged. This is the same
"anchor to now" strategy ``data/seed_hapi.py`` uses when it generates
the bundle in the first place; we just re-apply it on every read.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.fhir.models import (
    Condition,
    Encounter,
    MedicationAdministration,
    MedicationRequest,
    Observation,
    Patient,
)

# Public env-var contract — matches .env.example. Truthy values enable
# the fallback; anything else (or unset) disables it.
VIGIL_SYNTHETIC_FALLBACK_ENV = "VIGIL_SYNTHETIC_FALLBACK"

# Sentinel that ships in every fallback tool output's ``data_source`` field.
SYNTHETIC_DATA_SOURCE = "synthetic_demo"
LIVE_DATA_SOURCE = "fhir"

# Anchor: shift the bundle so the latest sample is this far before "now".
# 5 min keeps the data inside the default 4-hour MEWT lookback while
# leaving headroom for clock skew.
_RECENT_OFFSET = timedelta(minutes=5)

# Bundle paths — resolved once per import, evaluated against the repo
# layout so dev + container both work (the data directory ships next to
# backend/ in the image).
_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "patients"
_PT007_PATH = _DATA_DIR / "PT-007.json"
_PT008_PATH = _DATA_DIR / "PT-008.json"
_PT010_PATH = _DATA_DIR / "PT-010.json"

# Default bundle = PT-007 (deteriorating-postop trajectory). The PPH
# skill (vigil.assess_pph_severity) targets PT-010 specifically; passing
# patient_id="PT-010" to any of the get_synthetic_* helpers below loads
# that bundle instead. Anything else falls through to PT-007.
_DEFAULT_PATIENT_ID = "PT-007"

# Module-level cache, keyed by patient_id — load each JSON once, then
# reuse across requests. ``_lock`` keeps the first-load race-safe even
# if two MCP tool calls arrive before the cache is populated.
_lock = threading.Lock()
_BUNDLE_CACHE: dict[str, dict[str, Any]] = {}
_MAX_OBS_TIME_CACHE: dict[str, datetime] = {}


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def is_fallback_enabled() -> bool:
    """Return True iff ``VIGIL_SYNTHETIC_FALLBACK`` is set to a truthy value.

    Accepts ``1``, ``true``, ``yes``, ``on`` (case-insensitive). Anything
    else — including the env var being unset — disables the fallback.
    """
    raw = os.environ.get(VIGIL_SYNTHETIC_FALLBACK_ENV, "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def synthetic_disclosure(patient_id: str | None = None) -> str:
    """One-line honest disclosure for the agent's chat-friendly reply text.

    Used by the A2A skill handlers to prefix any response that was
    generated from synthetic data, so judges and downstream consumers
    can tell the data did not come from the live workspace.

    The bundle name is included so the operator can tell exactly which
    canned trajectory drove the response (PT-007 for the default
    deteriorating-postop case, PT-010 for the postpartum hemorrhage
    cameo invoked by ``vigil.assess_pph_severity``).
    """
    bundle = _select_patient(patient_id)
    return (
        "Note: clinical context unavailable from FHIR — using bundled "
        f"demo trajectory ({bundle})."
    )


def synthetic_breach_caveat() -> str:
    """Sentence appended to ``screen_vital_thresholds`` rationale on fallback.

    Lives in the tool's narrative-shaped fields (rationale, criteria_met)
    so a reader who only sees the tool's JSON can still tell the data
    didn't come from the workspace.
    """
    return (
        "using bundled demo trajectory PT-007 because FHIR access was "
        "denied"
    )


def reset_for_tests() -> None:
    """Clear the bundle cache. Tests use this to force a fresh load
    after monkey-patching or after re-seeding the JSON file."""
    with _lock:
        _BUNDLE_CACHE.clear()
        _MAX_OBS_TIME_CACHE.clear()


def _select_patient(patient_id: str | None) -> str:
    """Map an inbound patient_id to the bundle key.

    PT-010 is the postpartum hemorrhage trajectory used by the PPH
    skill; it also exercises the anticoag/Hgb-drop treatment-conflict
    rule via its active enoxaparin order plus the 12.4→9.8 g/dL Hgb
    swing. PT-008 ships the multi-rule conflict bundle — KDIGO stage 2
    AKI plus an active ibuprofen order trips ``nsaid_aki``, and a
    K+ 5.7 mmol/L lab + active lisinopril order trips ``ace_arb_hyperk``.
    PT-007 is the canonical demo trajectory and additionally surfaces
    ``opioid_resp_depression`` (T+9h SpO2 90 + active morphine) and
    ``bblocker_brady_hypo`` (latest SBP 88 + active metoprolol order).
    Everyone else falls through to PT-007 because the synthetic
    disclosure narrative names that bundle explicitly.
    """
    if patient_id == "PT-010":
        return "PT-010"
    if patient_id == "PT-008":
        return "PT-008"
    return _DEFAULT_PATIENT_ID


def get_synthetic_patient(patient_id: str | None = None) -> Patient:
    """Return the bundled :class:`Patient` resource (no time-shift needed)."""
    pid = _select_patient(patient_id)
    items = _resources_of_type("Patient", pid)
    if not items:
        raise RuntimeError(
            f"{pid} bundle missing Patient resource — regenerate via "
            "data/seed_hapi.py --generate-only."
        )
    return Patient.model_validate(items[0])


def get_synthetic_encounter(
    patient_id: str | None = None,
) -> Encounter | None:
    """Return the bundle's most recent :class:`Encounter`, or None.

    Each bundled trajectory has exactly one in-progress Encounter; if
    a future bundle omits it, callers must tolerate None (matches the
    live :func:`FhirClient.get_encounter` contract).
    """
    pid = _select_patient(patient_id)
    items = _resources_of_type("Encounter", pid)
    if not items:
        return None
    return Encounter.model_validate(items[0])


def get_synthetic_observations(
    category: str | None = None,
    patient_id: str | None = None,
) -> list[Observation]:
    """Return the bundle's Observations, time-shifted, sorted newest-first.

    ``category`` filters by :attr:`Observation.category_code` (e.g.
    ``"vital-signs"`` or ``"laboratory"``) to mirror
    :meth:`FhirClient.get_observations`'s ``category`` query parameter.
    ``patient_id`` selects which bundle to load (PT-010 → PPH bundle,
    everything else → PT-007 default). Sort order matches HAPI's
    ``_sort=-date``.
    """
    pid = _select_patient(patient_id)
    offset = _rebase_offset(pid)
    raws = [
        _shift_observation(r, offset)
        for r in _resources_of_type("Observation", pid)
    ]
    obs = [Observation.model_validate(r) for r in raws]

    if category is not None:
        obs = [o for o in obs if o.category_code == category]

    obs.sort(
        key=lambda o: o.effectiveDateTime
        or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return obs


def get_synthetic_conditions(
    patient_id: str | None = None,
) -> list[Condition]:
    """Return the bundle's Conditions (no time shift).

    Conditions are time-independent; we surface them verbatim so the
    risk score's ``contributing_conditions`` field reflects the
    bundled comorbidities.
    """
    pid = _select_patient(patient_id)
    return [
        Condition.model_validate(r)
        for r in _resources_of_type("Condition", pid)
    ]


def get_synthetic_medication_administrations(
    patient_id: str | None = None,
) -> list[MedicationAdministration]:
    """Return the bundle's MedicationAdministration with timestamps rebased."""
    pid = _select_patient(patient_id)
    offset = _rebase_offset(pid)
    raws = [
        _shift_observation(r, offset)
        for r in _resources_of_type("MedicationAdministration", pid)
    ]
    return [MedicationAdministration.model_validate(r) for r in raws]


def get_synthetic_medication_requests(
    patient_id: str | None = None,
) -> list[MedicationRequest]:
    """Return the bundle's MedicationRequest resources (timestamps rebased).

    MedicationRequest carries ``authoredOn`` (not ``effectiveDateTime``),
    so the rebase pass shifts that field instead. The same offset used
    for observations applies — the trajectory shape is preserved end-to-
    end. Used by ``vigil.flag_treatment_conflicts`` so the demo path
    surfaces drug-vs-physiology conflicts even when FHIR is unreachable.
    """
    pid = _select_patient(patient_id)
    offset = _rebase_offset(pid)
    raws: list[dict[str, Any]] = []
    for r in _resources_of_type("MedicationRequest", pid):
        out = dict(r)
        authored = r.get("authoredOn")
        if authored:
            out["authoredOn"] = (_parse_iso(authored) + offset).isoformat()
        raws.append(out)
    return [MedicationRequest.model_validate(r) for r in raws]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _bundle_path(patient_id: str) -> Path:
    """Resolve the JSON path for a known synthetic bundle id."""
    if patient_id == "PT-010":
        return _PT010_PATH
    if patient_id == "PT-008":
        return _PT008_PATH
    return _PT007_PATH


def _load_bundle(patient_id: str) -> dict[str, Any]:
    """Read the bundle JSON once, cache the parsed dict + max-obs-time.

    Race-safe under threading; the cache is populated under ``_lock`` so
    two simultaneous first-callers don't both hit the disk.
    """
    cached = _BUNDLE_CACHE.get(patient_id)
    if cached is not None:
        return cached

    with _lock:
        cached = _BUNDLE_CACHE.get(patient_id)
        if cached is not None:  # double-checked locking
            return cached

        path = _bundle_path(patient_id)
        with path.open("r", encoding="utf-8") as fh:
            bundle = json.load(fh)

        max_t: datetime | None = None
        for entry in bundle.get("entry", []):
            res = entry.get("resource", {})
            edt = res.get("effectiveDateTime")
            if not edt:
                continue
            ts = _parse_iso(edt)
            if max_t is None or ts > max_t:
                max_t = ts

        _BUNDLE_CACHE[patient_id] = bundle
        # Fall back to "now" if the bundle has no timestamps at all —
        # rebasing then becomes a no-op, which is the safe default.
        _MAX_OBS_TIME_CACHE[patient_id] = max_t or datetime.now(UTC)
        return bundle


def _resources_of_type(
    rtype: str, patient_id: str = _DEFAULT_PATIENT_ID,
) -> list[dict[str, Any]]:
    """Filter the bundle's entries by FHIR ``resourceType``."""
    bundle = _load_bundle(patient_id)
    out: list[dict[str, Any]] = []
    for entry in bundle.get("entry", []):
        if not isinstance(entry, dict):
            continue
        res = entry.get("resource")
        if isinstance(res, dict) and res.get("resourceType") == rtype:
            out.append(res)
    return out


def _rebase_offset(patient_id: str = _DEFAULT_PATIENT_ID) -> timedelta:
    """Return the timedelta that shifts the bundle's most-recent sample
    to ``now - _RECENT_OFFSET``.

    Computed every call so successive tool invocations across a single
    process always anchor to "now" — important for long-running agent
    deployments where the cache may persist for hours.
    """
    _load_bundle(patient_id)  # ensures cache is set
    target = datetime.now(UTC) - _RECENT_OFFSET
    base = _MAX_OBS_TIME_CACHE.get(patient_id) or target
    return target - base


def _parse_iso(s: str) -> datetime:
    """Parse a FHIR-style ISO datetime, accepting trailing 'Z'."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _shift_observation(
    raw: dict[str, Any], offset: timedelta
) -> dict[str, Any]:
    """Return a shallow copy of ``raw`` with ``effectiveDateTime`` shifted."""
    out = dict(raw)
    edt = raw.get("effectiveDateTime")
    if edt:
        out["effectiveDateTime"] = (
            _parse_iso(edt) + offset
        ).isoformat()
    return out
