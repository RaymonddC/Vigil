# Vigil — Submission Copy Audit

Owner: submission-auditor | Date: 2026-04-20
Scope: README.md, DEVPOST_SUBMISSION.md, MARKETPLACE_LISTING.md, DEMO_SCRIPT.md, SCREENSHOT_CHECKLIST.md, SUBMISSION_LOG.md, JUDGE_HOOK_CHECK.md, DEVELOPMENT.md

---

## Summary

| Category | Finding count |
|---|---|
| Corrections required (blockers) | 5 |
| Banned phrase hits | 1 |
| Citation issues | 2 |
| Verified claims (clean) | 18 |
| Judge hook gaps | 0 (Zheng gap in JUDGE_HOOK_CHECK is already resolved in DEVPOST) |

---

## 1. Corrections Required

### C1 — README test count is stale (BLOCKER)

**Claim in README**: "69 tests" appears in four places:
- `README.md:3` — badge: `tests-69_passing`
- `README.md:287` — make table: `Run pytest (69 tests)`
- `README.md:312` — repo layout: `13 test files, 69 tests, ~4.4K LOC`
- `README.md:386` — contributing section: `make test        # 69 pytest tests`

**Actual**: `uv run pytest --collect-only -q` → **312 tests collected**. All other docs (DEVELOPMENT.md:219, SUBMISSION_LOG.md:29, DEVPOST_SUBMISSION.md:76) correctly say 312.

**Fix**: Update all four README lines from `69` to `312`.

---

### C2 — DEVPOST PT-009 lactate value is wrong (BLOCKER)

**Claim**: `DEVPOST_SUBMISSION.md:52` — `"PT-009, 29F, 3 days post-C-section, lactate 4.1, WBC 18"`

**Actual**: `data/seed_hapi.py:101` — `{"Lactate": 4.2, "WBC": 18.4, ...}` (T4 timepoint, the escalation peak).

`4.1` is not in the seed data at any timepoint for this patient.

**Fix**: Change `lactate 4.1` → `lactate 4.2`, `WBC 18` → `WBC 18.4` in DEVPOST_SUBMISSION.md:52.

---

### C3 — DEMO_SCRIPT narration cites wrong lactate (BLOCKER)

**Claim**: `DEMO_SCRIPT.md:83` (beat table) and `DEMO_SCRIPT.md:110` (full narration) both read:
> "PT-009. Twenty-nine years old. Three days postpartum. **Lactate four point one**, white count eighteen."

**Actual**: `data/seed_hapi.py:101` — Lactate = 4.2.

If a judge (Zheng, Mandel) checks the seeded FHIR data against what the presenter says, this will undermine credibility.

**Fix**: Change "four point one" → "four point two" in both locations. Change "white count eighteen" → "white count eighteen point four" (or keep "eighteen" as a rounded figure — but lactate must be exact).

---

### C4 — MARKETPLACE_LISTING agent card has wrong GitHub URL

**Claim**: `MARKETPLACE_LISTING.md:154` (inside agent card JSON):
```json
"url": "https://github.com/raymond/vigil"
```

**Actual**: `DEVELOPMENT.md:26` — `git clone https://github.com/RaymonddC/Vigil.git`

The username is `RaymonddC`, not `raymond`. The repo name uses capital `V`.

**Fix**: Update MARKETPLACE_LISTING.md:154 to `"https://github.com/RaymonddC/Vigil"`.

---

### C5 — DEVPOST GitHub link is a placeholder

**Claim**: `DEVPOST_SUBMISSION.md:104` — `- **GitHub:** [link to repo]`

**Actual**: Link is not filled in. This must be populated before submission.

**Fix**: Replace `[link to repo]` with `https://github.com/RaymonddC/Vigil`.

---

## 2. Banned Phrase Hits

### B1 — "Autonomous" used affirmatively in SCREENSHOT_CHECKLIST

