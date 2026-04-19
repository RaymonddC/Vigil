# SYNTHETIC_DATA_SPEC.md

**Project:** Vigil — Agents Assemble Hackathon (Option B)
**Date:** 2026-04-15
**Scope:** 10 synthetic FHIR R4 patients × 6 timepoints × 4 trajectories. Zero real PHI.

---

## 1. Patient Roster

| patient_id | name                 | birthDate   | MRN        | procedure                        | trajectory              | demo role |
|------------|----------------------|-------------|------------|----------------------------------|-------------------------|-----------|
| PT-001     | Synthetic Patient 1  | 1978-03-14  | MRN-100001 | Lap cholecystectomy              | stable                  | hero      |
| PT-002     | Synthetic Patient 2  | 1965-11-02  | MRN-100002 | Total knee arthroplasty          | stable                  | filler    |
| PT-003     | Synthetic Patient 3  | 1991-07-22  | MRN-100003 | Appendectomy                     | stable                  | filler    |
| PT-004     | Synthetic Patient 4  | 1954-01-09  | MRN-100004 | Open colectomy                   | deteriorating           | filler    |
| PT-005     | Synthetic Patient 5  | 1972-05-30  | MRN-100005 | Hip arthroplasty                 | deteriorating           | filler    |
| PT-006     | Synthetic Patient 6  | 1960-09-17  | MRN-100006 | CABG                             | deteriorating           | filler    |
| PT-007     | Synthetic Patient 7  | 1983-12-04  | MRN-100007 | Exploratory laparotomy           | deteriorating           | hero      |
| PT-008     | Synthetic Patient 8  | 1969-06-11  | MRN-100008 | Bowel resection                  | sepsis_onset (postop)   | filler    |
| PT-009     | Synthetic Patient 9  | 1994-02-28  | MRN-100009 | C-section                        | sepsis_onset (postpartum) | hero    |
| PT-010     | Synthetic Patient 10 | 1996-08-19  | MRN-100010 | Vaginal delivery                 | postpartum hemorrhage   | hero      |

**Final roster counts:** 3 stable (PT-001..003) / 4 deteriorating (PT-004..007, PT-007 is the hero) / 2 sepsis (PT-008 postop, PT-009 postpartum) / 1 postpartum hemorrhage (PT-010). Total = 10 per `PROJECT_BRIEF.md:58`. PT-001, PT-007, PT-009, PT-010 are the on-camera heroes.

Note: the earlier draft added a PT-011 second hemorrhage case — dropped to keep the roster at exactly 10. The maternal cameo needs only one hemorrhage trajectory fired on screen (DEMO_SCRIPT 2:15 beat is a *flash*, not a deep dive), so 1 hemorrhage patient is sufficient.

---

## 2. Per-Trajectory Vital Sign Tables

Columns: SBP / DBP (mmHg), HR (bpm), RR (/min), SpO2 (%), Temp (°C), Urine (mL/hr).

### 2.1 Stable (PT-001, PT-002, PT-003)

| Timepoint | SBP | DBP | HR | RR | SpO2 | Temp | Urine |
|-----------|-----|-----|----|----|------|------|-------|
| T+0h      | 122 | 78  | 74 | 16 | 98   | 36.8 | 50    |
| T+1h      | 120 | 76  | 72 | 16 | 98   | 36.9 | 48    |
| T+2h      | 118 | 75  | 74 | 15 | 99   | 37.0 | 52    |
| T+4h      | 121 | 77  | 76 | 16 | 98   | 37.0 | 45    |
| T+6h      | 119 | 76  | 72 | 15 | 98   | 36.9 | 50    |
| T+8h      | 120 | 78  | 74 | 16 | 99   | 37.1 | 48    |

All values within MEWT "no trigger" zone.

### 2.2 Deteriorating (PT-004, PT-005, PT-006, PT-007 hero)

