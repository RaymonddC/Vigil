#!/usr/bin/env python3
"""
Vigil FHIR Seeder — generates synthetic FHIR R4 Transaction Bundles for 10
synthetic patients per SYNTHETIC_DATA_SPEC.md and POSTs them to HAPI FHIR.

Usage:
    # Generate + seed HAPI (default)
    python data/seed_hapi.py --fhir-base http://localhost:8080/fhir

    # Generate JSON files only (no HAPI POST)
    python data/seed_hapi.py --generate-only --out data/patients

    # Seed from pre-generated files
    python data/seed_hapi.py --fhir-base http://localhost:8080/fhir --src data/patients

Makefile target:
    make seed   →   python data/seed_hapi.py --fhir-base http://localhost:8080/fhir --src data/patients
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

# ── Time constants (anchored to "now" so MCP lookback windows find the data) ──
# The most recent datapoint (T+8h) is placed ~5 min ago so seeding + first
# MCP call always falls inside the 4h/6h windows used by the rule tools.
from datetime import datetime, timedelta, timezone as _tz
_NOW = datetime.now(_tz.utc).replace(microsecond=0)
_T0_DT = _NOW - timedelta(hours=8)   # T+0 is 8 hours ago; T+8 is now
_Z = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731

ENC_START    = _Z(_T0_DT - timedelta(hours=2))   # encounter started 2h before T0
PROC_TIME    = _Z(_T0_DT - timedelta(minutes=30))  # procedure at T-0:30
PREOP_M30    = _Z(_T0_DT - timedelta(minutes=30))
PREOP_M15    = _Z(_T0_DT - timedelta(minutes=15))

TP_TIMES: dict[str, str] = {
    "T0": _Z(_T0_DT),
    "T1": _Z(_T0_DT + timedelta(hours=1)),
    "T2": _Z(_T0_DT + timedelta(hours=2)),
    "T4": _Z(_T0_DT + timedelta(hours=4)),
    "T6": _Z(_T0_DT + timedelta(hours=6)),
    "T8": _Z(_T0_DT + timedelta(hours=8)),
    # T9 — used by per-patient EXTRA_VITAL_OBS / EXTRA_LAB_OBS to surface
    # post-trajectory readings (e.g. PT-007's late SpO2 dip that anchors
    # the opioid_resp_depression treatment-conflict rule).
    "T9": _Z(_T0_DT + timedelta(hours=9)),
}
TP_ORDER = ["T0", "T1", "T2", "T4", "T6", "T8"]
LAB_TPS  = ["T0", "T4", "T8"]

POST_ONSET_PT008 = _Z(_T0_DT + timedelta(hours=4, minutes=15))  # Pip-tazo after sepsis onset
POST_ONSET_PT009 = _Z(_T0_DT + timedelta(hours=4, minutes=20))  # Ampi-sulbactam after sepsis onset

# ── Vital sign tables (§2.1–2.4) ───────────────────────────────────────────────
# Keys: SBP, DBP, HR, RR, SpO2, Temp, Urine  (+EBL for PT-010)
VITALS: dict[str, list[dict]] = {
    "stable": [
        {"SBP": 122, "DBP": 78,  "HR": 74,  "RR": 16, "SpO2": 98, "Temp": 36.8, "Urine": 50},
        {"SBP": 120, "DBP": 76,  "HR": 72,  "RR": 16, "SpO2": 98, "Temp": 36.9, "Urine": 48},
        {"SBP": 118, "DBP": 75,  "HR": 74,  "RR": 15, "SpO2": 99, "Temp": 37.0, "Urine": 52},
        {"SBP": 121, "DBP": 77,  "HR": 76,  "RR": 16, "SpO2": 98, "Temp": 37.0, "Urine": 45},
        {"SBP": 119, "DBP": 76,  "HR": 72,  "RR": 15, "SpO2": 98, "Temp": 36.9, "Urine": 50},
        {"SBP": 120, "DBP": 78,  "HR": 74,  "RR": 16, "SpO2": 99, "Temp": 37.1, "Urine": 48},
    ],
    "deteriorating": [
        {"SBP": 130, "DBP": 82,  "HR": 76,  "RR": 16, "SpO2": 98, "Temp": 37.0, "Urine": 50},
        {"SBP": 124, "DBP": 78,  "HR": 84,  "RR": 17, "SpO2": 97, "Temp": 37.1, "Urine": 42},
        {"SBP": 114, "DBP": 72,  "HR": 92,  "RR": 18, "SpO2": 96, "Temp": 37.2, "Urine": 35},
        {"SBP": 102, "DBP": 64,  "HR": 100, "RR": 20, "SpO2": 95, "Temp": 37.3, "Urine": 26},
        {"SBP": 94,  "DBP": 58,  "HR": 108, "RR": 22, "SpO2": 94, "Temp": 37.4, "Urine": 18},
        {"SBP": 88,  "DBP": 54,  "HR": 116, "RR": 23, "SpO2": 93, "Temp": 37.5, "Urine": 12},
    ],
    "sepsis": [
        {"SBP": 120, "DBP": 76,  "HR": 82,  "RR": 16, "SpO2": 98, "Temp": 37.1, "Urine": 48},
        {"SBP": 118, "DBP": 75,  "HR": 90,  "RR": 18, "SpO2": 97, "Temp": 37.6, "Urine": 42},
        {"SBP": 114, "DBP": 72,  "HR": 105, "RR": 22, "SpO2": 96, "Temp": 38.6, "Urine": 34},
        {"SBP": 94,  "DBP": 58,  "HR": 118, "RR": 24, "SpO2": 94, "Temp": 38.8, "Urine": 22},
        {"SBP": 88,  "DBP": 54,  "HR": 124, "RR": 26, "SpO2": 93, "Temp": 39.0, "Urine": 15},
        {"SBP": 84,  "DBP": 52,  "HR": 128, "RR": 28, "SpO2": 92, "Temp": 39.1, "Urine": 10},
    ],
    "pph": [
        {"SBP": 118, "DBP": 74,  "HR": 84,  "RR": 16, "SpO2": 99, "Temp": 36.9, "Urine": 45, "EBL": 300},
        {"SBP": 108, "DBP": 68,  "HR": 104, "RR": 18, "SpO2": 98, "Temp": 36.8, "Urine": 30, "EBL": 650},
        {"SBP": 88,  "DBP": 52,  "HR": 124, "RR": 22, "SpO2": 96, "Temp": 36.6, "Urine": 18, "EBL": 1200},
        {"SBP": 82,  "DBP": 48,  "HR": 132, "RR": 24, "SpO2": 94, "Temp": 36.4, "Urine":  8, "EBL": 1800},
        {"SBP": 86,  "DBP": 50,  "HR": 128, "RR": 22, "SpO2": 95, "Temp": 36.5, "Urine": 12, "EBL": 2000},
        {"SBP": 92,  "DBP": 56,  "HR": 116, "RR": 20, "SpO2": 97, "Temp": 36.6, "Urine": 22, "EBL": 2050},
    ],
}

# ── Lab value tables (§2.5, drawn at T0/T4/T8 only) ───────────────────────────
LABS: dict[str, list[dict]] = {
    "stable": [
        {"Lactate": 1.2, "WBC": 8.1,  "Cr": 0.9, "Bili": 0.6, "Plt": 240},
        {"Lactate": 1.3, "WBC": 8.4,  "Cr": 0.9, "Bili": 0.7, "Plt": 232},
        {"Lactate": 1.2, "WBC": 8.0,  "Cr": 0.9, "Bili": 0.6, "Plt": 238},
    ],
    "deteriorating": [
        {"Lactate": 1.5, "WBC": 9.2,  "Cr": 1.0, "Bili": 0.7, "Plt": 220},
        {"Lactate": 2.1, "WBC": 11.6, "Cr": 1.2, "Bili": 0.8, "Plt": 198},
        {"Lactate": 2.8, "WBC": 14.2, "Cr": 1.5, "Bili": 1.0, "Plt": 175},
    ],
    "sepsis": [
        {"Lactate": 1.8, "WBC": 10.5, "Cr": 0.9, "Bili": 0.7, "Plt": 215},
        {"Lactate": 4.2, "WBC": 18.4, "Cr": 1.4, "Bili": 1.1, "Plt": 140},
        {"Lactate": 5.8, "WBC": 21.1, "Cr": 1.9, "Bili": 1.6, "Plt":  98},
    ],
    "pph": [
        {"Lactate": 1.6, "WBC": 11.2, "Cr": 0.8, "Bili": 0.6, "Plt": 225, "Hgb": 12.4},
        {"Lactate": 3.2, "WBC": 13.8, "Cr": 1.0, "Bili": 0.7, "Plt": 185, "Hgb":  7.2},
        {"Lactate": 2.4, "WBC": 12.4, "Cr": 0.9, "Bili": 0.7, "Plt": 192, "Hgb":  9.8},
    ],
}

# ── Nursing note text (§3) — indexed by trajectory then timepoint index ────────
NOTES: dict[str, list[str]] = {
    "stable": [
        "Pt A&Ox3, vitals WNL, pain 2/10 controlled with PO. IV site intact.",
        "Resting comfortably, tolerating ice chips. No c/o.",
        "Ambulated to chair, tolerated well. Pain 3/10.",
        "Lunch 75% intake, voided 400mL clear. Pain 2/10.",
        "Family at bedside, conversing appropriately. No distress.",
        "Preparing for overnight, pain controlled, vitals stable.",
    ],
    "deteriorating": [
        "Pt alert and oriented, vitals stable, pain 3/10, dressing dry.",
        "Pain 4/10, mildly anxious. Dressing dry. HR slightly up.",
        "Pt reports 'just doesn't feel right', pain 5/10. Slight pallor noted.",
        "Pt increasingly restless, pain now 6/10, skin cool to touch. UO trending down.",
        "Diaphoretic, pain 7/10 despite dose. Abdomen tender. Cap refill 3s.",
        "Lethargic, responds slowly. Extremities cool and mottled. UO minimal.",
    ],
    "sepsis": [
        "Postpartum Day 0 / POD 0. Vitals stable, lochia moderate rubra, incision CDI.",
        "Pt reports mild chills, requested extra blanket. Temp trending up.",
        "Pt reports chills, says 'feeling off'. Surgical site warm but no purulence. WBC pending.",
        "Rigors, flushed, HR 118, RR 24. Site erythema expanding. Lactate drawn. MD notified.",
        "Hypotensive despite 1L bolus. Mottled knees. Anuric last hour. Sepsis protocol active.",
        "On levophed, intubation anesthesia bedside. Family notified.",
    ],
    "pph": [
        "Delivery of viable infant, placenta intact, EBL 300 mL. Fundus firm at umbilicus.",
        "Pad saturation noted, fundus boggy — massaged to firm. Patient pale. Pitocin running.",
        "Large clot expressed (~400 mL). BP 88/52, HR 124. Second IV placed. OB at bedside.",
        "To OR for exam under anesthesia. 2 units PRBC transfusing. Bakri balloon placed.",
        "Return from OR, fundus firm, bleeding controlled. Hgb 7.2.",
        "Stable on L&D, 2nd unit PRBC complete, UO improving.",
    ],
}

# ── Patient roster (§1) ────────────────────────────────────────────────────────
PATIENTS: list[dict] = [
    {
        "id": "PT-001", "num": 1, "birth_date": "1978-03-14", "mrn": "MRN-100001",
        "family": "Hopkins", "given": ["Sarah", "L"],
        "procedure_display": "Laparoscopic cholecystectomy",
        "procedure_snomed": "38628009", "gender": "female",
        "trajectory": "stable", "demo_role": "hero",
    },
    {
        "id": "PT-002", "num": 2, "birth_date": "1965-11-02", "mrn": "MRN-100002",
        "family": "Brennan", "given": ["Robert", "J"],
        "procedure_display": "Total knee arthroplasty",
        "procedure_snomed": "57368009", "gender": "male",
        "trajectory": "stable", "demo_role": "filler",
    },
    {
        "id": "PT-003", "num": 3, "birth_date": "1991-07-22", "mrn": "MRN-100003",
        "family": "Reyes", "given": ["Emily"],
        "procedure_display": "Appendicectomy",
        "procedure_snomed": "80146002", "gender": "female",
        "trajectory": "stable", "demo_role": "filler",
    },
    {
        "id": "PT-004", "num": 4, "birth_date": "1954-01-09", "mrn": "MRN-100004",
        "family": "Donovan", "given": ["Frank", "M"],
        "procedure_display": "Open colectomy",
        "procedure_snomed": "44143004", "gender": "male",
        "trajectory": "deteriorating", "demo_role": "filler",
    },
    {
        "id": "PT-005", "num": 5, "birth_date": "1972-05-30", "mrn": "MRN-100005",
        "family": "Mitchell", "given": ["Karen"],
        "procedure_display": "Total hip replacement",
        "procedure_snomed": "52734007", "gender": "female",
        "trajectory": "deteriorating", "demo_role": "filler",
    },
    {
        "id": "PT-006", "num": 6, "birth_date": "1960-09-17", "mrn": "MRN-100006",
        "family": "Klein", "given": ["David", "A"],
        "procedure_display": "Coronary artery bypass graft",
        "procedure_snomed": "36197008", "gender": "male",
        "trajectory": "deteriorating", "demo_role": "filler",
    },
    {
        "id": "PT-007", "num": 7, "birth_date": "1983-12-04", "mrn": "MRN-100007",
        "family": "Chen", "given": ["Margaret"],
        "procedure_display": "Exploratory laparotomy",
        "procedure_snomed": "47162000", "gender": "female",
        "trajectory": "deteriorating", "demo_role": "hero",
    },
    {
        "id": "PT-008", "num": 8, "birth_date": "1969-06-11", "mrn": "MRN-100008",
        "family": "Russo", "given": ["Anthony"],
        "procedure_display": "Resection of intestine",
        "procedure_snomed": "44460008", "gender": "male",
        "trajectory": "sepsis", "demo_role": "filler",
    },
    {
        "id": "PT-009", "num": 9, "birth_date": "1994-02-28", "mrn": "MRN-100009",
        "family": "Williams", "given": ["Linda"],
        "procedure_display": "Cesarean section",
        "procedure_snomed": "11466000", "gender": "female",
        "trajectory": "sepsis", "demo_role": "hero",
    },
    {
        "id": "PT-010", "num": 10, "birth_date": "1996-08-19", "mrn": "MRN-100010",
        "family": "Patel", "given": ["Maya"],
        "procedure_display": "Normal delivery",
        "procedure_snomed": "3950001", "gender": "female",
        "trajectory": "pph", "demo_role": "hero",
    },
]

# ── Conditions per patient (§5.1.1) ───────────────────────────────────────────
# None for PT-003
CONDITIONS: dict[str, list[tuple[str, str, str]]] = {
    "PT-001": [("59621000",  "Essential hypertension",                    "2023-06-15")],
    "PT-002": [("239873007", "Osteoarthritis of knee",                    "2022-03-10")],
    "PT-003": [],
    "PT-004": [("44054006",  "Type 2 diabetes mellitus",                  "2018-04-20"),
               ("13645005",  "Chronic obstructive pulmonary disease",     "2020-09-05")],
    "PT-005": [("414916001", "Obesity",                                   "2019-01-12"),
               ("59621000",  "Essential hypertension",                    "2021-07-30")],
    "PT-006": [("53741008",  "Coronary artery disease",                   "2015-11-22"),
               ("44054006",  "Type 2 diabetes mellitus",                  "2017-08-14")],
    "PT-007": [("44054006",  "Type 2 diabetes mellitus",                  "2019-05-03"),
               ("433144002", "Chronic kidney disease stage 3",            "2022-02-18")],
    "PT-008": [("44054006",  "Type 2 diabetes mellitus",                  "2016-03-07"),
               ("13645005",  "Chronic obstructive pulmonary disease",     "2018-10-19"),
               ("76571007",  "Previous septicaemia",                      "2024-08-01")],
    "PT-009": [("199223000", "Gestational diabetes mellitus",             "2026-01-15"),
               ("414916001", "Obesity",                                   "2024-05-20"),
               ("11612004",  "Chorioamnionitis",                          "2026-04-14")],
    "PT-010": [("58532003",  "Placenta accreta",                          "2026-03-20"),
               ("200737006", "Previous cesarean section",                 "2024-09-10"),
               ("398254007", "Mild pre-eclampsia",                        "2026-04-01")],
}

# ── Medication administrations per patient (§5.1.2) ───────────────────────────
# Format: (drug_display, rxnorm_code, dose_value, dose_unit, effective_time)
MEDS: dict[str, list[tuple[str, str, float, str, str]]] = {
    "PT-001": [("Cefazolin 1 g IV",                 "309264",  1.0, "g", PREOP_M30)],
    "PT-002": [("Cefazolin 1 g IV",                 "309264",  1.0, "g", PREOP_M30)],
    "PT-003": [("Cefazolin 1 g IV",                 "309264",  1.0, "g", PREOP_M30)],
    "PT-004": [("Cefazolin 1 g IV",                 "309264",  1.0, "g", PREOP_M30)],
    "PT-005": [("Cefazolin 1 g IV",                 "309264",  1.0, "g", PREOP_M30)],
    "PT-006": [("Cefazolin 1 g IV",                 "309264",  1.0, "g", PREOP_M30)],
    "PT-007": [("Cefazolin 1 g IV",                 "309264",  1.0, "g", PREOP_M30),
               # T+8h morphine push — pairs with the active MedicationRequest
               # below so flag_treatment_conflicts.opioid_resp_depression has
               # a recent administration to anchor the 4h post-dose window.
               ("Morphine 4 mg IV",                  "1731341", 4.0, "mg",
                _Z(_T0_DT + timedelta(hours=8)))],
    "PT-008": [("Cefazolin 1 g IV",                 "309264",  1.0, "g", PREOP_M30),
               ("Piperacillin-tazobactam 4.5 g IV", "203134",  4.5, "g", POST_ONSET_PT008)],
    "PT-009": [("Cefazolin 2 g IV",                 "309264",  2.0, "g", PREOP_M15),
               ("Ampicillin-sulbactam 3 g IV",       "1659149", 3.0, "g", POST_ONSET_PT009)],
    "PT-010": [("Cefazolin 2 g IV",                 "309264",  2.0, "g", PREOP_M15)],
}

# ── Active medication orders per patient (§5.1.3 — flag_treatment_conflicts) ──
# Format: (drug_display, rxnorm_code, dose_text, authored_offset_from_T0)
# Each entry becomes an active ``MedicationRequest`` so the treatment-conflict
# rule engine can detect "drug-on-board vs physiology" conflicts. The
# ``authored_offset`` is added to T0 so timing matches the trajectory windows
# (e.g. ibuprofen ordered after the post-op AKI bumps creatinine).
#
# Each MedicationRequest is paired with the rule it lights up on the demo
# trajectory:
#   PT-007  morphine    → opioid_resp_depression  (SpO2 90 / RR 23 at T+8/9)
#   PT-007  metoprolol  → bblocker_brady_hypo     (SBP 88 < 90 at T+8)
#   PT-008  ibuprofen   → nsaid_aki               (KDIGO 2 from Cr 0.9→1.9)
#   PT-008  lisinopril  → ace_arb_hyperk          (K+ 5.7 at T+8, see EXTRA_LAB_OBS)
#   PT-010  enoxaparin  → anticoag_hgb_drop       (Hgb 12.4→7.2)
MED_REQUESTS: dict[str, list[tuple[str, str, str, timedelta]]] = {
    "PT-007": [
        ("Morphine sulfate 4 mg IV q4h prn pain",
         "1731341",
         "4 mg IV q4h prn moderate-severe pain",
         timedelta(hours=8)),
        # β-blocker order on a hypotensive patient — fires
        # bblocker_brady_hypo at warning severity (SBP 88 < 90 but ≥85).
        ("Metoprolol tartrate 25 mg po bid",
         "866427",
         "25 mg po bid — HR/BP control",
         timedelta(hours=7)),
    ],
    "PT-008": [
        ("Ibuprofen 600 mg po q6h prn",
         "5640",
         "600 mg po q6h prn pain — surgical-team standing order",
         timedelta(hours=6)),
        # ACE-I order on a sepsis-trajectory patient with hyperkalemia —
        # fires ace_arb_hyperk at warning severity (K+ 5.7, <6.0).
        ("Lisinopril 10 mg po qd",
         "314076",
         "10 mg po qd — chronic HTN management resumed",
         timedelta(hours=5)),
    ],
    "PT-010": [
        ("Enoxaparin 40 mg subq q24h (VTE prophylaxis)",
         "67108",
         "40 mg subq q24h — postpartum VTE prophylaxis",
         timedelta(hours=7, minutes=30)),
    ],
}

# ── Per-patient extra lab observations (§5.1.4) ───────────────────────────────
# Lab measurements outside the standard trajectory ``LABS`` panel — used to
# pin specific treatment-conflict rule triggers without polluting other
# patients on the same trajectory.
# Format: list of (timepoint_key, lab_key, value)
EXTRA_LAB_OBS: dict[str, list[tuple[str, str, float]]] = {
    # PT-008: K+ baseline + late-trajectory hyperkalemia — anchors
    # ace_arb_hyperk rule.  PT-009 also runs the sepsis trajectory but
    # doesn't get this — keep the K+ scoped here so the postpartum
    # endometritis case stays clean.
    "PT-008": [("T0", "K", 4.5), ("T8", "K", 5.7)],
    # PT-010: fibrinogen trend — hits the PPH stage-3 trigger
    # (assess_pph_severity) at T+8h with fibrinogen 175 mg/dL <200.
    "PT-010": [("T0", "Fibrinogen", 320.0),
               ("T4", "Fibrinogen", 220.0),
               ("T8", "Fibrinogen", 175.0)],
}

# ── Per-patient extra vital observations (§5.1.5) ─────────────────────────────
# Vital readings outside the standard trajectory grid.  Mirrors EXTRA_LAB_OBS
# but for vital-signs category Observations; supports optional nursing notes
# so the trajectory's narrative breadcrumb stays attached.
# Format: list of (timepoint_key, vital_key, value, note_or_None)
EXTRA_VITAL_OBS: dict[str, list[tuple[str, str, float, str | None]]] = {
    # PT-007: T+9h SpO2 dip after the morphine bolus — anchors the
    # opioid_resp_depression rule on the demo trajectory.  Without this
    # the latest SpO2 (T+8h = 93%) sits above the 92% trigger.
    "PT-007": [(
        "T9", "SpO2", 90,
        "SpO2 trending down post-morphine; consider opioid-induced "
        "respiratory depression.",
    )],
}

# ── LOINC + unit maps ──────────────────────────────────────────────────────────
VITAL_LOINC: dict[str, tuple[str, str, str]] = {
    # key: (loinc_code, display, ucum_code)
    "SBP":   ("8480-6",  "Systolic blood pressure",  "mm[Hg]"),
    "DBP":   ("8462-4",  "Diastolic blood pressure", "mm[Hg]"),
    "HR":    ("8867-4",  "Heart rate",               "/min"),
    "RR":    ("9279-1",  "Respiratory rate",         "/min"),
    "SpO2":  ("59408-5", "Oxygen saturation",        "%"),
    "Temp":  ("8310-5",  "Body temperature",         "Cel"),
    "Urine": ("9192-6",  "Urine output",             "mL/h"),
    "EBL":   ("55758-7", "Estimated blood loss",     "mL"),
}

LAB_LOINC: dict[str, tuple[str, str, str]] = {
    "Lactate": ("2524-7",  "Lactate [Moles/volume] in Blood",  "mmol/L"),
    "WBC":     ("6690-2",  "Leukocytes [#/volume] in Blood",   "10*3/uL"),
    "Cr":      ("2160-0",  "Creatinine [Mass/volume] in Serum","mg/dL"),
    "Bili":    ("1975-2",  "Bilirubin.total [Mass/volume]",    "mg/dL"),
    "Plt":     ("777-3",   "Platelets [#/volume] in Blood",    "10*3/uL"),
    "Hgb":     ("718-7",   "Hemoglobin [Mass/volume] in Blood","g/dL"),
    # Potassium — used by EXTRA_LAB_OBS to anchor the ACE-I/ARB +
    # hyperkalemia treatment-conflict rule without polluting the
    # baseline trajectory's panel.
    "K":       ("2823-3",  "Potassium [Moles/volume] in Serum or Plasma",
                "mmol/L"),
    # Fibrinogen — drives PPH stage 3 trigger via the assess_pph_severity
    # rule.  Scoped to PT-010 only via EXTRA_LAB_OBS.
    "Fibrinogen": ("3255-7", "Fibrinogen [Mass/volume] in Platelet poor plasma",
                   "mg/dL"),
}

# ── FHIR resource builders ────────────────────────────────────────────────────

def _vital_category() -> list[dict]:
    return [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                         "code": "vital-signs", "display": "Vital Signs"}]}]


def _lab_category() -> list[dict]:
    return [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                         "code": "laboratory", "display": "Laboratory"}]}]


def _clin_status(code: str = "active") -> dict:
    return {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                        "code": code}]}


def _ver_status(code: str = "confirmed") -> dict:
    return {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                        "code": code}]}


def make_patient(pt: dict) -> dict:
    """Build a FHIR R4 Patient with realistic names + Vigil demo-role extension.

    The name fields come from the per-patient ``family`` and ``given`` keys
    in PATIENTS so PO's picker shows clinically plausible names rather than
    ``Synthetic Patient 7``. The trajectory + demo-role are surfaced as a
    Vigil-namespaced Extension so the picker's detail panel (and any
    Vigil-aware UI) can show ``Postop deterioration (hero)`` next to the
    name — without polluting the FHIR Identifier / Name fields a real EHR
    would index on.
    """
    family = pt.get("family", "Patient")
    given = pt.get("given") or ["Synthetic", str(pt["num"])]
    full_text = f"{' '.join(given)} {family}".strip()

    return {
        "resourceType": "Patient",
        "id": pt["id"],
        "identifier": [{"system": "http://vigil.local/mrn", "value": pt["mrn"]}],
        "name": [{
            "use": "official",
            "family": family,
            "given": given,
            "text": full_text,
        }],
        "gender": pt["gender"],
        "birthDate": pt["birth_date"],
        # Vigil-namespaced extension so PO's detail panel (and any
        # Vigil-aware UI) can show the trajectory + demo role alongside
        # the name. Out of band of FHIR core fields — won't interfere
        # with US Core compliance.
        "extension": [
            {
                "url": "http://vigil.local/fhir/StructureDefinition/demo-trajectory",
                "valueString": pt["trajectory"],
            },
            {
                "url": "http://vigil.local/fhir/StructureDefinition/demo-role",
                "valueString": pt["demo_role"],
            },
        ],
    }


def make_encounter(pt: dict) -> dict:
    return {
        "resourceType": "Encounter",
        "id": f"ENC-{pt['id']}",
        "status": "in-progress",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                  "code": "IMP", "display": "inpatient encounter"},
        "type": [{"coding": [{"system": "http://snomed.info/sct", "code": "8715000",
                               "display": "Hospital admission for surgical procedure"}]}],
        "subject": {"reference": f"Patient/{pt['id']}"},
        "period": {"start": ENC_START},
    }


def make_procedure(pt: dict) -> dict:
    return {
        "resourceType": "Procedure",
        "id": f"PROC-{pt['id']}",
        "status": "completed",
        "code": {"coding": [{"system": "http://snomed.info/sct",
                              "code": pt["procedure_snomed"],
                              "display": pt["procedure_display"]}]},
        "subject": {"reference": f"Patient/{pt['id']}"},
        "encounter": {"reference": f"Encounter/ENC-{pt['id']}"},
        "performedDateTime": PROC_TIME,
    }


def make_vital_obs(pt_id: str, tp: str, vital_key: str, value: float,
                   note_text: str | None = None) -> dict:
    loinc, display, ucum = VITAL_LOINC[vital_key]
    obs: dict[str, Any] = {
        "resourceType": "Observation",
        "id": f"OBS-{pt_id}-{tp}-{vital_key}",
        "status": "final",
        "category": _vital_category(),
        "code": {"coding": [{"system": "http://loinc.org", "code": loinc, "display": display}],
                 "text": vital_key},
        "subject": {"reference": f"Patient/{pt_id}"},
        "encounter": {"reference": f"Encounter/ENC-{pt_id}"},
        "effectiveDateTime": TP_TIMES[tp],
        "valueQuantity": {"value": value, "unit": ucum,
                          "system": "http://unitsofmeasure.org", "code": ucum},
    }
    if note_text:
        obs["note"] = [{"text": note_text}]
    return obs


def make_nursing_note_doc(
    pt_id: str, tp: str, idx: int, note_text: str
) -> dict:
    """Emit a FHIR DocumentReference carrying one nursing note.

    Why a DocumentReference and not just Observation.note: some FHIR
    importers (notably Prompt Opinion's data-import pipeline at the time
    of writing) strip the inline ``Observation.note`` array on ingest.
    Free-text clinical notes are conventionally carried as
    DocumentReference resources in production EHRs anyway — this is the
    more portable representation.

    Type-coded LOINC 11506-3 ("Progress note") so a real ward EHR
    surfaces it in the right tab. content[].attachment.data carries the
    base64-encoded note text per FHIR R4.
    """
    import base64
    encoded = base64.b64encode(note_text.encode("utf-8")).decode("ascii")
    return {
        "resourceType": "DocumentReference",
        "id": f"DOC-{pt_id}-{tp}-NOTE-{idx}",
        "status": "current",
        "docStatus": "final",
        "type": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "11506-3",
                    "display": "Subsequent evaluation note",
                }
            ],
            "text": "Nursing progress note",
        },
        "category": [
            {
                "coding": [
                    {
                        "system": "http://hl7.org/fhir/us/core/CodeSystem/us-core-documentreference-category",
                        "code": "clinical-note",
                        "display": "Clinical Note",
                    }
                ]
            }
        ],
        "subject": {"reference": f"Patient/{pt_id}"},
        "date": TP_TIMES[tp],
        "author": [
            {
                "type": "PractitionerRole",
                "display": "Ward nurse (synthetic, no PHI)",
            }
        ],
        "content": [
            {
                "attachment": {
                    "contentType": "text/plain",
                    "data": encoded,
                    "title": f"Nursing note T{tp}",
                    "creation": TP_TIMES[tp],
                }
            }
        ],
        "context": {
            "encounter": [{"reference": f"Encounter/ENC-{pt_id}"}],
            "period": {"start": TP_TIMES[tp]},
        },
    }


def make_lab_obs(pt_id: str, tp: str, lab_key: str, value: float) -> dict:
    loinc, display, ucum = LAB_LOINC[lab_key]
    return {
        "resourceType": "Observation",
        "id": f"OBS-{pt_id}-{tp}-{lab_key}",
        "status": "final",
        "category": _lab_category(),
        "code": {"coding": [{"system": "http://loinc.org", "code": loinc, "display": display}],
                 "text": lab_key},
        "subject": {"reference": f"Patient/{pt_id}"},
        "encounter": {"reference": f"Encounter/ENC-{pt_id}"},
        "effectiveDateTime": TP_TIMES[tp],
        "valueQuantity": {"value": value, "unit": ucum,
                          "system": "http://unitsofmeasure.org", "code": ucum},
    }


def make_condition(pt_id: str, snomed: str, display: str,
                   recorded_date: str, cond_idx: int) -> dict:
    return {
        "resourceType": "Condition",
        "id": f"COND-{pt_id}-{cond_idx}",
        "clinicalStatus": _clin_status("active"),
        "verificationStatus": _ver_status("confirmed"),
        "code": {"coding": [{"system": "http://snomed.info/sct",
                              "code": snomed, "display": display}]},
        "subject": {"reference": f"Patient/{pt_id}"},
        "recordedDate": recorded_date,
    }


def make_med_admin(pt_id: str, drug_display: str, rxnorm: str,
                   dose_val: float, dose_unit: str,
                   effective_time: str, med_idx: int) -> dict:
    return {
        "resourceType": "MedicationAdministration",
        "id": f"MEDADMIN-{pt_id}-{med_idx}",
        "status": "completed",
        "medicationCodeableConcept": {
            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                        "code": rxnorm, "display": drug_display}]
        },
        "subject": {"reference": f"Patient/{pt_id}"},
        "effectiveDateTime": effective_time,
        "dosage": {
            "dose": {"value": dose_val, "unit": dose_unit,
                     "system": "http://unitsofmeasure.org", "code": dose_unit},
            "route": {"coding": [{"system": "http://snomed.info/sct",
                                   "code": "47625008", "display": "Intravenous route"}]},
        },
    }


def make_med_request(pt_id: str, drug_display: str, rxnorm: str,
                     dosage_text: str, authored_time: str,
                     req_idx: int) -> dict:
    """Build an active MedicationRequest used by flag_treatment_conflicts.

    Active orders are the forward-looking signal the engine wants — they
    represent drugs the team is about to give, not just ones already in
    the bloodstream.  ``status="active"`` and ``intent="order"`` are
    required for ``_active_requests`` in the rule engine to pick it up.
    """
    return {
        "resourceType": "MedicationRequest",
        "id": f"MEDREQ-{pt_id}-{req_idx}",
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                        "code": rxnorm, "display": drug_display}],
            "text": drug_display,
        },
        "subject": {"reference": f"Patient/{pt_id}"},
        "authoredOn": authored_time,
        "dosageInstruction": [{"text": dosage_text}],
    }


# ── Bundle assembly ───────────────────────────────────────────────────────────

def _entry(resource: dict) -> dict:
    rt = resource["resourceType"]
    rid = resource["id"]
    return {
        "fullUrl": f"urn:uuid:{rt}-{rid}",
        "resource": resource,
        "request": {"method": "PUT", "url": f"{rt}/{rid}"},
    }


def build_patient_bundle(pt: dict) -> dict:
    """Generate a complete FHIR R4 Transaction Bundle for one patient."""
    traj   = pt["trajectory"]
    pt_id  = pt["id"]
    vitals = VITALS[traj]
    labs   = LABS[traj]
    notes  = NOTES[traj]

    entries: list[dict] = []

    # Core resources
    entries.append(_entry(make_patient(pt)))
    entries.append(_entry(make_encounter(pt)))
    entries.append(_entry(make_procedure(pt)))

    # Vital observations (6 timepoints × 7 vitals)
    vital_keys = ["SBP", "DBP", "HR", "RR", "SpO2", "Temp", "Urine"]
    if traj == "pph":
        vital_keys.append("EBL")

    for i, tp in enumerate(TP_ORDER):
        row = vitals[i]
        note = notes[i]
        for vk in vital_keys:
            if vk not in row:
                continue
            # Attach nursing note to Urine observation only — inline
            # form, for FHIR servers that surface Observation.note.
            n = note if vk == "Urine" else None
            entries.append(_entry(make_vital_obs(pt_id, tp, vk, row[vk], n)))
        # Also emit the nursing note as a standalone DocumentReference
        # so importers that strip Observation.note (Prompt Opinion does)
        # still expose the free text. Vigil's read_nursing_signals
        # handler reads BOTH paths and dedupes.
        entries.append(_entry(make_nursing_note_doc(pt_id, tp, i, note)))

    # Lab observations (T0, T4, T8 only)
    for j, tp in enumerate(LAB_TPS):
        lab_row = labs[j]
        for lk, val in lab_row.items():
            entries.append(_entry(make_lab_obs(pt_id, tp, lk, val)))

    # Per-patient extra lab observations (e.g. K+ for PT-008's ACE-I/hyperK
    # rule, fibrinogen for PT-010's PPH stage-3 trigger). Kept separate
    # from the trajectory panel so each rule fixture stays scoped to the
    # patient that actually needs it.
    for tp_key, lk, val in EXTRA_LAB_OBS.get(pt_id, []):
        entries.append(_entry(make_lab_obs(pt_id, tp_key, lk, val)))

    # Per-patient extra vital observations (e.g. PT-007's T+9h SpO2 dip
    # that lights up the opioid_resp_depression conflict rule).
    for tp_key, vk, val, note in EXTRA_VITAL_OBS.get(pt_id, []):
        entries.append(_entry(make_vital_obs(pt_id, tp_key, vk, val, note)))

    # Conditions
    for cidx, (snomed, display, rec_date) in enumerate(CONDITIONS.get(pt_id, [])):
        entries.append(_entry(make_condition(pt_id, snomed, display, rec_date, cidx + 1)))

    # Medication administrations
    for midx, (drug, rxnorm, dose_val, dose_unit, eff_time) in enumerate(
        MEDS.get(pt_id, [])
    ):
        entries.append(_entry(make_med_admin(pt_id, drug, rxnorm, dose_val,
                                             dose_unit, eff_time, midx + 1)))

    # Medication requests (active orders — used by flag_treatment_conflicts)
    for ridx, (drug, rxnorm, dosage_text, authored_offset) in enumerate(
        MED_REQUESTS.get(pt_id, [])
    ):
        authored_time = _Z(_T0_DT + authored_offset)
        entries.append(_entry(make_med_request(pt_id, drug, rxnorm,
                                               dosage_text, authored_time,
                                               ridx + 1)))

    return {
        "resourceType": "Bundle",
        "id": f"BUNDLE-{pt_id}",
        "type": "transaction",
        "timestamp": "2026-04-15T10:00:00Z",
        "entry": entries,
    }


def generate_all_bundles() -> dict[str, dict]:
    return {pt["id"]: build_patient_bundle(pt) for pt in PATIENTS}


# ── I/O helpers ───────────────────────────────────────────────────────────────

def save_bundles(bundles: dict[str, dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for pt_id, bundle in bundles.items():
        path = out_dir / f"{pt_id}.json"
        path.write_text(json.dumps(bundle, indent=2))
        print(f"  wrote {path}")

    # Write index
    index = [
        {"patient_id": pt["id"], "mrn": pt["mrn"], "trajectory": pt["trajectory"],
         "demo_role": pt["demo_role"], "file": f"{pt['id']}.json"}
        for pt in PATIENTS
    ]
    (out_dir / "_index.json").write_text(json.dumps({"patients": index}, indent=2))
    print(f"  wrote {out_dir / '_index.json'}")


def load_bundles(src_dir: Path) -> dict[str, dict]:
    bundles: dict[str, dict] = {}
    for pt in PATIENTS:
        path = src_dir / f"{pt['id']}.json"
        if path.exists():
            bundles[pt["id"]] = json.loads(path.read_text())
        else:
            print(f"  [WARN] {path} not found — generating on the fly")
            bundles[pt["id"]] = build_patient_bundle(pt)
    return bundles


# ── HAPI seeding ──────────────────────────────────────────────────────────────

def seed_hapi(bundles: dict[str, dict], fhir_base: str, *, retries: int = 3) -> bool:
    try:
        import httpx  # noqa: PLC0415
    except ImportError:
        print("ERROR: httpx not installed. Run: uv add httpx", file=sys.stderr)
        return False

    fhir_base = fhir_base.rstrip("/")
    ok = True

    for pt_id, bundle in bundles.items():
        url = f"{fhir_base}"
        for attempt in range(1, retries + 1):
            try:
                r = httpx.post(
                    url,
                    json=bundle,
                    headers={"Content-Type": "application/fhir+json",
                             "Accept": "application/fhir+json"},
                    timeout=60.0,
                )
                if r.status_code in (200, 201):
                    print(f"  [OK]  {pt_id} → HTTP {r.status_code}")
                    break
                else:
                    print(f"  [ERR] {pt_id} attempt {attempt}: HTTP {r.status_code}")
                    print(f"        {r.text[:300]}")
                    if attempt == retries:
                        ok = False
            except httpx.RequestError as exc:
                print(f"  [ERR] {pt_id} attempt {attempt}: {exc}")
                if attempt < retries:
                    time.sleep(2)
                else:
                    ok = False

    return ok


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and/or seed HAPI FHIR with synthetic Vigil patients."
    )
    parser.add_argument("--fhir-base", default="",
                        help="HAPI FHIR base URL (e.g. http://localhost:8080/fhir). "
                             "Required unless --generate-only is set.")
    parser.add_argument("--src", default="data/patients",
                        help="Directory to read pre-generated bundles from (default: data/patients)")
    parser.add_argument("--out", default="",
                        help="Directory to write generated bundles to "
                             "(defaults to --src if not set)")
    parser.add_argument("--generate-only", action="store_true",
                        help="Generate JSON files without POSTing to HAPI")
    parser.add_argument("--no-generate", action="store_true",
                        help="Skip generation; read from --src only")

    args = parser.parse_args()

    src_dir = Path(args.src)
    out_dir = Path(args.out) if args.out else src_dir

    if not args.fhir_base and not args.generate_only:
        parser.error("--fhir-base is required unless --generate-only is set")

    # Step 1: generate bundles
    if args.no_generate and src_dir.exists():
        print(f"Loading pre-generated bundles from {src_dir} …")
        bundles = load_bundles(src_dir)
    else:
        print("Generating FHIR R4 Transaction Bundles …")
        bundles = generate_all_bundles()
        print(f"Saving to {out_dir} …")
        save_bundles(bundles, out_dir)

    if args.generate_only:
        print(f"\nDone — {len(bundles)} bundles saved. HAPI not seeded.")
        return 0

    # Step 2: seed HAPI
    print(f"\nSeeding HAPI at {args.fhir_base} …")
    success = seed_hapi(bundles, args.fhir_base)

    if success:
        print(f"\nAll {len(bundles)} patients seeded successfully.")
        return 0
    else:
        print("\nOne or more patients failed to seed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
