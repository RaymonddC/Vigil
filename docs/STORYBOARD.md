# Vigil demo storyboard — 3 minute video

_Target: 3:00 ± 0:10 · 30 fps · 1920×1080 · screen-record + voiceover_
_Voice: clinical-direct. Third person about the patient. Second person to the clinician. The AI is "Vigil" or "the agent" — never "we," never "I."_

This document is the **visual layer** for the hackathon submission video. The hero of every beat after the cold open is the **Prompt Opinion launchpad chat invoking Vigil over A2A** — that is the marketplace surface judges score, and it is the path empirically proven end-to-end on 2026-04-27 (`docs/A2A_LOCAL_SMOKE.md`). The Next.js dashboard is a portfolio surface used for context framing (beat 1) and for the human-in-the-loop approve moment (beat 6); it is never the climax.

A video editor reading this storyboard alone should be able to record the demo without asking questions: every beat names the exact route or screen, the exact viewport, the exact element clicked, and the timestamp window.

---

## Voice and copy rules (enforced)

- **The Approve attribution string is sacred.** On screen, in voiceover, and in any title card it appears verbatim: **`Approved by Dr. Amit Patel · 14:07 · written to EHR`**. Never "Submitted." Never "Sent." Never "Success."
- No exclamation marks anywhere — narration, lower-thirds, or on-screen.
- No emoji on screen or in voiceover. The single permitted decorative character is the typographic arrow `→` (used inside the dashboard's `Approve handoff →` button).
- Severity words are ranked **Normal → Low concern → Watch → Elevated → Critical**. The product never says "emergency" except for the postpartum-specific `EMERGENCY` chip the brief reserves.
- The hemodynamic trend rule (SBP drop ≥ 10 % AND HR rise ≥ 15 % over 2 h) is **operational, not validated**. Speak it that way if mentioned at all.
- Don't promise live EHR integration. The demo writes to **HAPI** (a synthetic FHIR server) plus the Prompt Opinion workspace FHIR server. Say "writes a Communication and an AuditEvent to the chart." Never "real EHRs."

---

## Pre-record dressing (do this once before take 1)

1. **Light mode** for beats 1–6, switch to **dark** in beat 7's transition. The theme toggle is in the dashboard top nav.
2. **Prompt Opinion side**, signed in to `app.promptopinion.ai`:
   - Workspace Models: Gemini API key already loaded; default model **Gemini 3.1 Flash Lite**.
   - Workspace Hub: a patient is selected as active context with at least one clinical note attached, so Prompt Opinion has grounding content for general chat.
   - Workspace Hub: the **Vigil** A2A connection is added by public URL, the agent card is verified, the API key is pasted, the **FHIR-context extension toggle is on**, and the connection shows green.
   - Marketplace Studio: the `vigil-ward-agent` listing draft is open in a second tab so beat 7 can cut to it without a search.
3. **Vigil side**, on the same EC2 host serving the public URL Prompt Opinion is wired to:
   - `LLM_PROVIDER=gemini` for the agent (so `vigil.draft_sbar` returns real Gemini prose, not the stub template).
   - `MCP` and `A2A` services healthy. ngrok or Caddy reachable from Prompt Opinion. `app.promptopinion.ai` is in `ALLOWED_FHIR_HOSTS`.
   - `make demo-warmup` has run: HAPI reseeded, an agent tick has been triggered, and the dashboard's `/patients` and `/patients/PT-007` routes are warmed.
4. **Dashboard side** (used in beats 1, 4, and 6 only):
   - Sign in as **Sarah Chen (RN, Post-op 4B)** at start. Switch to **Dr. Amit Patel (Intensivist)** before beat 6.
   - PT-007 row sits at the top of the roster, sorted by risk, with the pulsing red `●` dot.
5. **Browser hygiene.** No bookmarks bar, no extension icons, no second tab title peeking, no notification badges in the OS dock. The Prompt Opinion launchpad and the dashboard run in two separate Chrome windows so the editor can cut between them without switching tabs on screen.

---

## Beat 1 (0:00–0:25) — Cold open: the bed that matters right now

**On screen.** Vigil dashboard, route `/patients`. Light theme. Browser at 1920×1080, Chrome zoom 110 %. Roster table edge-to-edge: 8 rows, sorted by risk. The critical row (PT-007) sits at the top with the pulsing red `●` dot in the leading risk-stripe column and a `CRITICAL` chip in the Risk column. Top nav shows the Vigil shield mark, route tabs, the theme toggle, and the clinician pill `SC · Sarah Chen · RN`.

**Action.**
- 0:00 — fade in over 200 ms from black to the roster. No logo card, no title swell.
- 0:04 — slow downward scroll of the roster (≤ 80 px) so the eye registers ward density.
- 0:12 — cursor arcs from the lower-right to the leading red dot on row PT-007 and rests there. Do not click.
- 0:22 — hold on the static frame.

**Voiceover (≈ 60 words, ~24 s at 150 wpm).**
> Four point two million people die within thirty days of surgery every year. One woman dies every two minutes from obstetric complications. The warning signs sit in the chart thirty to sixty minutes before the crisis. One nurse watches eight beds. This is Vigil — a second pair of eyes on every post-op and postpartum bed.

**Why this beat — Potential Impact.** The opening earns the next 2:35 of attention. The mortality stats land Mathur and Zheng. The dense, real, sortable ward roster lands Mandel (this is real FHIR data) and Proctor (a clinical surface, not a marketing site). One bed is already pulsing red; the rest of the demo is about *that* bed.

**Editor note.** No title card, no music swell on entry. A flat fade keeps the tone clinical.

---

## Beat 2 (0:25–0:45) — One minute to decide

**On screen.** Same route `/patients`, but the camera tightens: cursor hovers PT-007's row, the row's hover state fires (`surface-2` background, no scale, no shadow). Lower third of the frame still shows three other rows of the dense roster — context that PT-007 is one bed of many.

**Action.**
- 0:25 — cursor moves up the row, pausing on the `Risk: CRITICAL` chip, the `Last vitals: 14:01` cell, and the `Alert: Pattern · NEWS2 6/12` cell.
- 0:35 — cursor hovers the row but does **not** click. Hold on the populated row for 8 s.
- 0:43 — cursor drifts to the right edge of the screen, anticipating the cut to Prompt Opinion.

**Voiceover (≈ 50 words, ~20 s).**
> The clinician has one minute to decide whether this patient needs escalation. Eight beds. Twelve trends per bed. Cognitive load is the bottleneck, not data. A second pair of eyes — one that reads every chart on every cycle, and only speaks when a published clinical standard says it should.

**Why this beat — Potential Impact.** Sets up the *why-AI* question without naming the AI yet. Frames cognitive load as the human limit, which is the entry point for Mathur's research interest and Proctor's "agentic AI that takes action" axis.

**Editor note.** The cut at 0:45 is hard, no fade. The next frame is Prompt Opinion's launchpad. The contrast between "the clinician's view" and "the platform-native consult" is the point of the cut.

---

## Beat 3 (0:45–1:30) — The Prompt Opinion launchpad invocation

**On screen.** Prompt Opinion launchpad chat, route `app.promptopinion.ai/launchpad` (or whatever the host's running URL is). The patient context selector at the top of the chat shows the same patient identifier as PT-007 (the synthetic test patient set in pre-record dressing). The general chat agent (Gemini) is the active agent. The Vigil A2A connection appears in the chat's tool sidebar with a green dot, labelled `vigil-ward-agent · A2A · 5 skills`.

**Action.**
- 0:45 — hard cut from the dashboard to the launchpad. The chat input is empty and focused.
- 0:48 — keystrokes appear in the input field, typed at a natural cadence:

  > Use Vigil to draft an SBAR for this patient.

- 0:55 — the user hits Enter. The general chat agent's response begins streaming. The chat shows two tool-call cards inline:
  1. `GetPatientData` — *resolved patient context, attached note*
  2. `SendA2AMessage` — *target: vigil-ward-agent · skill: vigil.draft_sbar*
- 1:02 — the `SendA2AMessage` card expands. A status line reads *Vigil is drafting…* for ~2 seconds. The card resolves.
- 1:05 — Vigil's response renders inline in the chat as a structured SBAR card:

  > **Situation.** Patient is three days post-op, tachycardic at 118 bpm, mean arterial pressure trending down over the last two hours.
  > **Background.** Open abdominal surgery on day zero. No prior cardiac history. Lactate 2.1, white count 13.
  > **Assessment.** NEWS2 6 of 12. qSOFA 2 of 3. Pattern consistent with early deterioration. Sepsis screen negative on CDC criteria.
  > **Recommendation.** Escalate to the rapid response team. Recheck lactate in one hour. Consider broad-spectrum antibiotics if a source is identified.

  (The exact prose is whatever Gemini drafts on the take — these four sections in this order are the load-bearing requirement.)
- 1:22 — the cursor scrolls slowly down the SBAR card so each section is visible in turn. Hold the final frame on the Recommendation block.

**Voiceover (≈ 110 words, ~44 s).**
> Vigil is published as an A2A agent on the Prompt Opinion Marketplace. Any clinician on the platform can consult it from chat. The general chat agent reads the patient context, calls Vigil over A2A, and Vigil takes over. The agent reads vitals from the workspace FHIR server using the SHARP context Prompt Opinion injects on every call. It runs four deterministic clinical screens — vital thresholds against MEWT, deterioration scoring with NEWS2 and qSOFA, sepsis screen against the CDC adult sepsis event criteria — and then asks Gemini to draft an SBAR a clinician can act on. Situation, background, assessment, recommendation. The format hospitals already use for rapid response.

**Why this beat — AI Factor.** This is the heart of the submission. The platform-native invocation (`SendA2AMessage` resolved by Prompt Opinion's general chat) is exactly what the host's getting-started video tells builders to demonstrate. The LLM-drafted SBAR is the moment the model does what rules cannot — it writes clinically natural prose grounded in the rule output. The agent card and skill resolution are visible on screen, so the platform compliance proof is in-frame.

**Editor note.** Do not cut away from the launchpad during the drafting state. The 2-second *Vigil is drafting…* status is the proof the call is live, not a static screenshot. If Gemini takes longer than 4 s on the take, hold the camera; do not splice. If it takes shorter, hold the rendered SBAR longer to absorb the surplus.

---

## Beat 4 (1:30–1:55) — Under the hood: deterministic rules first, LLM second

**On screen.** Picture-in-picture. The Prompt Opinion launchpad stays in the main frame at 60 % opacity, the rendered SBAR still visible. A bottom-right inset (≈ 480×270 px, hard 1 px ink border) shows the agent's structured-log tail — five lines, monospace, large enough to read:

```
14:06:58  skill_router  resolved vigil.draft_sbar (PT-007)
14:06:58  mcp.call      screen_vital_thresholds → 2 breaches (HR, MAP-trend)
14:06:59  mcp.call      score_deterioration_risk → NEWS2 6/12 · band=elevated
14:06:59  mcp.call      flag_sepsis_onset → not_suspected (cdc_ase)
14:07:00  mcp.call      generate_escalation_note → llm=gemini · 1.4 s
14:07:01  a2a.response  task=completed parts=1
```

**Action.**
- 1:30 — the inset slides in from the bottom-right (`motion-base`, 180 ms ease-out), no shadow.
- 1:33 — cursor in the inset traces line by line down the four `mcp.call` rows.
- 1:48 — the inset fades out at 30 % opacity but stays on screen. The main frame rises back to 100 %.
- 1:54 — the inset is gone.

**Voiceover (≈ 62 words, ~25 s).**
> Every threshold cites a public clinical standard. MEWT for vital screens. NEWS2 and qSOFA for risk. The CDC adult sepsis event criteria for sepsis screening. The language model never decides whether to escalate — the rules do. The model writes the prose a human can act on. Four chained tool calls, every one of them auditable, every one of them traceable to a published source.

**Why this beat — Feasibility.** This is the conservative-architecture proof. A clinical judge needs to see that the LLM is fenced, not steering. Mandel and Hickey both score on this. The log inset shows four named tools resolving in order, with timings, with the LLM step explicitly last and explicitly bounded.

**Editor note.** The log is an OBS browser-source capture of the agent's actual stdout via `journalctl` on the EC2 host (or `docker compose logs a2a` on the local rehearsal). Do not type-set fake log lines — judges who care about this beat will spot synthetic logs in a heartbeat.

---

## Beat 5 (1:55–2:20) — Same pipeline, two wards

**On screen.** Back to the Prompt Opinion launchpad, full frame. The patient context selector at the top of the chat changes mid-beat from the post-op patient to a postpartum patient (the synthetic PT-009 trajectory: 29 years old, three days postpartum, lactate 4.2, WBC 18). The chat history from beat 3 has been cleared so the new prompt is the first message in the visible window.

**Action.**
- 1:55 — click the patient context selector. The dropdown opens.
- 1:57 — select the postpartum patient. The selector updates; the attached clinical note in the sidebar refreshes.
- 2:00 — the same prompt is typed into the chat:

  > Use Vigil to draft an SBAR for this patient.

- 2:06 — Enter. Same `SendA2AMessage` card resolves. Vigil's response renders inline as a new SBAR card. The Recommendation section names the postpartum sepsis bundle (broad-spectrum antibiotics, source control, rapid response activation). The Assessment chip reads `EMERGENCY` (the postpartum-specific severity).
- 2:18 — hold on the rendered Recommendation.

**Voiceover (≈ 62 words, ~25 s).**
> Switch wards. Same prompt. Same agent. Same four tools. Postpartum hemorrhage and sepsis kill one woman every two minutes globally. Vigil's pipeline does not branch on ward — it cites the right criteria, drafts the right bundle, and calls the right severity. One agent, two wards, zero conditional code. The same path the post-op nurse used a moment ago.

**Why this beat — Potential Impact.** The architectural unity moment the brief calls "the 2:00 climax." Zheng's hook — maternal mortality is her thesis — lands on the postpartum patient. Mandel sees the reusability: same MCP tools, same A2A skill, different criteria fired by the trajectory. Proctor sees an agentic system that generalizes across cohorts.

**Editor note.** Do not cut between the patient-switch and the new prompt. The 11-second window where the same prompt produces a different SBAR with a different severity chip is the entire point. If the take fumbles the dropdown, restart the take from 1:55.

---

## Beat 6 (2:20–2:40) — Human in the loop

**On screen.** Cut from the launchpad to the Vigil dashboard, route `/patients/PT-007`, scrolled so the SBAR card and the Approve bar are centred. The SBAR card shows the same structured prose Gemini drafted in beat 3, tagged `SBAR · DRAFT`. Approve bar shows **Dismiss** · spacer · **Approve handoff →** (the primary button is the deep ink colour). Top-right clinician pill reads `AP · Dr. Amit Patel · ICU` (switched during pre-record dressing).

**Action.**
- 2:20 — hard cut from the launchpad to the dashboard. The SBAR card and Approve bar are already in frame.
- 2:23 — cursor moves to **Approve handoff →**.
- 2:26 — click. Button shows `Approving…` for ~400 ms, then the entire Approve bar is replaced by the green attribution row: **`Approved by Dr. Amit Patel · 14:07 · written to EHR`**. The SBAR header tag flips from `SBAR · DRAFT` to `SBAR · APPROVED`.
- 2:28 — Sonner toast bottom-right: *Handoff written to EHR for PT-007. Audit f4a17b9c…*. Hold for 2 s.
- 2:38 — pull-back zoom-out by 6 % to recompose for beat 7.

**Voiceover (≈ 50 words, ~20 s).**
> Vigil drafts. The clinician approves. **Approved by Dr. Amit Patel, fourteen oh seven, written to EHR.** Behind that line: one FHIR Communication, one AuditEvent, posted to the chart. The agent never writes alone. Every alert that touches the record carries a clinician's signature.

**Why this beat — Feasibility.** The human-in-the-loop guarantee, on screen, with a real FHIR write. Hickey gets the SBAR rigor. Proctor gets agentic action that closes the loop with a real chart write. Mandel gets the concrete resource pair (`Communication` + `AuditEvent`). The Approve attribution string is the single most-quoted line in the demo — read it cleanly, with one beat between **fourteen oh seven** and **written to EHR**.

**Editor note.** Do not insert a transition wipe between the click and the green attribution row — the in-product 180 ms slide-in is the whole point. If OBS drops a frame on the swap, re-record. The toast and the attribution row are different surfaces; both must be visible simultaneously for at least 1.5 s.

---

## Beat 7 (2:40–3:00) — Marketplace, standards, close

**On screen.** Two halves.
- 2:40–2:52: route `app.promptopinion.ai/marketplace` (the Marketplace Studio listing for `vigil-ward-agent`). Light theme. Listing card shows the agent name, the Vigil mark, the description block (`Autonomous post-op / postpartum monitor. Deterministic 7-state pipeline. Human-in-the-loop by default. SHARP-compliant.`), the 5 declared skills as chips, install count, and rating. A second listing tile for `vigil-clinical-tools` (MCP) is visible below in the same frame.
- 2:52–3:00: theme switches to **dark** at 2:52 (hit the theme toggle as the cut happens). Cut to a centred Vigil mark on a flat dark surface; the wordmark `Vigil` fades up beneath it. Bottom-centre, small mono: `github.com/raymond/vigil · devpost.com/software/vigil`.

**Action.**
- 2:40 — cut to the marketplace listing. Cursor rests on the `vigil-ward-agent` card.
- 2:46 — cursor moves down to the `vigil-clinical-tools` card.
- 2:50 — pull back so both listings are in the same frame.
- 2:52 — cut to dark; mark fades in.
- 2:56 — wordmark fades up.
- 2:58 — URL line appears.

**Voiceover (≈ 50 words, ~20 s).**
> Vigil is published on the Prompt Opinion Marketplace. The A2A agent and the four MCP tools it calls. Built on the standards Prompt Opinion is built on — MCP, A2A, FHIR, SHARP. A second pair of eyes on every post-op and postpartum bed.

**Why this beat — AI Factor and Feasibility together.** Re-frames Vigil from a demo to a *marketplace product*. Mandel's reusability hook (the MCP tools any other agent on the platform can call) and the Prompt Opinion judges' compliance hook (MCP + A2A + FHIR + SHARP named in one breath) both land here. The closing line is structured so the cadence falls on **post-op and postpartum bed** for the cut to black.

**Editor note.** Do not click into either listing — the marketplace is intentionally read-only in the demo, and a 404 from a missing detail page would be the worst possible cut. Hold black for ~1.5 s after the URL fades before ending the file. Don't stack a "Thanks for watching" card.

---

## Time and word budget

| Beat | Window | Seconds | Word target (≈ 150 wpm) | Actual draft |
|---|---|---|---|---|
| 1 — Cold open | 0:00–0:25 | 25 | 62 | 60 |
| 2 — One minute to decide | 0:25–0:45 | 20 | 50 | 50 |
| 3 — Launchpad invocation | 0:45–1:30 | 45 | 112 | 110 |
| 4 — Under the hood | 1:30–1:55 | 25 | 62 | 62 |
| 5 — Same pipeline, two wards | 1:55–2:20 | 25 | 62 | 62 |
| 6 — Human in the loop | 2:20–2:40 | 20 | 50 | 50 |
| 7 — Close | 2:40–3:00 | 20 | 50 | 49 |
| **Total** | **3:00** | **180** | **448** | **443** |

Rehearse at ~150 wpm. The 5-word headroom absorbs the deliberate pause on the Approve attribution line in beat 6 and the patient-switch dropdown in beat 5. If a take runs long, trim from beat 4's voiceover before any other beat — that beat's *visual* (the four-line MCP-call log inset) carries the architecture point on its own.

---

## Frame-level checklist (run through this before take 1)

- [ ] Dashboard `/patients` renders 8 rows with PT-007 critical at the top and a visible pulsing red dot.
- [ ] Prompt Opinion launchpad has the Vigil A2A connection green-dotted with all 5 skills visible in the sidebar.
- [ ] Patient context selector in the launchpad shows the post-op patient at start and the postpartum patient is one click away in the dropdown.
- [ ] Typing the prompt produces two tool-call cards in order: `GetPatientData`, then `SendA2AMessage` targeting `vigil.draft_sbar`.
- [ ] Vigil's SBAR response renders inline as four labelled sections (Situation / Background / Assessment / Recommendation). The render completes within 6 s on a warm Gemini key.
- [ ] The agent log inset for beat 4 shows four `mcp.call` lines plus the `a2a.response` line, all timestamped, all readable at 1920×1080.
- [ ] Postpartum take in beat 5 produces a different SBAR with a postpartum sepsis bundle in Recommendation and the `EMERGENCY` chip in Assessment.
- [ ] Dashboard PT-007 detail shows the SBAR card with `Approve handoff →` button visible above the fold.
- [ ] Approve transitions cleanly: `Approving…` → green attribution row + Sonner toast + SBAR header flip to `APPROVED`. All within 600 ms.
- [ ] Marketplace shows both `vigil-ward-agent` and `vigil-clinical-tools` listings in the same frame at 1920×1080.
- [ ] No browser tab title peeking, no extension icons visible, no bookmarks bar, no notification badges on the OS dock.

---

## What this storyboard deliberately does not include

- **The dashboard's Edit-draft button.** It is unwired. Do not film it.
- **Token-flow caveats.** If `vigil.screen_vitals` or `vigil.score_risk` is invoked from chat without a SMART-on-FHIR scoped bearer in SHARP context, the agent honestly returns a friendly fallback. That is correct behaviour but it is not the demo path. The demo path is `vigil.draft_sbar`, which has a graceful fallback that produces real Gemini prose even without FHIR observations. Beat 3 and beat 5 both call `vigil.draft_sbar`. Do not invoke the others on camera.
- **Code or terminal screenshots that aren't load-bearing.** The only terminal-style content that earns its frame is the four-line MCP-call log inset in beat 4.
- **Footage of the dashboard alone without launchpad context.** The dashboard appears in beat 1 (ward framing) and beat 6 (human-in-the-loop write). Every other dashboard moment is cut.
- **Lower-thirds and on-screen captions.** The user does the edit. A single bottom-right URL card in beat 7 is the only enforced supered text.
- **Music or stock B-roll.** The design rules forbid stock healthcare imagery. Either ambient room tone or a single quiet bed of strings — the user decides at the edit.
- **Branching for outage modes.** If the agent, MCP, or Prompt Opinion is unhealthy, abort the take and re-warm. Do not improvise.

---

*End of storyboard. The next document the user owns is the OBS scene preset and the recorded takes. Everything visible above is reachable in the running stack at the routes named.*