| Timepoint | SBP | DBP | HR | RR | SpO2 | Temp | Urine |
|-----------|-----|-----|----|----|------|------|-------|
| T+0h      | 130 | 82  | 76 | 16 | 98   | 37.0 | 50    |
| T+1h      | 124 | 78  | 84 | 17 | 97   | 37.1 | 42    |
| T+2h      | 114 | 72  | 92 | 18 | 96   | 37.2 | 35    |
| T+4h      | 102 | 64  | 100| 20 | 95   | 37.3 | 26    |
| T+6h      | 94  | 58  | 108| 22 | 94   | 37.4 | 18    |
| T+8h      | 88  | 54  | 116| 23 | 93   | 37.5 | 12    |

Individually each reading at T+2h is "borderline normal" — SBP 114 is not frankly hypotensive, HR 92 is not tachycardia. The **trend** is the signal: **at T+2h, SBP has dropped 12.3% (130 → 114) and HR has risen 21.1% (76 → 92) from T+0h.** Per the hemodynamic trend rule (`CLINICAL_EVIDENCE §2.3`), a ≥10% SBP drop AND ≥15% HR rise over any 2-hour window fires TRIGGERED regardless of absolute values. PT-007 hits the rule precisely at T+2h, advances to HIGH at T+4h (when absolute thresholds also cross: HR ≥100, RR ≥20), and stays HIGH through the window.

### 2.3 Sepsis Onset (PT-008 postop, PT-009 postpartum)

| Timepoint | SBP | DBP | HR  | RR | SpO2 | Temp | Urine |
|-----------|-----|-----|-----|----|------|------|-------|
| T+0h      | 120 | 76  | 82  | 16 | 98   | 37.1 | 48    |
| T+1h      | 118 | 75  | 90  | 18 | 97   | 37.6 | 42    |
| T+2h      | 114 | 72  | 105 | 22 | 96   | 38.6 | 34    |
| T+4h      | 94  | 58  | 118 | 24 | 94   | 38.8 | 22    |
| T+6h      | 88  | 54  | 124 | 26 | 93   | 39.0 | 15    |
| T+8h      | 84  | 52  | 128 | 28 | 92   | 39.1 | 10    |

At T+4h: Temp >38 ✓, HR >90 ✓, RR >20 ✓, suspected infection source (postop/postpartum) ✓ → CDC Adult Sepsis Event + SIRS criteria met. qSOFA = 2 (RR ≥22, SBP ≤100) → EMERGENCY.

### 2.4 Postpartum Hemorrhage (PT-010 hero)

Additional column: EBL (cumulative mL) and fundal tone (firm/boggy).

| Timepoint | SBP | DBP | HR  | RR | SpO2 | Temp | Urine | EBL  | Fundus |
|-----------|-----|-----|-----|----|------|------|-------|------|--------|
| T+0h      | 118 | 74  | 84  | 16 | 99   | 36.9 | 45    | 300  | firm   |
| T+1h      | 108 | 68  | 104 | 18 | 98   | 36.8 | 30    | 650  | boggy  |
| T+2h      | 88  | 52  | 124 | 22 | 96   | 36.6 | 18    | 1200 | boggy  |
| T+4h      | 82  | 48  | 132 | 24 | 94   | 36.4 | 8     | 1800 | boggy  |
| T+6h      | 86  | 50  | 128 | 22 | 95   | 36.5 | 12    | 2000 | firm (post-intervention) |
| T+8h      | 92  | 56  | 116 | 20 | 97   | 36.6 | 22    | 2050 | firm   |

EBL >500 mL (vaginal) at T+1h = primary PPH threshold (RCOG Green-top 52). EBL >1000 mL by T+2h = major PPH → EMERGENCY.

### 2.5 Lab Observations by trajectory and timepoint

Values keyed to trajectory × timepoint. LOINC codes per `CLINICAL_EVIDENCE §11.2`. Units: lactate `mmol/L`, WBC `10*3/uL`, creatinine `mg/dL`, bilirubin `mg/dL`, platelets `10*3/uL`. Labs are drawn only at T+0h, T+4h, and T+8h (no one draws labs every hour). `flag_sepsis_onset`'s evaluation window is 24h so this cadence is sufficient.

