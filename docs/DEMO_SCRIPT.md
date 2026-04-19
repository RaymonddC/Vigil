# Vigil — Demo Script (3-minute Devpost submission)

> Target runtime: **2:55** (hard ceiling 3:00 per Devpost rules)
> Final narration word count: **~454 words** (~156 wpm)
> Video format: 1920x1080, 30fps, MP4 H.264, <500MB

---

## 1. Pre-flight checklist

Run through this in order. Nothing gets recorded until every box is ticked.

### Services up
- [ ] HAPI FHIR server healthy at `http://localhost:8080/fhir/metadata` (200 OK)
- [ ] MCP server running on `localhost:7001`, all 4 canonical tools registered (`screen_vital_thresholds`, `score_deterioration_risk`, `flag_sepsis_onset`, `generate_escalation_note`)
- [ ] Python A2A agent running on `localhost:9000`, health endpoint green
- [ ] Next.js clinician dashboard on `localhost:3000`, all 6 views load without console errors (home, patients roster, patient detail, alerts/review queue, agent timeline, settings)
- [ ] `LLM_PROVIDER=claude` set in agent `.env` (NOT ollama — quality matters for the judge-facing narration)

### Data fresh
- [ ] Re-seed HAPI with `./scripts/seed_patients.sh` so timestamps are within the last 2 hours
- [ ] Verify PT-001, PT-007, PT-009, PT-010 all appear in the patient roster table
- [ ] PT-007 vitals trend shows clear deterioration in last 6 hours
- [ ] PT-009 latest lactate >4, WBC >18

### Recording rig
- [ ] Desktop cleaned (hide dock, close Slack, Discord, email, all notifications silenced)
- [ ] Chrome zoom set to 110% for dashboard legibility
- [ ] Chrome window sized to exactly 1920x1080 (use window-resizer extension)
- [ ] Mic check: pop filter on, gain at -12dB peak, no fan/AC noise
- [ ] OBS scene preset loaded: dashboard source + webcam disabled + no overlays
- [ ] Do a 10-second mic+screen test and play it back before the real take

---

## 2. Production notes

| Setting | Value |
| --- | --- |
| Resolution | 1920x1080 minimum, 2560x1440 preferred |
| Frame rate | 30fps minimum, 60fps for smoother cursor |
| Screen recorder | OBS Studio (free, reliable, no watermark) |
| Mic | USB condenser with pop filter — **pop filter is non-negotiable**, plosives kill clarity |
| Audio codec | AAC, 192kbps, mono |
| Video codec | H.264, CRF 20 |
| Container | MP4 |
| Target file size | <500MB (Devpost upload limit is 500MB — aim for 300MB to be safe) |
| Cursor | Enable OBS "cursor highlight" filter, 40px yellow ring |
| Text overlays | Use OBS Text (GDI+) source, Inter font, 48pt, drop shadow |

**Record in 3 takes minimum.** Don't try to nail it in one. Cut the best of each in DaVinci Resolve (free).

---

## 3. Beat-by-beat script (36 rows, every 5 seconds)

