# Vigil demo storyboard — 3 minute video

_Target: 3:00 ± 0:15 · 30 fps · 1920×1080 · screen-record + voiceover_
_Voice: clinical-direct. Third person about the patient. Second person to the clinician. The AI is "Vigil" or "the agent" — never "we," never "I."_

This document is the **visual layer** on top of `DEMO_SCRIPT.md`. It maps the seven storyboard beats to real, click-able routes in the redesigned Next.js UI. For technical pre-flight (services up, data freshness, OBS preset, codec), see `DEMO_SCRIPT.md §1`. For the full continuous-read narration, see `DEMO_SCRIPT.md §4`. The judge-hook ledger lives in `DEMO_SCRIPT.md §5` and is not duplicated here.

A video editor reading this storyboard alone should be able to record the demo without asking questions: every beat names the exact route, the exact viewport, the exact element clicked, and the timestamp window.

---

## Voice and copy rules (enforced)

- **The Approve attribution string is sacred.** On screen, in voiceover, and in any title card it appears verbatim: **`Approved by Dr. Amit Patel · 14:07 · written to EHR`**. Never "Submitted." Never "Sent." Never "Success."
- No exclamation marks anywhere — narration, lower-thirds, or on-screen.
- No emoji on screen or in voiceover. The single permitted decorative character is the typographic arrow `→` (used inside the UI's `Approve handoff →` button).
- Severity words are ranked **Normal → Low concern → Watch → Elevated → Critical**. The product never says "emergency" except for the postpartum-specific `EMERGENCY` chip the brief reserves.
- The hemodynamic trend rule (SBP drop ≥ 10 % AND HR rise ≥ 15 % over 2 h) is **operational, not validated**. Speak it that way if mentioned at all.
- Don't promise live EHR integration. The demo writes to **HAPI** (a synthetic FHIR server). Say "writes to the chart" or "writes a Communication and an AuditEvent to FHIR." Never "real EHRs."

---

## Pre-record dressing (do this once before take 1)

1. **Light mode** for beats 1–6, switch to **dark mode** in beat 7's transition. The theme toggle is in the top nav, right of the clinician pill.
2. Sign in as **Sarah Chen (RN, Post-op 4B)** at start. Switch to **Dr. Amit Patel (Intensivist)** before approving in beat 4. Switch to **Dr. Lindsay Park (Rapid Response)** before the postpartum patient in beat 5.
3. Re-seed HAPI so PT-001 / PT-007 / PT-009 / PT-010 timestamps fall inside the last two hours (`make demo-warmup`). PT-007 must have visible MAP-down + HR-up trend on the 24 h chart; PT-009 must have lactate > 4 and WBC > 18.
4. Set `LLM_PROVIDER=claude` for recording (Sonnet quality matters; Ollama is dev-only).
5. Pre-trigger one agent tick on the timeline so the trace already shows recent events when you cut to it. Don't open with an empty `awaiting events` state.

---

## Beat 1 (0:00–0:20) — Cold open: the bed that matters right now

**On screen.** Route `/patients`. Light theme. Browser at 1920×1080, Chrome zoom 110 %. Roster table visible edge-to-edge: 8 rows, sorted by risk. Critical row (PT-007) sits at the top with the pulsing red `●` dot in the leading risk-stripe column and a `CRITICAL` chip in the Risk column. Top nav shows the Vigil shield mark, five tabs (Roster · Alerts · Timeline · Marketplace · Settings), the theme toggle, and the clinician pill `SC · Sarah Chen · RN`.

**Action.**
- 0:00 — fade in over 200 ms from black to the roster, no logo card, no title swell.
- 0:04 — slow downward scroll of the roster (≤ 80 px) so the eye registers ward density.
- 0:10 — cursor arcs from the lower-right to the leading red dot on row PT-007 and rests there. Do not click.
- 0:18 — hold on the static frame.

**Voiceover (≈ 49 words).**
> Four point two million people die within thirty days of surgery every year. One woman dies every two minutes from obstetric complications. The warning signs appear thirty to sixty minutes before the crisis. One nurse watches eight beds. This is Vigil — a second pair of eyes on every post-op and postpartum bed.

**Why this beat.** The opening must earn the next 2:40 of attention. We pair the mortality stat (Mathur, Zheng) with the dense, real, sortable ward (Mandel sees real FHIR data; Proctor sees a clinical surface, not a marketing site). One bed is already pulsing red — the rest of the demo is about *that* bed.

**Editor note.** No title card, no music swell on the entry. A flat fade keeps the tone clinical.

---

## Beat 2 (0:20–0:45) — The agent watches

**On screen.** Route `/timeline`. Light theme. Page heading **Agent timeline · 7-state machine · polling every 2 s**, primary `Tick now` button top-right, `LIVE` indicator with green pulse-dot above the trace. Recent events visible newest-first: `POLLING`, `SCREENING`, `RISK_SCORING`, `SEPSIS_CHECK`, `ESCALATING`, `AWAITING_REVIEW` — each row is `time · state label · detail · ms`.

**Action.**
- 0:20 — click the **Timeline** tab in the top nav. The trace renders.
- 0:24 — cursor moves over the first three event rows in succession; the active row pulses an ink-coloured dot.
- 0:32 — click `Tick now`. A Sonner toast slides in: *Agent cycle triggered · Polling HAPI · running MCP tools · scoring risk*. Two new rows append at the top of the trace.
- 0:42 — cursor rests on the new `ESCALATING` row.

**Voiceover (≈ 64 words).**
> The agent runs a seven-state machine and polls every two seconds. It screens vitals against thresholds, scores deterioration with NEWS2 and qSOFA, checks for sepsis onset, and only then drafts the handoff. Every clinical decision is a deterministic rule from a published standard. The language model is the last step, and only writes prose. It never decides whether to escalate.

**Why this beat.** Establishes "deterministic first, LLM second" — the conservative architecture that keeps a clinical judge willing to keep watching. It also previews the four MCP tools by their state names, so when beat 3 opens the patient detail the judge already has the vocabulary.

**Editor note.** Hold the `Tick now` toast on screen for at least 1.5 seconds before it fades. It is the only proof that the trace is live, not a static screenshot.

---

## Beat 3 (0:45–1:15) — The flag

**On screen.** Route `/patients/PT-007`. Light theme. Two-column layout: left column shows the **Vitals · 24 hours** chart (HR red trace, MAP ink, SpO₂ green; dashed red flag-line at the moment Vigil escalated), then **Comorbidities** chips, then **Risk reasoning** panel with the score `6 / 12 · NEWS2` and three short bullets. Right column shows the SBAR card tagged `SBAR · DRAFT` with Situation / Background / Assessment / Recommend sections populated, an Approve bar beneath it, then a **Recent alerts** panel.

**Action.**
- 0:45 — click the **Roster** tab, then click the PT-007 row.
- 0:50 — cursor traces along the dropping MAP curve and the rising HR curve, then rests at the dashed flag-line.
- 0:58 — cursor moves down to the **Risk reasoning** panel; the `6` numeral and the bullets are visible.
- 1:08 — cursor moves to the SBAR `DRAFT` tag and lingers.

**Voiceover (≈ 76 words).**
> Patient seven. Day three post-op. Heart rate climbing, mean arterial pressure drifting down — and no single value has crossed a hard threshold. A rules engine would stay silent. The agent fires on the *pattern*: an operational rule, SBP down ten percent and HR up fifteen percent over two hours. NEWS2 reads six of twelve. qSOFA two of three. Every number on this panel is a real FHIR Observation, pulled by the agent in the last cycle.

**Why this beat.** This is Mathur's beat — pattern-not-threshold, the exact research area. It is also Mandel's second hit (real Observation IDs are visible in the chart's tile values). The `6 / 12 · NEWS2` numeral is large and tabular — that single glyph is what a judge remembers.

**Editor note.** The vitals chart is an SVG; cursor movement over the trace looks calmer than a hover-tooltip. Don't hover-pause, just move.

---

## Beat 4 (1:15–1:50) — The approve moment

**On screen.** Same route `/patients/PT-007`, scrolled so the SBAR card and the Approve bar are centred. Before approval: SBAR card tagged `SBAR · DRAFT`, Approve bar showing **Dismiss** · spacer · **Edit draft** · **Approve handoff →** (the primary button is the deep ink colour). Top-right clinician pill reads `AP · Dr. Amit Patel · ICU` (we switched in pre-record dressing).

**Action.**
- 1:15 — cursor reads down the SBAR sections one by one: Situation, Background, Assessment, Recommend. Allow ~1.0 s on each.
- 1:31 — cursor moves to **Approve handoff →**.
- 1:34 — click. Button shows `Approving…` for ~400 ms, then the entire Approve bar is replaced by the green attribution row: `AP · Approved by Dr. Amit Patel · 14:07 · written to EHR`. The SBAR header tag flips from `SBAR · DRAFT` to `SBAR · APPROVED`.
- 1:36 — Sonner toast bottom-right: *Handoff written to EHR for PT-007. Audit f4a17b9c…*. Hold for 2 s.
- 1:48 — pull-back zoom-out by 6 % to recompose for beat 5's transition.

**Voiceover (≈ 89 words).**
> Situation. Background. Assessment. Recommendation. SBAR is the format hospitals already use for rapid response. Vigil drafts every handoff in SBAR — and waits. The clinician reviews, the clinician approves. **Approved by Dr. Amit Patel, fourteen oh seven, written to EHR.** Behind that line: one FHIR Communication, one AuditEvent, posted by the proxy to HAPI. The agent never writes the chart on its own. Every action is attributable to the clinician who approved it. Vigil is a teammate, not a dashboard.

**Why this beat.** This is the emotional climax and the human-in-the-loop proof in one shot. Hickey gets the SBAR rigor. Proctor gets agentic action that closes the loop with a real FHIR write. Mandel gets the concrete resource pair (`Communication` + `AuditEvent`). The Approve attribution string is the single most-quoted line in the demo — read it cleanly, with one beat between **fourteen oh seven** and **written to EHR**.

**Editor note.** Do not insert a transition wipe between the click and the green attribution row — the in-product 180 ms slide-in is the whole point. If OBS drops a frame on the swap, re-record. The toast and the attribution row are different surfaces; both must be visible simultaneously for at least 1.5 s.

---

## Beat 5 (1:50–2:15) — Same pipeline, both wards

**On screen.** First frame: `/patients/PT-007` with the green Approve attribution still on screen. Then `/patients` roster, then `/patients/PT-009`. Light theme throughout. Top-right clinician pill changes mid-beat to `LP · Dr. Lindsay Park · RAPID`. PT-009 detail: same vitals chart layout, same NEWS2-style risk reasoning panel (this time tagged with sepsis-specific bullets — lactate 4.2, WBC 18, three days postpartum), same SBAR `DRAFT` card on the right.

**Action.**
- 1:50 — click the clinician pill in the top nav. The dropdown opens.
- 1:52 — click `Dr. Lindsay Park · RAPID`. The pill updates.
- 1:54 — click the **Roster** tab. PT-009 sits high in the sort by risk.
- 1:58 — click PT-009. The patient detail mounts.
- 2:04 — cursor traces the lactate bullet in the **Risk reasoning** panel, then the SBAR `Recommendation` section (which, for PT-009, names the postpartum sepsis bundle).
- 2:14 — hold.

**Voiceover (≈ 64 words).**
> Switch wards. Patient nine. Twenty-nine years old. Three days postpartum. Lactate four point two. White count eighteen. The same four MCP tools fire — screen vital thresholds, score risk, flag sepsis, draft the note. No ward branching. No conditional code. Postpartum sepsis is caught by the same pipeline that caught post-op deterioration. One agent. Two wards. Zero lines changed.

**Why this beat.** The architectural kill shot the brief calls "the moment of unity at 2:00." Zheng's hook lands here (260 K maternal deaths is implied by the patient and the bundle, but is stated explicitly in the closing beat — don't waste the words twice). Mandel gets a second confirmation of reusability. The clinician switcher proves the system also handles role-routing, which Proctor cares about.

**Editor note.** The clinician pill change must be a *deliberate* click — judges shouldn't miss it. Hold the open dropdown for ~600 ms before selecting Dr. Park.

---

## Beat 6 (2:15–2:35) — Marketplace

**On screen.** Route `/marketplace`. Light theme. Page heading **Prompt Opinion Marketplace · 2 listings · published · verified**. Two listing cards stacked:
1. `vigil-clinical-tools` · MCP Tool Library · Vigil Health · *FHIR read, NEWS2 / qSOFA scoring, SBAR drafter, audit log writer. 4 tools, versioned. SHARP-compliant.* · 2.4k installs · ★ 4.8
2. `vigil-ward-agent` · A2A Agent · Vigil Health · *Autonomous post-op / postpartum monitor. Deterministic 7-state machine. Human-in-the-loop by default.* · 810 installs · ★ 4.9

**Action.**
- 2:15 — click the **Marketplace** tab.
- 2:18 — cursor rests on the first listing for ~3 s.
- 2:22 — cursor moves to the second listing for ~3 s.
- 2:30 — pull back so both listings are visible in the same frame.

**Voiceover (≈ 49 words).**
> Both layers ship to the Prompt Opinion Marketplace. Path A — four reusable MCP tools any agent can call, FHIR-aware, SHARP-compliant. Path B — the autonomous ward agent, human-in-the-loop by default. Same FHIR contract, same three SHARP headers, two installable products. Any hospital with a FHIR endpoint can install either path.

**Why this beat.** Re-frames Vigil from a demo to a *platform*. Mandel's reusability hook (Path A is what every other agent can call) and Mathur / Zheng's "I want this in my hospital today" hook both land here. SHARP gets a single explicit mention so the Prompt Opinion judges hear the compliance word.

**Editor note.** Don't click into either listing — the marketplace surface is intentionally read-only in the demo, and a 404 from a missing detail page would be the worst possible cut.

---

## Beat 7 (2:35–3:00) — Close

**On screen.** Two halves.
- 2:35–2:48: route `/settings`. Theme switches to **dark** at 2:35 (hit the theme toggle). Heading **System health · all green · last check 14:02:11**. Four panels in a 2×2 grid:
  - LLM provider · `claude-sonnet-4.5` · OPERATIONAL
  - FHIR gateway · R4 endpoint · OPERATIONAL
  - Agent heartbeat · poll interval 2 s · HEARTBEAT
  - Prompt Opinion SHARP · 3 headers wired · RUNTIME
- 2:48–3:00: cut to a centred Vigil mark on a flat dark surface; the wordmark `Vigil` fades up beneath it.

**Action.**
- 2:35 — hit the theme toggle. Dark mode renders.
- 2:36 — click the **Settings** tab.
- 2:40 — cursor visits each `OPERATIONAL` / `HEARTBEAT` / `RUNTIME` chip in turn (~1 s each).
- 2:48 — fade through dark to the centered mark.
- 2:54 — wordmark fades up.
- 2:58 — URL line appears bottom-centre, small mono: *github.com/raymond/vigil · devpost.com/software/vigil*.

**Voiceover (≈ 64 words).**
> LLM provider, FHIR gateway, agent heartbeat, SHARP runtime — all green. Four point two million post-op deaths a year. Two hundred sixty thousand mothers. The pattern is in the chart thirty minutes before the crisis. Vigil reads the pattern, drafts the handoff, and waits for the clinician to approve. One platform. Two paths. Published to the Prompt Opinion Marketplace.

**Why this beat.** Closes on the operational truth (everything is wired, the system is real) and the moral truth (the deaths are preventable, the signals are already in the chart). No call-to-action verb — the URL is the call-to-action. The closing line is structured so the cadence falls on **One platform. Two paths.** for the cut to black.

**Editor note.** Hold black for ~1.5 s after the URL fades before ending the file. Don't stack a "Thanks for watching" card.

---

## Time and word budget

| Beat | Window | Seconds | Word target (≈ 156 wpm) | Actual draft |
|---|---|---|---|---|
| 1 — Cold open | 0:00–0:20 | 20 | 52 | 49 |
| 2 — The agent watches | 0:20–0:45 | 25 | 65 | 64 |
| 3 — The flag | 0:45–1:15 | 30 | 78 | 76 |
| 4 — The approve moment | 1:15–1:50 | 35 | 91 | 89 |
| 5 — Same pipeline, both wards | 1:50–2:15 | 25 | 65 | 64 |
| 6 — Marketplace | 2:15–2:35 | 20 | 52 | 49 |
| 7 — Close | 2:35–3:00 | 25 | 65 | 64 |
| **Total** | **3:00** | **180** | **468** | **455** |

Rehearse at ~150 wpm. The 13-word headroom absorbs natural pauses on the Approve attribution line (beat 4) and the patient-handoff to PT-009 (beat 5). If a take runs long, trim from beat 6's voiceover before any other beat — that beat's *visual* is what carries the marketplace point.

---

## Frame-level checklist (run through this before take 1)

- [ ] Roster (`/patients`) renders 8 rows with critical at the top and a visible pulsing red dot on PT-007.
- [ ] Timeline (`/timeline`) shows recent events. `Tick now` succeeds and appends rows.
- [ ] PT-007 detail shows the dashed flag line on the vitals chart and a populated SBAR draft.
- [ ] PT-009 detail shows lactate 4.2 and WBC 18 in the risk reasoning bullets.
- [ ] Clinician switcher cleanly shows AP and LP options without scroll.
- [ ] Approve handoff on PT-007 transitions cleanly: `Approving…` → green attribution row + Sonner toast + SBAR header flip to `APPROVED`. All within 600 ms.
- [ ] Marketplace shows both listings without horizontal scroll at 1920×1080 zoom 110 %.
- [ ] Settings shows four green status chips and the dark-mode theme renders.
- [ ] No browser tab title peeking, no extension icons visible, no bookmarks bar.

---

## What this storyboard deliberately does not include

- **Lower-thirds and on-screen captions.** The user does the edit. A single bottom-right URL card in beat 7 is the only enforced supered text.
- **Music or stock B-roll.** The design rules forbid stock healthcare imagery. Either ambient room tone or a single quiet bed of strings — the user decides at the edit.
- **A 30-second teaser cut.** That variant exists in `DEMO_SCRIPT.md §8`; we do not duplicate it here.
- **Branching for outage modes.** If the agent or HAPI is unhealthy, abort the take and re-warm, do not improvise.

---

*End of storyboard. The next document the user owns is the OBS scene preset and the recorded takes. Everything visible above is in the running app at the routes named.*