#### 2.5.1 Stable (PT-001, PT-002, PT-003)

| Timepoint | Lactate (2524-7) | WBC (6690-2) | Creatinine (2160-0) | Bilirubin (1975-2) | Platelets (777-3) |
|-----------|:---:|:---:|:---:|:---:|:---:|
| T+0h  | 1.2 | 8.1  | 0.9 | 0.6 | 240 |
| T+4h  | 1.3 | 8.4  | 0.9 | 0.7 | 232 |
| T+8h  | 1.2 | 8.0  | 0.9 | 0.6 | 238 |

No CDC ASE organ-dysfunction criterion is met at any timepoint. Expected: `flag_sepsis_onset.sepsis_suspected=false, mode="cdc_ase"`.

#### 2.5.2 Deteriorating (PT-004, PT-005, PT-006, PT-007 hero)

| Timepoint | Lactate | WBC  | Creatinine | Bilirubin | Platelets |
|-----------|:---:|:---:|:---:|:---:|:---:|
| T+0h  | 1.5 | 9.2  | 1.0 | 0.7 | 220 |
| T+4h  | 2.1 | 11.6 | 1.2 | 0.8 | 198 |
| T+8h  | 2.8 | 14.2 | 1.5 | 1.0 | 175 |

At T+4h, lactate 2.1 >= 2.0 crosses CDC ASE → `flag_sepsis_onset` returns POSSIBLE with organ-dysfunction criterion `lactate>=2.0`. WBC rise and creatinine drift add evidence by T+8h. Pairs cleanly with the hemodynamic trend rule firing on PT-007 at T+2h (from vitals alone).

#### 2.5.3 Sepsis onset (PT-008 postop, PT-009 postpartum hero)

| Timepoint | Lactate | WBC  | Creatinine | Bilirubin | Platelets |
|-----------|:---:|:---:|:---:|:---:|:---:|
| T+0h  | 1.8 | 10.5 | 0.9 | 0.7 | 215 |
| T+4h  | **4.2** | **18.4** | 1.4 | 1.1 | 140 |
| T+8h  | 5.8 | 21.1 | 1.9 | 1.6 | 98 |

**PT-009 T+4h is the DEMO_SCRIPT PT-009 beat**: `lactate 4.2` satisfies `DEMO_SCRIPT.md:24, 82` "lactate 4.1" narration (within rounding), and `WBC 18.4` satisfies "white count 18". Expected at T+4h: `flag_sepsis_onset.sepsis_suspected=true, mode="cdc_ase"`, criteria_met=["presumed infection (antibiotic started)", "organ dysfunction: lactate 4.2 mmol/L", "organ dysfunction: SBP 94 mmHg" (from §2.3 T+4h vitals)]. At T+8h, platelets 98 < 100 crosses the "platelet drop" criterion as well.

#### 2.5.4 Postpartum hemorrhage (PT-010 hero)

| Timepoint | Lactate | WBC  | Creatinine | Bilirubin | Platelets | Hgb (718-7) |
|-----------|:---:|:---:|:---:|:---:|:---:|:---:|
| T+0h  | 1.6 | 11.2 | 0.8 | 0.6 | 225 | 12.4 |
| T+4h  | 3.2 | 13.8 | 1.0 | 0.7 | 185 | 7.2  |
| T+8h  | 2.4 | 12.4 | 0.9 | 0.7 | 192 | 9.8  |

Hgb added to this trajectory only (LOINC 718-7, unit `g/dL`) because the hemorrhage narrative requires it — Hgb 7.2 at T+4h drives the "2 units PRBC transfusing" note in `SYNTHETIC_DATA_SPEC §3 Postpartum Hemorrhage T+4h`. Lactate >= 2.0 at T+4h also qualifies as ASE organ dysfunction, but `flag_sepsis_onset` returns POSSIBLE (1 criterion, no infection signal — no antibiotic administration + no fever). The dominant alert for PT-010 is still MEWT (absolute thresholds) + the hemorrhage-specific fundal/EBL annotations in §2.4.

