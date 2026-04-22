"""
Vigil FHIR Fixture Server (KS-2 fallback).

A lightweight FastAPI application that serves pre-generated FHIR R4 data
from ``data/patients/`` matching HAPI FHIR's response shapes.  Swap in by
setting ``FHIR_BACKEND=fixture`` — the FHIR client then targets
``http://localhost:8080/fhir`` which this server answers instead of HAPI.

Endpoints mirror HAPI's search/read interface:
    GET /fhir/metadata
    GET /fhir/Patient
    GET /fhir/Patient/{id}
    GET /fhir/Observation            ?patient=&category=
    GET /fhir/Condition              ?patient=
    GET /fhir/MedicationAdministration ?patient=
    GET /fhir/Encounter              ?patient=
    GET /fhir/Procedure              ?patient=

All search endpoints return FHIR R4 ``searchset`` Bundles identical in shape
to HAPI responses (``fullUrl``, ``search.mode="match"``, ``total`` count).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

# ── Configuration ──────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(os.getenv("FIXTURE_DATA_DIR", str(_REPO_ROOT / "data" / "patients")))
FHIR_BASE = os.getenv("FIXTURE_BASE_URL", "http://localhost:8080/fhir")

# ── In-memory resource index ───────────────────────────────────────────────────
# Populated at startup from all PT-*.json transaction bundles.
# Structure: {resource_type: {resource_id: resource_dict}}

_index: dict[str, dict[str, dict]] = {}

# Seed T0 anchor — recovered from the earliest MedicationAdministration
# timestamp at load time.  Pre-op prophylaxis (cefazolin) is administered
# at T0 − 30 min, so:  seed_T0 = min(MedAdmin.effectiveDateTime) + 30 min.
# Used by _rebase_medadmin() to shift timestamps to the CURRENT monitoring
# window (now − 8 h) at request time, keeping integration tests deterministic
# regardless of the date the fixture files were generated.
# (Vigil fixture operational choice — mirrors the Observation endpoint's design
# philosophy of returning all data irrespective of the tool's lookback window.)
_seed_t0: datetime | None = None


def _load_bundles() -> None:
    """Parse all PT-*.json bundles and index resources by type and id."""
    global _seed_t0
    _index.clear()
    files = sorted(DATA_DIR.glob("PT-*.json"))
    if not files:
        # Gracefully start with empty store; seed later
        return
    for path in files:
        bundle = json.loads(path.read_text())
        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {})
            rt = resource.get("resourceType")
            rid = resource.get("id")
            if rt and rid:
                _index.setdefault(rt, {})[rid] = resource

    # Recover seed T0 from the earliest MedAdmin timestamp.
    # All patients receive pre-op cefazolin at T0 − 30 min; the minimum
    # effectiveDateTime across all MedicationAdministrations is therefore
    # seed_T0 − 30 min, giving us seed_T0 = min_time + 30 min.
    min_time: datetime | None = None
    for resource in _index.get("MedicationAdministration", {}).values():
        ts_str = resource.get("effectiveDateTime", "")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if min_time is None or ts < min_time:
                    min_time = ts
            except ValueError:
                pass
    _seed_t0 = (min_time + timedelta(minutes=30)) if min_time is not None else None


# ── FastAPI app ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Vigil FHIR Fixture Server",
    description="Serves static FHIR R4 data from data/patients/ matching HAPI response shapes.",
    version="0.1.0",
)


@app.on_event("startup")
def _startup() -> None:
    _load_bundles()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _full_url(resource_type: str, resource_id: str) -> str:
    return f"{FHIR_BASE}/{resource_type}/{resource_id}"


def _searchset(resources: list[dict]) -> dict[str, Any]:
    entries = [
        {
            "fullUrl": _full_url(r["resourceType"], r["id"]),
            "resource": r,
            "search": {"mode": "match"},
        }
        for r in resources
    ]
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(entries),
        "link": [{"relation": "self", "url": FHIR_BASE}],
        "entry": entries,
    }


def _fhir_json(data: dict) -> JSONResponse:
    return JSONResponse(content=data, media_type="application/fhir+json")


def _patient_ref(resource: dict, patient_id: str) -> bool:
    """True if resource references the given patient id."""
    subj = resource.get("subject", {}).get("reference", "")
    return subj.endswith(f"/{patient_id}") or subj == patient_id


def _resources_for_patient(resource_type: str, patient_id: str) -> list[dict]:
    return [
        r for r in _index.get(resource_type, {}).values()
        if _patient_ref(r, patient_id)
    ]


def _rebase_medadmin(resource: dict) -> dict:
    """Shift a MedicationAdministration's effectiveDateTime to the current window.

    The seed data fixes all timestamps relative to T0 = seed NOW − 8 h.
    At test time we rebase them to T0 = now − 8 h so that the empiric-window
    filter in flag_sepsis_onset (_ABX_EMPIRIC_WINDOW_HOURS = 6 h) behaves
    identically to production:

      * Pre-op cefazolin at seed T0 − 30 min  →  now − 8.5 h  (> 6 h ago = excluded ✓)
      * Therapeutic ABX at seed T0 + 4–5 h    →  now − 3–4 h  (< 6 h ago = included ✓)

    Rebasing happens at response time (the stored resource is unchanged).
    (Vigil fixture operational choice — mirrors the Observation endpoint's
    "return all rows regardless of date" design so clinical-assertion tests
    are deterministic regardless of the date the fixtures were generated.)
    """
    if _seed_t0 is None:
        return resource
    ts_str = resource.get("effectiveDateTime", "")
    if not ts_str:
        return resource
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        current_t0 = datetime.now(UTC) - timedelta(hours=8)
        delta = current_t0 - _seed_t0
        new_ts = ts + delta
        rebased = dict(resource)
        rebased["effectiveDateTime"] = new_ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        return rebased
    except (ValueError, TypeError):
        return resource


# ── FHIR endpoints ─────────────────────────────────────────────────────────────

@app.get("/fhir/metadata")
def capability_statement() -> JSONResponse:
    """Minimal FHIR CapabilityStatement so HAPI client health checks pass."""
    cs = {
        "resourceType": "CapabilityStatement",
        "status": "active",
        "fhirVersion": "4.0.1",
        "kind": "instance",
        "software": {"name": "Vigil FHIR Fixture", "version": "0.1.0"},
        "format": ["application/fhir+json"],
        "rest": [
            {
                "mode": "server",
                "resource": [
                    {"type": rt, "interaction": [{"code": "read"}, {"code": "search-type"}]}
                    for rt in ["Patient", "Observation", "Condition",
                               "MedicationAdministration", "Encounter", "Procedure"]
                ],
            }
        ],
    }
    return _fhir_json(cs)


@app.get("/fhir/Patient")
def search_patients() -> JSONResponse:
    """Return all patients as a searchset Bundle."""
    patients = list(_index.get("Patient", {}).values())
    return _fhir_json(_searchset(patients))


@app.get("/fhir/Patient/{patient_id}")
def read_patient(patient_id: str) -> JSONResponse:
    """Return a single Patient resource."""
    resource = _index.get("Patient", {}).get(patient_id)
    if resource is None:
        raise HTTPException(status_code=404, detail=f"Patient/{patient_id} not found")
    return _fhir_json(resource)


@app.get("/fhir/Observation")
def search_observations(
    patient: str = Query(default=""),
    category: str = Query(default=""),
    _sort: str = Query(alias="_sort", default="-date"),
    _count: int = Query(alias="_count", default=200),
) -> JSONResponse:
    """Return observations filtered by patient and optional category."""
    if not patient:
        # Return all observations (large — only used for debugging)
        obs = list(_index.get("Observation", {}).values())
    else:
        obs = _resources_for_patient("Observation", patient)

    if category:
        # Filter by category code (e.g. "vital-signs" or "laboratory")
        filtered = []
        for o in obs:
            cats = o.get("category", [])
            for cat in cats:
                codes = [c.get("code") for c in cat.get("coding", [])]
                if category in codes:
                    filtered.append(o)
                    break
        obs = filtered

    # Stable sort: newest first
    obs.sort(key=lambda o: o.get("effectiveDateTime", ""), reverse=True)
    obs = obs[:_count]

    return _fhir_json(_searchset(obs))


@app.get("/fhir/Condition")
def search_conditions(patient: str = Query(default="")) -> JSONResponse:
    """Return conditions for a patient."""
    if not patient:
        resources = list(_index.get("Condition", {}).values())
    else:
        resources = _resources_for_patient("Condition", patient)
    return _fhir_json(_searchset(resources))


@app.get("/fhir/MedicationAdministration")
def search_medication_administrations(patient: str = Query(default="")) -> JSONResponse:
    """Return medication administrations for a patient.

    Timestamps are rebased to the current monitoring window (now − 8 h) so
    that the empiric-window filter in flag_sepsis_onset works correctly
    regardless of when the fixture files were generated.  See _rebase_medadmin.
    """
    if not patient:
        resources = list(_index.get("MedicationAdministration", {}).values())
    else:
        resources = _resources_for_patient("MedicationAdministration", patient)
    # Rebase to current T0 so pre-op prophylaxis stays outside the empiric
    # window and therapeutic antibiotics fall inside it. (Vigil fixture op.)
    resources = [_rebase_medadmin(r) for r in resources]
    return _fhir_json(_searchset(resources))


@app.get("/fhir/Encounter")
def search_encounters(patient: str = Query(default="")) -> JSONResponse:
    """Return encounters for a patient."""
    if not patient:
        resources = list(_index.get("Encounter", {}).values())
    else:
        resources = _resources_for_patient("Encounter", patient)
    return _fhir_json(_searchset(resources))


@app.get("/fhir/Procedure")
def search_procedures(patient: str = Query(default="")) -> JSONResponse:
    """Return procedures for a patient."""
    if not patient:
        resources = list(_index.get("Procedure", {}).values())
    else:
        resources = _resources_for_patient("Procedure", patient)
    return _fhir_json(_searchset(resources))


# ── Hot-reload endpoint (same as make seed for fixture) ───────────────────────

@app.post("/fhir/_reload")
def reload_fixtures() -> dict[str, Any]:
    """Re-read data/patients/ from disk (equivalent to make seed for the fixture)."""
    _load_bundles()
    counts = {rt: len(ids) for rt, ids in _index.items()}
    return {"status": "ok", "loaded": counts}