**Location**: `SCREENSHOT_CHECKLIST.md:255`:
```
Right: **Vigil Postop Sentinel** — "Autonomous A2A Agent" — badges: [A2A] [FHIR R4] [SHARP]
```

**Rule**: "autonomous" is banned — the project is explicit that the agent is *not* autonomous.

This string will appear as the marketplace card label in Shot 10 of the demo video and README. Proctor (CHOP) specifically distinguishes autonomous from agentic-with-human-in-loop, and Vigil's core thesis is the latter.

**Fix**: Change `"Autonomous A2A Agent"` → `"Human-supervised A2A Agent"` or `"7-state A2A Sentinel"`.

**No other banned phrases found in submission copy:**
- "Cleveland Clinic 35%": appears only in `docs/CLINICAL_EVIDENCE.md:43` as a section heading for the reference that was *rejected* — not in any submission file. ✓
- "Rubenstein formula": appears only in `docs/REVIEW_NOTES.md:90` as a guard rail. ✓
- "third leading cause": appears only in `docs/CLINICAL_EVIDENCE.md:290` and `docs/REVIEW_NOTES.md:65` as warnings. All submission copy correctly uses "third greatest contributor." ✓
- "Epic": `DEVPOST_SUBMISSION.md:88` — "The SHARP header pattern ports directly to Epic and Cerner FHIR endpoints" — this is in a specific integration context (What's next), which is the permitted use. ✓

---

## 3. Citation Issues

### CI1 — CDC MMWR citation does not support the "2.6×" claim

**Claim**: `DEVPOST_SUBMISSION.md:31`:
> "In the US, Black women die from pregnancy-related causes at **2.6× the rate of white women**, and over 80% of those deaths are preventable ([CDC MMWR 2023](https://www.cdc.gov/mmwr/volumes/72/wr/mm7235e1.htm))."

**Verification**: `mm7235e1.htm` is the MMWR Vol 72 No 35 (2023) report on *maternity care experiences* (mistreatment, discrimination, respectful care). It does not contain a "2.6×" mortality ratio. It states racial disparities exist without quantifying them as 2.6×.

The 2.6× figure does exist in CDC data (from separate CDC surveillance reports on pregnancy-related mortality), but it is not in this article.

**Risk**: If Zheng or any judge fact-checks this URL, the citation will not support the number. This could undermine the Zheng hook at the exact moment it matters most.

**Fix**: Either:
- (Preferred) Replace with the correct CDC citation: CDC Pregnancy Mortality Surveillance System (PMSS) — Black women 2.6× more likely to die from pregnancy-related causes (use the PMSS report URL or the specific MMWR that carries this figure).
- Or soften to: "Black women face significantly higher pregnancy-related death rates than white women (CDC data)" and cite the MMWR broadly.

---

### CI2 — AHRQ PSNet does not explicitly confirm "70–90%" override rate

**Claim**: `README.md:18` and `DEVPOST_SUBMISSION.md:33`:
> "Clinicians override 70–90% of threshold-based CDS alerts ([AHRQ PSNet])."

**Verification**: The AHRQ PSNet alert fatigue primer resolves and is on-topic, but does not cite a "70–90%" range explicitly. It says clinicians override "the vast majority" of CPOE warnings.

**Risk**: Low (Mandel is the most likely to probe this, and "vast majority" is defensible). The 70–90% range is widely cited in CDS literature from other sources.

**Fix**: Either add a second citation (e.g., van der Sijs 2006 *JAMA*; Payne 2011 *JAMIA*) that explicitly states the range, or narrow the claim to "the vast majority" to match the cited source.

---

## 4. Verified Claims (Clean)

| Claim | Location | Verification | Status |
|---|---|---|---|
| 312 tests | DEVPOST:76, DEVELOPMENT:219 | `pytest --collect-only` → 312 | ✓ |
| 39 SHARP compliance tests | README:191, DEVPOST:59 | `grep -c "def test_" test_sharp_compliance.py` → 39 | ✓ |
| 38-test integration harness | DEVPOST:76 | `grep -c "def test_" tests/integration/test_mcp_tools.py` → 38 | ✓ |
| 4 MCP tools | README:24, DEVPOST:41 | `ls backend/mcp_server/tools/` → 4 .py files | ✓ |
| 7-state machine | README:72, DEVPOST:48 | `sentinel.py:3-4,64,93-224` — all 7 states present | ✓ |
| 10 synthetic patients | README:360, DEVPOST:57 | `seed_hapi.py:150-207` — PT-001 through PT-010 | ✓ |
| 6 timepoints per patient | README:360, DEVPOST:57 | `seed_hapi.py:44` — `TP_ORDER = ["T0","T1","T2","T4","T6","T8"]` | ✓ |
| 4 trajectories | README:360, DEVPOST:57 | stable, deteriorating, sepsis, pph in seed data | ✓ |
| LOINC SBP `8480-6` | README:160 | `seed_hapi.py:256` | ✓ |
| LOINC DBP `8462-4` | README:162 | `seed_hapi.py:257` | ✓ |
| LOINC HR `8867-4` | README:164 | `seed_hapi.py:258` | ✓ |
| LOINC RR `9279-1` | README:166 | `seed_hapi.py:259` | ✓ |
| LOINC SpO2 `59408-5` | README:168 | `seed_hapi.py:260` | ✓ |
| LOINC Temp `8310-5` | README:170 | `seed_hapi.py:261` | ✓ |
| LOINC Lactate `2524-7` | README:172 | `seed_hapi.py:267` | ✓ |
| LOINC WBC `6690-2` | README:174 | `seed_hapi.py:268` | ✓ |
| LOINC Creatinine `2160-0` | README:176 | `seed_hapi.py:269` | ✓ |
| LOINC Bilirubin `1975-2` | README:178 | `seed_hapi.py:270` | ✓ |
| LOINC Platelets `777-3` | README:180 | `seed_hapi.py:271` | ✓ |
| "third greatest contributor" | README:15, DEVPOST:20, DEMO_SCRIPT:59,102 | Correct phrasing throughout submission copy | ✓ |
| FastMCP streamable HTTP | README:325 | `backend/mcp_server/` uses FastMCP; SHARP via streamable HTTP transport | ✓ |
| WHO 2023 URL | README:16, DEVPOST:31 | URL resolves; WHO headline confirms "every 2 minutes" | ✓ |
| Moll/Khanna/Mathur 2025 URL | DEVPOST:33 | PMC12266812 resolves; correct authors + topic (AI for postop) | ✓ |
| AHRQ PSNet URL | README:18, DEVPOST:33 | Resolves; on-topic (alert fatigue) | ✓ |
| All internal README doc links | README:404-412 | All 10 docs in `docs/` exist | ✓ |

---

## 5. Judge Hook Coverage

JUDGE_HOOK_CHECK.md flagged Zheng as "AT RISK" due to missing racial disparities and "fourth trimester" language. Both have since been added to DEVPOST_SUBMISSION.md:31. Status updated:

| Judge | Submission hook | Demo script | README | Verdict |
|---|---|---|---|---|
| **Mathur** | DEVPOST:20,33,62 — postop mortality, "marginal lift" AI, "no false alarm" | 0:10–1:00 — pattern-not-threshold, 4.2M, PT-001 stable | README:14-18 problem statement, evaluation table | **SERVED** |
| **Mandel** | DEVPOST:41-48 — 4 MCP tools, FHIR R4 resources, zero code changes | 0:20–0:40, 1:05, 2:00–2:35 — FHIR payload, tool states, reusability | README:140-210 — LOINC table, SHARP, substitutability | **SERVED** |
| **Hickey** | DEVPOST:43,46 — SBAR generation, never writes chart | 1:15–1:35, 2:05 — S/B/A/R typed live | README:131 — SBAR clinical standard | **SERVED** |
| **Proctor** | DEVPOST:50,74 — "closed-loop action, not a dashboard", approve flow | 1:10–1:45 — draft not persisted, approve writes FHIR | README:220-224 — no autonomous writes | **SERVED** |
| **Zheng** | DEVPOST:31 — "2.6× Black women" (citation needs fix per CI1), "fourth trimester", 260K stat | 1:50–2:15 — PT-009 reveal, 260K stat, PT-010 flash | README:16 — WHO stat | **SERVED** (citation fix needed) |

No judge has a hook gap. Zheng is fully covered in Devpost but the CDC citation supporting the 2.6× figure needs correction (CI1).

---

## 6. Link and URL Issues

| Item | Status |
|---|---|
| README internal links to docs/*.md (10 files) | All resolve ✓ |
| DEVPOST video URL | `[link to Devpost video]` — placeholder, must be filled before submit |
| DEVPOST GitHub URL | `[link to repo]` — placeholder (C5 above) |
| DEVPOST live dashboard | `[Vercel URL]` — placeholder |
| MARKETPLACE agent card GitHub URL | Wrong: `github.com/raymond/vigil` → should be `github.com/RaymonddC/Vigil` (C4 above) |
| Nepogodiev Lancet URL | Returns 403 (paywall); URL pattern is correct for PIIS0140-6736(18)33139-8; considered valid |

---

## 7. Consistency Check

| Item | Consistent? | Notes |
|---|---|---|
| Test count across docs | NO ❌ | README says 69 (×4), all other docs say 312 |
| Tool names | YES ✓ | `screen_vital_thresholds`, `score_deterioration_risk`, `flag_sepsis_onset`, `generate_escalation_note` identical across README, DEVPOST, MARKETPLACE, DEMO_SCRIPT |
| State names | YES ✓ | IDLE → POLLING → SCREENING → RISK_SCORING → SEPSIS_CHECK → ESCALATING → AWAITING_REVIEW identical across README, DEVPOST, MARKETPLACE |
| Port numbers | YES ✓ | HAPI :8080, MCP :7001, A2A :9000, Proxy :8000, Frontend :3000 consistent |
| PT-009 lactate | NO ❌ | DEVPOST says 4.1; JUDGE_HOOK_CHECK and seed data say 4.2 |
| FHIR resource names | YES ✓ | Communication + AuditEvent consistently named |
| SHARP header names | YES ✓ | `x-fhir-server-url`, `x-fhir-access-token`, `x-patient-id` consistent |

---

## 8. Action List (prioritized)

| Priority | Item | File | Fix |
|---|---|---|---|
| P1 | C1 — README test count | `README.md` lines 3, 287, 312, 386 | `69` → `312` |
| P1 | C2 — DEVPOST lactate | `DEVPOST_SUBMISSION.md:52` | `4.1` → `4.2`, `WBC 18` → `WBC 18.4` |
| P1 | C3 — DEMO_SCRIPT lactate | `DEMO_SCRIPT.md:83,110` | "four point one" → "four point two" |
| P1 | C4 — Marketplace GitHub URL | `MARKETPLACE_LISTING.md:154` | `raymond/vigil` → `RaymonddC/Vigil` |
| P1 | CI1 — CDC MMWR citation | `DEVPOST_SUBMISSION.md:31` | Replace `mm7235e1.htm` with PMSS citation for 2.6× figure |
| P2 | B1 — "Autonomous" in screenshot | `SCREENSHOT_CHECKLIST.md:255` | Remove "Autonomous" label |
| P2 | CI2 — AHRQ 70-90% range | `README.md:18`, `DEVPOST:33` | Add corroborating citation or soften to "vast majority" |
| P3 | C5 — DEVPOST GitHub placeholder | `DEVPOST_SUBMISSION.md:104` | Fill in `https://github.com/RaymonddC/Vigil` |

*End of audit.*