**Reference-range sanity check.** All "stable" rows sit strictly inside the reference ranges from `CLINICAL_EVIDENCE §11.2`. All "triggered" rows cross published thresholds (CDC ASE lactate>=2.0, WBC elevated per SIRS, etc.). No value is physiologically impossible; the sepsis progression follows the expected organ-dysfunction sequence (lactate first, then WBC/creatinine/bilirubin, platelets last).

---

## 3. Nursing Note Text Samples

### Stable
- **T+0h:** "Pt A&Ox3, vitals WNL, pain 2/10 controlled with PO. IV site intact."
- **T+1h:** "Resting comfortably, tolerating ice chips. No c/o."
- **T+2h:** "Ambulated to chair, tolerated well. Pain 3/10."
- **T+4h:** "Lunch 75% intake, voided 400mL clear. Pain 2/10."
- **T+6h:** "Family at bedside, conversing appropriately. No distress."
- **T+8h:** "Preparing for overnight, pain controlled, vitals stable."

### Deteriorating
- **T+0h:** "Pt alert and oriented, vitals stable, pain 3/10, dressing dry."
- **T+1h:** "Pain 4/10, mildly anxious. Dressing dry. HR slightly up."
- **T+2h:** "Pt reports 'just doesn't feel right', pain 5/10. Slight pallor noted."
- **T+4h:** "Pt increasingly restless, pain now 6/10, skin cool to touch. UO trending down."
- **T+6h:** "Diaphoretic, pain 7/10 despite dose. Abdomen tender. Cap refill 3s."
- **T+8h:** "Lethargic, responds slowly. Extremities cool and mottled. UO minimal."

### Sepsis Onset
- **T+0h:** "Postpartum Day 0 / POD 0. Vitals stable, lochia moderate rubra, incision CDI."
- **T+1h:** "Pt reports mild chills, requested extra blanket. Temp trending up."
- **T+2h:** "Pt reports chills, says 'feeling off'. Surgical site warm but no purulence. WBC pending."
- **T+4h:** "Rigors, flushed, HR 118, RR 24. Site erythema expanding. Lactate drawn. MD notified."
- **T+6h:** "Hypotensive despite 1L bolus. Mottled knees. Anuric last hour. Sepsis protocol active."
- **T+8h:** "On levophed, intubation anesthesia bedside. Family notified."

### Postpartum Hemorrhage
- **T+0h:** "Delivery of viable infant, placenta intact, EBL 300 mL. Fundus firm at umbilicus."
- **T+1h:** "Pad saturation noted, fundus boggy — massaged to firm. Patient pale. Pitocin running."
- **T+2h:** "Large clot expressed (~400 mL). BP 88/52, HR 124. Second IV placed. OB at bedside."
- **T+4h:** "To OR for exam under anesthesia. 2 units PRBC transfusing. Bakri balloon placed."
- **T+6h:** "Return from OR, fundus firm, bleeding controlled. Hgb 7.2."
- **T+8h:** "Stable on L&D, 2nd unit PRBC complete, UO improving."

---

## 4. Expected Alert Table

