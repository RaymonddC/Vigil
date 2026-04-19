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


def _load_bundles() -> None:
    """Parse all PT-*.json bundles and index resources by type and id."""
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
    """Return medication administrations for a patient."""
    if not patient:
        resources = list(_index.get("MedicationAdministration", {}).values())
    else:
        resources = _resources_for_patient("MedicationAdministration", patient)
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