| Time | Screen | Narration | Cutaway / Effect | Judge hook |
| --- | --- | --- | --- | --- |
| 0:00 | Black frame, fade into Vigil logo | "Deaths within 30 days of surgery are the third greatest contributor to global deaths —" | Logo fade in | GENERAL |
| 0:05 | Stat card: "4.2M deaths / year" | "— more than AIDS, tuberculosis, and malaria each." | Red overlay on stat | GENERAL |
| 0:10 | Same card, "30 days post-surgery" | "4.2 million people die within 30 days of surgery every year." | Hold on stat | MATHUR |
| 0:15 | Cut to patient roster table, 10 rows sorted by risk | "Most of those deaths are missed signals — not missing data." | Zoom into roster | MATHUR |
| 0:20 | PT-001 row, green "Normal" RiskBadge | "This is Vigil. A clinician dashboard watching post-op patients in a live FHIR server." | Highlight "FHIR" label | MANDEL |
| 0:25 | Click PT-001, vitals chart flat/green, latest vitals cards | "PT-001 is stable. Vitals flat, labs clean, our agent says: no action." | Green check animation | MATHUR |
| 0:30 | PT-001 detail view, Risk: Normal, qSOFA 0/3, no alerts | "Notice what's missing — no alert. No false alarm." | Callout: "0 false alerts" | MATHUR |
| 0:35 | Switch to Agent Timeline page, tool_call rows with LOINC payloads | "Every number on this screen is a real FHIR Observation pulled by an MCP tool." | Expand a row to show JSON payload | MANDEL |
| 0:40 | Expand `screen_vital_thresholds` event, FHIR Observation IDs in payload | "Same tool any MCP-compatible agent can call. SMART-on-FHIR under the hood." | Highlight tool name | MANDEL |
| 0:45 | Back to patient list | "Now watch what happens when the pattern shifts." | Fade transition | GENERAL |
| 0:50 | Click PT-007, vitals chart with downward trend | "PT-007. Same post-op cohort. But heart rate is climbing and blood pressure is drifting down." | Red highlight on trend | MATHUR |
| 0:55 | Zoom on trend arrows | "No single value has crossed a threshold. A rules engine would stay silent." | Callout: "Below threshold" | MATHUR |
| 1:00 | Switch to Agent Timeline page, SCREENING → RISK_SCORING events appear | "Vigil's agent sees the pattern across six hours of FHIR data and escalates." | Pulse animation | MATHUR |
| 1:05 | Four tool_call rows in timeline: SCREENING → RISK_SCORING → SEPSIS_CHECK → ESCALATING | "Four MCP tool calls — screen vital thresholds, score deterioration risk, flag sepsis onset, draft the SBAR." | Highlight each state badge | MANDEL |
| 1:10 | ESCALATING row highlighted, click to expand `generate_escalation_note` payload | "The agent drafts the escalation, but never writes the chart on its own. Every action waits for a clinician." | Callout: "draft — not persisted" | PROCTOR |
| 1:15 | SBAR card appears, empty | "And here's the moment a nurse actually uses." | Zoom on empty card | HICKEY |
| 1:20 | SBAR streams in: Situation line | "An SBAR note. Situation —" | Text types in live | HICKEY |
| 1:25 | Background line appears | "Background —" | Text types in live | HICKEY |
| 1:30 | Assessment line appears | "Assessment —" | Text types in live | HICKEY |
| 1:35 | Recommendation line appears | "Recommendation: call the rapid response team." | Text types in live | HICKEY |
| 1:40 | Review Queue page, "Approve & send RRT" button on PT-007 alert card | "One click and the backend writes a FHIR Communication plus an AuditEvent to the chart." | Button click | PROCTOR |
| 1:45 | Sonner toast: "Communication {id} written — audit {id}" | "Closed loop — clinician approves, chart updates, audit trail captured. Agentic action, always with a human in the loop." | Toast fade | PROCTOR |
| 1:50 | Back to patient roster, click PT-009, red "Critical" RiskBadge | "Now the part we're most proud of." | Hard cut | ZHENG |
| 1:55 | PT-009 detail: postpartum sepsis | "PT-009. Twenty-nine years old. Three days postpartum. Lactate four point one, white count eighteen." | Red banner | ZHENG |
| 2:00 | Same 4 MCP tools fire, same agent | "Same four MCP tools. Same agent. Zero code changes." | Diff overlay: "0 lines changed" | MANDEL |
| 2:05 | SBAR generates for sepsis path | "Maternal sepsis SBAR, generated the exact same way." | Text streams | HICKEY |
| 2:10 | Stat overlay: "260K maternal deaths/year" | "Maternal mortality kills 260,000 women a year. Most from sepsis and hemorrhage." | Red stat card | ZHENG |
| 2:15 | PT-010 flash: postpartum hemorrhage | "PT-010 is a hemorrhage case — same pipeline, same escalation." | Quick flash | ZHENG |
| 2:20 | MCP marketplace mockup, two tiles | "Because these are MCP tools, both care paths ship as one registry entry." | Zoom on tiles | MANDEL |
| 2:25 | Tile 1: "Post-op Watch" | "Post-op watch." | Highlight tile | MATHUR |
| 2:30 | Tile 2: "Postpartum Watch" | "Postpartum watch." | Highlight tile | ZHENG |
| 2:35 | Both tiles + "Install" button | "Any hospital running SMART-on-FHIR can install either path in minutes." | Install button pulse | MANDEL |
| 2:40 | Architecture splash: 4 tools → 1 agent → N paths | "Four tools. One agent. Unlimited clinical pathways." | Diagram reveal | GENERAL |
| 2:45 | Closing stat: "4.2M + 260K" | "Four point two million post-op deaths. Two hundred sixty thousand mothers." | Large text | GENERAL |
| 2:50 | "One platform. Vigil." + logo | "One platform. Vigil." | Logo hold | GENERAL |
| 2:55 | Fade to URL + GitHub + team names | (silent) | Fade out | GENERAL |

---