| patient_id | T+0h    | T+1h      | T+2h        | T+4h                 | T+6h        | T+8h        |
|------------|---------|-----------|-------------|----------------------|-------------|-------------|
| PT-001     | NORMAL  | NORMAL    | NORMAL      | NORMAL               | NORMAL      | NORMAL      |
| PT-002     | NORMAL  | NORMAL    | NORMAL      | NORMAL               | NORMAL      | NORMAL      |
| PT-003     | NORMAL  | NORMAL    | NORMAL      | NORMAL               | NORMAL      | NORMAL      |
| PT-004     | NORMAL  | NORMAL    | TRIGGERED   | HIGH                 | HIGH        | HIGH        |
| PT-005     | NORMAL  | NORMAL    | TRIGGERED   | HIGH                 | HIGH        | HIGH        |
| PT-006     | NORMAL  | NORMAL    | TRIGGERED   | HIGH                 | HIGH        | HIGH        |
| PT-007 ★   | NORMAL  | NORMAL    | **TRIGGERED** | **HIGH + SBAR**    | HIGH        | HIGH        |
| PT-008     | NORMAL  | NORMAL    | TRIGGERED   | CRITICAL + sepsis=YES| EMERGENCY   | EMERGENCY   |
| PT-009 ★   | NORMAL  | NORMAL    | **TRIGGERED** | **CRITICAL + sepsis=YES + SBAR + abx bundle** | EMERGENCY | EMERGENCY |
| PT-010 ★   | NORMAL  | **TRIGGERED** | **EMERGENCY + SBAR + blood products + fundal massage** | CRITICAL | HIGH | HIGH |

★ = demo hero. MCP tools invoked every tick: `screen_vital_thresholds`, `score_deterioration_risk`, `flag_sepsis_onset`. `generate_escalation_note` fires at the first TRIGGERED tick of each patient and every tick thereafter until state machine exits `AWAITING_REVIEW`. Postpartum-specific handling (PT-009 sepsis, PT-010 hemorrhage) is data-driven, not tool-specific — the same four tools serve both wards per `PROJECT_BRIEF.md:27`.

---

## 5. FHIR R4 Bundle Template (one patient-timepoint)

```json
{
  "resourceType": "Bundle",
  "id": "PT-007-T2",
  "type": "collection",
  "timestamp": "2026-04-15T12:00:00Z",
  "entry": [
    {
      "resource": {
        "resourceType": "Patient",
        "id": "PT-007",
        "identifier": [{"system": "urn:oid:2.16.840.1.113883.19.5", "value": "MRN-100007"}],
        "name": [{"family": "Patient", "given": ["Synthetic", "7"]}],
        "gender": "female",
        "birthDate": "1983-12-04"
      }
    },
    {
      "resource": {
        "resourceType": "Encounter",
        "id": "ENC-PT-007",
        "status": "in-progress",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP"},
        "subject": {"reference": "Patient/PT-007"},
        "period": {"start": "2026-04-15T10:00:00Z"}
      }
    },
    {
      "resource": {
        "resourceType": "Procedure",
        "id": "PROC-PT-007",
        "status": "completed",
        "code": {"coding": [{"system": "http://snomed.info/sct", "code": "47162000", "display": "Exploratory laparotomy"}]},
        "subject": {"reference": "Patient/PT-007"},
        "performedDateTime": "2026-04-15T10:00:00Z"
      }
    },
    {
      "resource": {
        "resourceType": "Observation", "id": "OBS-PT-007-T2-SBP", "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "vital-signs"}]}],
        "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6", "display": "Systolic blood pressure"}]},
        "subject": {"reference": "Patient/PT-007"},
        "effectiveDateTime": "2026-04-15T12:00:00Z",
        "valueQuantity": {"value": 111, "unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]"}
      }
    },
    { "resource": {"resourceType": "Observation", "id": "OBS-PT-007-T2-DBP", "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "8462-4", "display": "Diastolic blood pressure"}]},
        "subject": {"reference": "Patient/PT-007"}, "effectiveDateTime": "2026-04-15T12:00:00Z",
        "valueQuantity": {"value": 70, "unit": "mmHg", "code": "mm[Hg]"}}},
    { "resource": {"resourceType": "Observation", "id": "OBS-PT-007-T2-HR", "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4", "display": "Heart rate"}]},
        "subject": {"reference": "Patient/PT-007"}, "effectiveDateTime": "2026-04-15T12:00:00Z",
        "valueQuantity": {"value": 88, "unit": "/min", "code": "/min"}}},
    { "resource": {"resourceType": "Observation", "id": "OBS-PT-007-T2-RR", "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "9279-1", "display": "Respiratory rate"}]},
        "subject": {"reference": "Patient/PT-007"}, "effectiveDateTime": "2026-04-15T12:00:00Z",
        "valueQuantity": {"value": 18, "unit": "/min", "code": "/min"}}},
    { "resource": {"resourceType": "Observation", "id": "OBS-PT-007-T2-SPO2", "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "59408-5", "display": "SpO2"}]},
        "subject": {"reference": "Patient/PT-007"}, "effectiveDateTime": "2026-04-15T12:00:00Z",
        "valueQuantity": {"value": 96, "unit": "%", "code": "%"}}},
    { "resource": {"resourceType": "Observation", "id": "OBS-PT-007-T2-TEMP", "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "8310-5", "display": "Body temperature"}]},
        "subject": {"reference": "Patient/PT-007"}, "effectiveDateTime": "2026-04-15T12:00:00Z",
        "valueQuantity": {"value": 37.2, "unit": "Cel", "code": "Cel"}}},
    { "resource": {"resourceType": "Observation", "id": "OBS-PT-007-T2-URINE", "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "9192-6", "display": "Urine output"}]},
        "subject": {"reference": "Patient/PT-007"}, "effectiveDateTime": "2026-04-15T12:00:00Z",
        "valueQuantity": {"value": 35, "unit": "mL/h", "code": "mL/h"},
        "note": [{"text": "Pt reports 'just doesn't feel right', pain 5/10. Slight pallor noted."}]}}
  ]
}
```

