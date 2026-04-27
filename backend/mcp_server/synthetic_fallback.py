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

# Bundle path — resolved once per import, evaluated against the repo
# layout so dev + container both work (the data directory ships next to
# backend/ in the image).
_PT007_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "patients" / "PT-007.json"
)

# Module-level cache — load the JSON once, then reuse across requests.
# `_lock` keeps the first-load race-safe even if two MCP tool calls
# arrive before the cache is populated.
_lock = threading.Lock()
_BUNDLE_CACHE: dict[str, Any] | None = None
_MAX_OBS_TIME_CACHE: datetime | None = None


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


def synthetic_disclosure() -> str:
    """One-line honest disclosure for the agent's chat-friendly reply text.

    Used by the A2A skill handlers to prefix any response that was
    generated from synthetic data, so judges and downstream consumers
    can tell the data did not come from the live workspace.
    """
    return (
        "Note: clinical context unavailable from FHIR — using bundled "
        "demo trajectory (PT-007)."
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
    global _BUNDLE_CACHE, _MAX_OBS_TIME_CACHE
    with _lock:
        _BUNDLE_CACHE = None
        _MAX_OBS_TIME_CACHE = None


def get_synthetic_patient() -> Patient:
    """Return PT-007's :class:`Patient` resource (no time-shift needed)."""
    items = _resources_of_type("Patient")
    if not items:
        raise RuntimeError(
            "PT-007 bundle missing Patient resource — regenerate via "
            "data/seed_hapi.py --generate-only."
        )
    return Patient.model_validate(items[0])


def get_synthetic_encounter() -> Encounter | None:
    """Return PT-007's most recent :class:`Encounter`, or None.

    PT-007's bundle has exactly one in-progress Encounter; if the
    bundle is ever regenerated to omit it, callers must tolerate None
    (matches the live :func:`FhirClient.get_encounter` contract).
    """
    items = _resources_of_type("Encounter")
    if not items:
        return None
    return Encounter.model_validate(items[0])


def get_synthetic_observations(
    category: str | None = None,
) -> list[Observation]:
    """Return PT-007's Observations, time-shifted, sorted newest-first.

    ``category`` filters by :attr:`Observation.category_code` (e.g.
    ``"vital-signs"`` or ``"laboratory"``) to mirror
    :meth:`FhirClient.get_observations`'s ``category`` query parameter.
    Sort order matches HAPI's ``_sort=-date``.
    """
    offset = _rebase_offset()
    raws = [
        _shift_observation(r, offset)
        for r in _resources_of_type("Observation")
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


def get_synthetic_conditions() -> list[Condition]:
    """Return PT-007's Conditions (T2DM + CKD3 — both active, no time shift).

    Conditions are time-independent; we surface them verbatim so the
    risk score's ``contributing_conditions`` field reflects the
    bundled comorbidities.
    """
    return [
        Condition.model_validate(r)
        for r in _resources_of_type("Condition")
    ]


def get_synthetic_medication_administrations() -> list[MedicationAdministration]:
    """Return PT-007's MedicationAdministration with timestamps rebased.

    PT-007 has only the pre-op cefazolin dose — well outside the CDC
    ASE empiric-antibiotic window after rebasing. That's intentional:
    PT-007 is the deteriorating-but-not-yet-septic case, so the sepsis
    tool will return ``sepsis_suspected=false`` with real reasoning
    (organ-dysfunction lab values, but no presumed infection signal).
    """
    offset = _rebase_offset()
    raws = [
        _shift_observation(r, offset)
        for r in _resources_of_type("MedicationAdministration")
    ]
    return [MedicationAdministration.model_validate(r) for r in raws]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_pt007_bundle() -> dict[str, Any]:
    """Read ``PT-007.json`` once, cache the parsed dict + max-obs-time.

    Race-safe under threading; the cache is populated under ``_lock`` so
    two simultaneous first-callers don't both hit the disk.
    """
    global _BUNDLE_CACHE, _MAX_OBS_TIME_CACHE
    if _BUNDLE_CACHE is not None:
        return _BUNDLE_CACHE

    with _lock:
        if _BUNDLE_CACHE is not None:  # double-checked locking
            return _BUNDLE_CACHE

        with _PT007_PATH.open("r", encoding="utf-8") as fh:
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

        _BUNDLE_CACHE = bundle
        # Fall back to "now" if the bundle has no timestamps at all —
        # rebasing then becomes a no-op, which is the safe default.
        _MAX_OBS_TIME_CACHE = max_t or datetime.now(UTC)
        return _BUNDLE_CACHE


def _resources_of_type(rtype: str) -> list[dict[str, Any]]:
    """Filter the bundle's entries by FHIR ``resourceType``."""
    bundle = _load_pt007_bundle()
    out: list[dict[str, Any]] = []
    for entry in bundle.get("entry", []):
        if not isinstance(entry, dict):
            continue
        res = entry.get("resource")
        if isinstance(res, dict) and res.get("resourceType") == rtype:
            out.append(res)
    return out


def _rebase_offset() -> timedelta:
    """Return the timedelta that shifts the bundle's most-recent sample
    to ``now - _RECENT_OFFSET``.

    Computed every call so successive tool invocations across a single
    process always anchor to "now" — important for long-running agent
    deployments where the cache may persist for hours.
    """
    _load_pt007_bundle()  # ensures _MAX_OBS_TIME_CACHE is set
    target = datetime.now(UTC) - _RECENT_OFFSET
    base = _MAX_OBS_TIME_CACHE or target
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