## 4. Full narration (rehearsal text)

> **Word count: ~454 words. Target cadence: 156 wpm. Rehearse at 150 wpm to leave breathing room.**

Postoperative mortality is the world's third greatest contributor to global deaths — more than AIDS, tuberculosis, and malaria each. 4.2 million people die within 30 days of surgery every year. Most of those deaths are missed signals, not missing data.

This is Vigil. A clinician dashboard watching post-op patients in a live FHIR server. PT-001 is stable. Vitals flat, labs clean, our agent says: no action. Notice what's missing — no alert. No false alarm. Every number on this screen is a real FHIR Observation pulled by an MCP tool. Same tool any MCP-compatible agent can call. SMART-on-FHIR under the hood.

Now watch what happens when the pattern shifts. PT-007. Same post-op cohort. But heart rate is climbing and blood pressure is drifting down. No single value has crossed a threshold. A rules engine would stay silent. Vigil's agent sees the pattern across six hours of FHIR data and escalates. Four MCP tool calls — screen vital thresholds, score deterioration risk, flag sepsis onset, and draft the SBAR. The agent never writes the chart itself. It drafts. It waits.

And here's the moment a nurse actually uses. An SBAR note. Situation — Background — Assessment — Recommendation: call the rapid response team. One click — Approve — and the backend writes a FHIR Communication and an AuditEvent to the chart. Closed loop, clinician in control. Agentic action — not a dashboard, a teammate.

Now the part we're most proud of. PT-009. Twenty-nine years old. Three days postpartum. Lactate four point one, white count eighteen. Same four MCP tools. Same agent. Zero code changes. Maternal sepsis SBAR, generated the exact same way. Maternal mortality kills 260,000 women a year. Most from sepsis and hemorrhage. PT-010 is a hemorrhage case — same pipeline, same escalation.

Because these are MCP tools, both care paths ship as one registry entry. Post-op watch. Postpartum watch. Any hospital running SMART-on-FHIR can install either path in minutes. Four tools. One agent. Unlimited clinical pathways.

Four point two million post-op deaths. Two hundred sixty thousand mothers. One platform. Vigil.

---

## 5. Judge hooks checklist

Every judge must be served by 3:00. Here's the ledger.