The nursing note is attached to the urine-output observation's `note[]` field for simplicity; alternative is a separate `Observation` with LOINC 34109-9 (Note).

### 5.1 Additional FHIR resource shapes (per patient)

The per-timepoint template in §5 shows only Patient + Encounter + Procedure + 7 vital Observations. For the tools to work, each patient bundle must ALSO include the lab Observations from §2.5, the Condition resources from the comorbidity table below, and the MedicationAdministration resources from the antibiotic-timing table below. These are generated once per patient (not per timepoint) and bundled under the same `Bundle.id` as the T+0h bundle.

#### 5.1.1 Condition (comorbidities — generated once per patient)

| Patient | SNOMED code | Display |
|---|---|---|
| PT-001 | 59621000  | Essential hypertension |
| PT-002 | 239873007 | Osteoarthritis of knee |
| PT-003 | (none)    | — |
| PT-004 | 44054006, 13645005 | Type 2 diabetes mellitus; COPD |
| PT-005 | 414916001, 59621000 | Obesity; Essential hypertension |
| PT-006 | 53741008, 44054006  | Coronary artery disease; Type 2 diabetes mellitus |
| PT-007 | 44054006, 433144002 | Type 2 diabetes mellitus; Chronic kidney disease stage 3 |
| PT-008 | 44054006, 13645005, 76571007 | Type 2 diabetes mellitus; COPD; Previous septicaemia |
| PT-009 | 199223000, 414916001, 11612004 | Gestational diabetes; Obesity; Chorioamnionitis |
| PT-010 | 58532003, 200737006, 398254007 | Placenta accreta; Previous cesarean; Mild preeclampsia |

Shape per condition (from `API_CONTRACTS.md §5.5`):
```json
{
  "resourceType": "Condition",
  "id": "cond-PT-007-T2DM",
  "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
  "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"}]},
  "code": {"coding": [{"system": "http://snomed.info/sct", "code": "44054006", "display": "Type 2 diabetes mellitus"}]},
  "subject": {"reference": "Patient/PT-007"},
  "recordedDate": "2024-11-02"
}
```

#### 5.1.2 MedicationAdministration (antibiotic timing — critical for CDC ASE path)