| Judge | What they care about | Hook timestamp | Hook content | Status |
| --- | --- | --- | --- | --- |
| **Piyush Mathur** (Cleveland Clinic, postop AI) | Postop deterioration, signal quality, no false alerts | 0:10, 0:25–0:30, 0:50–1:00, 2:25 | Opening mortality stat, "no false alarm" on PT-001, pattern-not-threshold on PT-007, postop marketplace tile | SERVED |
| **Josh Mandel** (Microsoft, SMART on FHIR) | Real FHIR, real interop, reusability | 0:20, 0:35–0:40, 1:05, 2:00, 2:20–2:35 | "live FHIR server" call-out, timeline payload with Observation IDs, tool-call state badges, "zero code changes" diff, marketplace install | SERVED |
| **Joshua Hickey** (Mayo, SBAR) | SBAR rigor, nurse workflow fit | 1:15–1:35, 2:05 | Full S-B-A-R typed out live on PT-007, reused for PT-009 | SERVED |
| **Stephon Proctor** (CHOP, agentic action) | Action not reporting, closed loop | 1:10, 1:40–1:45 | `generate_escalation_note` returns a draft (not a write), clinician clicks "Approve & Send RRT", backend writes `Communication` + `AuditEvent`, toast confirms — "teammate not dashboard" line | SERVED |
| **Alice Zheng** (VC, women's health) | Maternal health, market size | 1:50–2:15, 2:30 | PT-009 reveal, 260K stat, PT-010 hemorrhage flash, postpartum marketplace tile | SERVED |

**All five judges served. No flags.**

---

## 6. Scene-by-scene breakdown

### Scene 1 — The stakes (0:00–0:20)
Open cold on the 4.2M mortality stat. No music swell, no logo parade. One line, one number, one cut to the product. Purpose: earn the next 2:40 of attention with a punch nobody can argue with.

### Scene 2 — PT-001 stable, "no false alarms" (0:20–0:50)
Show the boring case first. This is the Mathur moment: clinicians distrust AI because it cries wolf. Vigil's first demonstration is *silence* on a stable patient. Click through from the patient roster table to PT-001's detail view — show the flat vitals chart, green "Normal" RiskBadge, and qSOFA 0/3. Then cut to the Agent Timeline page to show FHIR Observation IDs in the tool-call payload — that's the Mandel hook, establishing interop before we get to the drama.

### Scene 3 — PT-007 deteriorating, "pattern not threshold" (0:50–1:20)
The reveal. Heart rate and BP drift but nothing crosses a hard cutoff. Narration explicitly says "a rules engine would stay silent." This is where Mathur leans in. Cut to the Agent Timeline page to show all four tool-call events: SCREENING → RISK_SCORING → SEPSIS_CHECK → ESCALATING. Expand the ESCALATING row to show the `generate_escalation_note` payload — Proctor's first taste of the draft-then-approve pattern.

### Scene 4 — SBAR live generation, "action not dashboard" (1:20–1:50)
SBAR types in on screen in the patient detail view's 2×2 SBAR panel (S · Situation / B · Background / A · Assessment / R · Recommendation). Hickey's entire thesis is that nurses think in SBAR, so show each section appearing. Then navigate to the Review Queue page and click "Approve & send RRT" — the proxy POSTs `Communication` + `AuditEvent` to HAPI and a Sonner toast confirms the write. That's Proctor's closing moment. This is the longest uninterrupted product shot; it needs to breathe.

### Scene 5 — PT-009 postpartum sepsis, "same tools, zero code changes" (1:50–2:20)
The architectural kill shot. Cut hard to a maternal patient. Same four tool calls fire. Same SBAR generator runs. Overlay explicitly says "0 lines changed." Zheng's hook lands here and lasts 30 seconds. Mandel gets a second hit on reusability.

### Scene 6 — Marketplace, "both paths, published" (2:20–2:45)
Pull up to the MCP marketplace mockup. Two tiles side by side: Post-op Watch and Postpartum Watch. "Install" button. This reframes Vigil as a platform, not a demo. Both Mathur and Zheng see their care path shipped as a first-class product.

### Scene 7 — Closing stat, "4.2M + 260K. One platform." (2:45–3:00)
Two numbers, one logo, one line. No call to action, no "thanks for watching." The numbers are the call to action.

---

## 7. Risk moments (and the fix)

### Risk 1 — LLM latency spike at 1:20 during live SBAR generation
**Probability:** High. Claude can take 8–12 seconds for a full SBAR, and our beat allocates 20 seconds total for all four SBAR lines.
**Fix:** Pre-generate both SBAR notes (PT-007 and PT-009) into a JSON fixture. Add a `?demo=1` flag to the frontend that replays the cached SBAR character-by-character with a fixed 80ms cadence. The agent still fires the MCP tools live — only the LLM streaming is cached. Re-record if the cadence looks fake; push through if it looks natural.

### Risk 2 — HAPI FHIR cold start returns 503 at 0:20
**Probability:** Medium. HAPI takes ~30 seconds to warm up after container start.
**Fix:** Hit every endpoint used in the demo with a warm-up script (`./scripts/warm_fhir.sh`) exactly 90 seconds before hitting record. If a 503 flashes during the take, **re-record** — it's a 2-second hit that ruins the Mandel moment.

### Risk 3 — Cursor jitter / OBS frame drop during the 2:00 "zero code changes" overlay
**Probability:** Low-Medium. OBS can drop frames when a large text source animates in on a busy desktop.
**Fix:** Lock OBS to 30fps (not 60), pre-render the "0 lines changed" overlay as a PNG instead of live text, and close Docker Desktop's GUI during recording (it eats GPU). If frame drop is under 2 frames, push through — nobody watches at frame-level. If it's a visible stutter, re-record.

---

## 8. Stretch — 30-second teaser variant

For Twitter / LinkedIn / recruiter DMs. Reuses footage from the main video.

| Time | Source footage | Narration |
| --- | --- | --- |
| 0:00–0:05 | Stat card "4.2M deaths / year" | "4.2 million people die after surgery every year. Most are missed signals." |
| 0:05–0:12 | PT-007 deterioration trend + tool calls | "Vigil watches every FHIR vital, sees the pattern before the threshold, and writes back to the chart." |
| 0:12–0:20 | SBAR typing in live | "It drafts the SBAR. The nurse approves and the chart updates in one click." |
| 0:20–0:25 | Cut to PT-009 + "0 code changes" overlay | "Same four MCP tools save post-op patients and postpartum mothers. Zero code changes." |
| 0:25–0:30 | Logo + URL | "Vigil. One platform. github.com/vigil-health" |

**Teaser word count:** ~60 words. **Cadence:** 120 wpm (slower for social autoplay without captions). **Captions:** burn them in — most social viewers watch muted.

---

*End of demo script.*