| Patient | Drug | RxNorm | Dose | Route | effectiveDateTime (relative to T+0h procedure) |
|---|---|---|---|---|---|
| PT-001..003 | Cefazolin | 309264 | 1 g | IV | T-0:30 (pre-op prophylaxis) |
| PT-004..007 | Cefazolin | 309264 | 1 g | IV | T-0:30 |
| PT-008 | Cefazolin | 309264 | 1 g | IV | T-0:30 |
| PT-008 | Piperacillin-tazobactam | 203134 | 4.5 g | IV | **T+4:15** (post sepsis-onset broad spectrum) |
| PT-009 | Cefazolin | 309264 | 2 g | IV | T-0:15 (pre-delivery) |
| PT-009 | Ampicillin-sulbactam | 1659149 | 3 g | IV | **T+4:20** (post sepsis-onset, postpartum endometritis/sepsis per ACOG PB 199) |
| PT-010 | Cefazolin | 309264 | 2 g | IV | T-0:15 |

**Why the post-onset times are ≥ 4:15 and not simultaneous with T+4h.** `flag_sepsis_onset` looks for an antibiotic start event within the 24h evaluation window but AFTER the organ-dysfunction marker appears — this lets it (correctly) flag "pre-administration window" scenarios for the DEMO_SCRIPT PT-009 beat, where the vitals + labs are already triggering the alert by the time empirical abx rolls. A simultaneous-with-onset dataset would confuse the tool's recency logic. **Citations:** Cefazolin dosing per ASHP Surgical Site Infection Prevention Guidelines (2013, https://www.ashp.org/-/media/assets/policy-guidelines/docs/therapeutic-guidelines/therapeutic-guidelines-surgical-site-infection.pdf); Piperacillin-tazobactam 4.5g q6h per Surviving Sepsis Campaign 2021 (https://journals.lww.com/ccmjournal/fulltext/2021/11000/surviving_sepsis_campaign_2021_guidelines.1.aspx); Ampicillin-sulbactam 3g IV q6h per ACOG Practice Bulletin 199 (2018, https://www.acog.org/clinical/clinical-guidance/practice-bulletin/articles/2018/09/use-of-prophylactic-antibiotics-in-labor-and-delivery).

Shape per administration:
```json
{
  "resourceType": "MedicationAdministration",
  "id": "medadmin-PT-009-ampisulbactam-1",
  "status": "completed",
  "medicationCodeableConcept": {"coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": "1659149", "display": "Ampicillin-sulbactam 3 g IV"}]},
  "subject": {"reference": "Patient/PT-009"},
  "effectiveDateTime": "2026-04-15T14:20:00Z",
  "dosage": {"dose": {"value": 3, "unit": "g", "system": "http://unitsofmeasure.org", "code": "g"}, "route": {"coding": [{"system": "http://snomed.info/sct", "code": "47625008", "display": "Intravenous route"}]}}
}
```

#### 5.1.3 Lab Observation shape

Identical structure to the vital Observation shape in §5, except:
- `category[].coding[].code = "laboratory"` (not `"vital-signs"`)
- `code.coding[].code` uses the LOINC codes from §2.5 (e.g. `2524-7` for lactate)
- `valueQuantity.unit` matches the UCUM from `CLINICAL_EVIDENCE §11.2`
- `effectiveDateTime` is the draw time — T+0h, T+4h, or T+8h per §2.5

Example (PT-009 T+4h lactate):
```json
{
  "resourceType": "Observation",
  "id": "OBS-PT-009-T4-LACTATE",
  "status": "final",
  "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "laboratory"}]}],
  "code": {"coding": [{"system": "http://loinc.org", "code": "2524-7", "display": "Lactate [Moles/volume] in Blood"}]},
  "subject": {"reference": "Patient/PT-009"},
  "effectiveDateTime": "2026-04-15T14:00:00Z",
  "valueQuantity": {"value": 4.2, "unit": "mmol/L", "system": "http://unitsofmeasure.org", "code": "mmol/L"}
}
```

---

## 6. Clinical Plausibility Sanity Check

All numbers chosen to sit inside physiologically observed ranges for post-surgical and postpartum patients:

- **Stable postop vitals:** SBP 115–125, HR 65–85, Temp 36.5–37.2 — within ASA/PACU discharge criteria. Matches Aldrete scoring defaults.
- **MEWT deterioration thresholds:** 2-parameter drift of ≥10% SBP drop OR HR ≥100 OR RR ≥22 triggers escalation. PT-007's T+2h hits the trend threshold while each individual number is benign.
- **qSOFA ≥2:** RR ≥22, altered mentation, SBP ≤100 → bedside screen positive. PT-008/009 hit this at T+4h.
- **SIRS/Sepsis-3:** Temp >38 or <36, HR >90, RR >20, WBC >12k or <4k — ≥2 criteria = SIRS; with infection source = sepsis.
- **CDC Adult Sepsis Event:** presumed infection + ≥1 acute organ dysfunction (vasopressor, lactate ≥2, Cr doubling, bili doubling, plt <100k, mech vent).
- **PPH (RCOG Green-top 52):** primary PPH = EBL ≥500 mL vaginal / ≥1000 mL C-section within 24h; major PPH = ≥1000 mL + ongoing bleeding or shock.
- **Postpartum normal vitals:** SBP 100–130, HR 60–100 (may be bradycardic first 24h), Temp ≤38 (≤38.7 allowable in first 24h due to milk let-down).

**Cited sources:**

1. Singer M et al. "The Third International Consensus Definitions for Sepsis and Septic Shock (Sepsis-3)." *JAMA* 2016;315(8):801-810. https://jamanetwork.com/journals/jama/fullarticle/2492881
2. CDC. "Hospital Toolkit for Adult Sepsis Surveillance." CDC National Healthcare Safety Network, 2018. https://www.cdc.gov/sepsis/pdfs/sepsis-surveillance-toolkit-mar-2018_508.pdf
3. RCOG Green-top Guideline No. 52. "Prevention and Management of Postpartum Haemorrhage." *BJOG* 2017;124:e106–e149. https://www.rcog.org.uk/guidance/browse-all-guidance/green-top-guidelines/prevention-and-management-of-postpartum-haemorrhage-green-top-guideline-no-52/
4. Mhyre JM et al. "The Maternal Early Warning Criteria." *Obstet Gynecol* 2014;124(4):782-6. (Basis for MEWT in obstetric population.) https://pubmed.ncbi.nlm.nih.gov/25198266/
5. Subbe CP et al. "Validation of a Modified Early Warning Score in medical admissions." *QJM* 2001;94(10):521-6. https://pubmed.ncbi.nlm.nih.gov/11588210/

---

## 7. Generation Script Requirements (`data/generate_synthetic_patients.py`)

**Inputs:** hardcoded tables from §2 (dict of trajectory → list of 6 timepoint dicts), roster from §1.

**Output directory layout:**

```
data/synthetic_patients/
  PT-001/
    T0.json   # FHIR Bundle for T+0h
    T1.json
    T2.json
    T4.json
    T6.json
    T8.json
    _manifest.json   # trajectory, demo_role, expected_alerts
  PT-002/...
  ...
  _index.json   # flat list of all 10 patients with trajectories
```

**Filename convention:** `T{hours}.json` (not `T+{hours}` — `+` is URL-unfriendly). `_manifest.json` per patient mirrors §4 expected alerts so tests can assert ground truth.

**Re-seed into HAPI FHIR:**
```bash
python data/generate_synthetic_patients.py --out data/synthetic_patients
python data/seed_hapi.py --fhir-base http://localhost:8080/fhir --src data/synthetic_patients
```
`seed_hapi.py` POSTs each bundle to `/fhir` as a transaction bundle (rewrite `type` from `collection` → `transaction` and add `request.method=POST`/`request.url=<ResourceType>` on each entry before upload).

**Determinism:** script takes `--seed 42`. No randomness in the hero patients (PT-001/007/009/010); fillers may get ±1 jitter on each value via `random.Random(seed)`.

**Validation step:** after generation, the script runs each bundle through `fhir.resources` pydantic models to guarantee R4 conformance, then runs a smoke test calling `screen_vital_thresholds` on PT-001/T0 and PT-007/T2 and asserting the expected alert state from §4.

---

**End of SYNTHETIC_DATA_SPEC.md**
