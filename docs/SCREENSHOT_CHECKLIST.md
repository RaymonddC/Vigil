# Vigil — Screenshot Checklist

> **For the person recording the demo** — capture these shots while the stack is live.
> Every shot is a still frame pulled from a beat in `docs/DEMO_SCRIPT.md`.
> These become README hero images and Prompt Opinion marketplace card assets.

---

## Global rig settings (apply to every shot)

| Setting | Value |
|---|---|
| Browser | Chrome (no extensions) |
| Zoom | **110 %** (`Ctrl +` until Chrome address bar shows 110) |
| Window size | **1920 × 1080** (use Window Resizer extension or OBS canvas) |
| Theme | **Light mode** (system or browser, not dark) |
| Bookmarks bar | Hidden (`Ctrl+Shift+B` to toggle off) |
| Dev Tools | Closed (open separately after the shot to verify, then close) |
| Cursor | Move off-screen or to a neutral corner **before** taking the shot |
| Notifications | All silenced (Do Not Disturb on) |

Pre-warm every URL with `curl` before taking shots so no skeleton/loading state appears.

---

## Shot 01 — Patient list, all risk levels visible

| Field | Value |
|---|---|
| **URL** | `http://localhost:3000/` |
| **File** | `docs/img/01-patients-list.png` |
| **Demo beat** | 0:15–0:20 |
| **Judge hook** | Mathur (risk triage at a glance), Mandel ("live FHIR server") |

**What must be visible:**
- Header: "Vigil · Post-op Unit 4B · Dr. A. Chen" + settings gear
- Filter pills: `All 10` selected (not "High+" or "Triggered")
- At minimum 4 rows showing one of each risk level:
  - One **CRITICAL** badge (red) — e.g. Reyes, Maria — MRN 102394
  - One **HIGH** badge (amber) — e.g. PT-007 patient
  - One **MED** badge (yellow) — e.g. Novak, Irena
  - One **LOW** or **NORMAL** badge (blue/green) — e.g. Tanaka, Yuki / PT-001
- Columns: Name, MRN, Procedure, T+ OR, Risk, Alert, →
- No horizontal scrollbar visible

**Annotation overlay (add in post):**
- Arrow pointing to the CRITICAL row with callout: `"FHIR Observation — live"`
- Small box around filter pills row labeling them: `"Risk filter"`

---

## Shot 02 — PT-001 stable, flat vitals chart

| Field | Value |
|---|---|
| **URL** | `http://localhost:3000/patients/PT-001` |
| **File** | `docs/img/02-pt001-stable.png` |
| **Demo beat** | 0:25–0:30 |
| **Judge hook** | Mathur ("no false alarm" — the boring case is the first proof) |

**What must be visible:**
- Patient header: name, MRN, procedure, day, `NORMAL` or `LOW` RiskBadge (green/blue)
- `VitalsChart` — all 5 lines (HR, SpO2, MAP, RR, Temp) flat or gently sloping **downward** (recovering)
- Y-axis numbers readable; X-axis time labels visible (T+0h..T+8h range)
- Alert timeline sidebar: empty or showing only LOW/NORMAL entries
- **No** "What triggered" card rendered (it only shows for HIGH+)

**Annotation overlay:**
- Callout box on chart legend: `"5 FHIR vitals · updated every 15 min"`
- Arrow to the NORMAL badge: `"Agent: IDLE — no escalation"`

---

## Shot 03 — PT-001 with FHIR tooltip on badge/link

| Field | Value |
|---|---|
| **URL** | `http://localhost:3000/patients/PT-001` |
| **File** | `docs/img/03-pt001-fhir-tooltip.png` |
| **Demo beat** | 0:35–0:40 |
| **Judge hook** | Mandel (real FHIR resource IDs, not mocked data) |

**What must be visible:**
- Same patient detail page as Shot 02
- A tooltip/popover is open on a FHIR resource badge or the vitals chart, showing something like `Observation/obs-pt001-001`
- If the tooltip doesn't exist in the current build, hover over a vital number so the Recharts tooltip appears showing the full reading row

**Annotation overlay:**
- Rectangle highlight around the tooltip bubble
- Label: `"FHIR R4 Observation resource (live HAPI store)"`

---

## Shot 04 — PT-007 deteriorating vitals (the pattern reveal)

| Field | Value |
|---|---|
| **URL** | `http://localhost:3000/patients/PT-007` |
| **File** | `docs/img/04-pt007-deteriorating.png` |
| **Demo beat** | 0:50–1:00 |
| **Judge hook** | Mathur (pattern not threshold), Mandel (6h of FHIR observations) |

**What must be visible:**
- Patient header: HIGH or CRITICAL RiskBadge (amber/red)
- `VitalsChart` showing a clear **6-hour deterioration arc**:
  - HR line (red `#DC2626`) trending **up** — should reach ≥ 110 bpm at the right edge
  - MAP line (purple `#7C3AED`) trending **down** — should reach ≤ 70 at the right edge
  - SpO2 line (blue `#2563EB`) trending **down** slightly
  - RR line (teal `#0891B2`) trending **up**
- "What triggered" card visible (renders for HIGH+): "Sustained HR ↑ + MAP ↓…"
- Alert timeline sidebar showing at least 2 alerts (HIGH, CRITICAL)

**Annotation overlay:**
- Two arrows: one pointing to HR slope (label `"HR ↑"`), one to MAP slope (label `"MAP ↓"`)
- Callout box on the "What triggered" card: `"Pattern detected across 6h — no single threshold crossed"`

---

## Shot 05 — PT-007 with 4 MCP tool calls in agent/sidebar panel

| Field | Value |
|---|---|
| **URL** | `http://localhost:3000/patients/PT-007` |
| **File** | `docs/img/05-pt007-tool-calls.png` |
| **Demo beat** | 1:05–1:10 |
| **Judge hook** | Mandel (real MCP calls), Proctor (draft not write) |

**What must be visible:**
- All 4 tool call entries visible in the agent activity panel or network/sidebar:
  1. `screen_vital_thresholds` — result: TRIGGERED
  2. `score_deterioration_risk` — result: HIGH
  3. `flag_sepsis_onset` — result: POSSIBLE
  4. `generate_escalation_note` — result: draft SBAR
- Each row shows tool name + status (completed / streaming)
- The `generate_escalation_note` row should be highlighted or last in sequence
- Label or callout: "draft — not persisted" near the final row

> **Note:** If the dashboard doesn't have an agent-activity panel, capture the browser Network tab (DevTools → Network) filtered to `/api/` showing the 4 sequential POST calls. Take this shot in a second browser window so the main window stays clean.

**Annotation overlay:**
- Number labels 1–4 next to each tool call row
- Callout on row 4: `"Returns a draft — nothing written to FHIR yet"`

---

## Shot 06 — PT-007 alert detail, full SBAR

| Field | Value |
|---|---|
| **URL** | `http://localhost:3000/patients/PT-007/alerts/[use-seeded-alert-id]` |
| **File** | `docs/img/06-pt007-sbar-full.png` |
| **Demo beat** | 1:15–1:40 |
| **Judge hook** | Hickey (S-B-A-R rigor), Proctor (approve button pattern) |

**What must be visible:**
- EMERGENCY bar at top (red left-border stripe, `"EMERGENCY — Rapid Response recommended"`)
- Countdown timer: `"09:xx until auto-escalate"` (capture while timer is counting)
- 2×2 SBAR grid — all four cards populated:
  - **S: Situation** — includes age, procedure, trigger summary
  - **B: Background** — surgical context
  - **A: Assessment** — qSOFA score, concern statement
  - **R: Recommendation** — "Call RRT. Blood cultures, lactate…"
- Contributing signals row at bottom (HR, SpO2, MAP, RR, Temp sparklines + arrows)
- Both buttons visible: **"Approve & send RRT"** (blue primary) and **"Dismiss"** (outline ghost)
- Countdown timer should NOT be at 10:00 (that looks un-started); aim for 09:30–09:50

**Annotation overlay:**
- Bracket around the 4 SBAR cards: `"AI-generated SBAR — clinician-reviewed before any action"`
- Arrow to "Approve & send RRT": `"Single click → FHIR Communication + AuditEvent"`

---

## Shot 07 — Approve toast confirmation

| Field | Value |
|---|---|
| **URL** | `http://localhost:3000/patients/PT-007/alerts/[same-alert-id]` |
| **File** | `docs/img/07-pt007-approved-toast.png` |
| **Demo beat** | 1:45 |
| **Judge hook** | Proctor (closed loop, audit trail) |

**What must be visible:**
- Sonner toast in bottom-right corner: `"Communication/comm-884 written — audit audit_xxx"`
  (replace with whatever the seeded system returns)
- Toast should be fully visible and not cropped by the window edge
- The main SBAR page still visible behind the toast
- "Approve & send RRT" button in a disabled/submitted state if the component supports it

> **Timing:** Click "Approve & send RRT", then immediately take the screenshot when the toast appears. You have ~3 seconds before it auto-dismisses. Consider pausing the recording on this frame.

**Annotation overlay:**
- Rectangle highlight around the toast
- Label: `"FHIR write: Communication + AuditEvent. Audit trail captured."`

---

## Shot 08 — PT-009 postpartum sepsis, CRITICAL badge

| Field | Value |
|---|---|
| **URL** | `http://localhost:3000/patients/PT-009` |
| **File** | `docs/img/08-pt009-sepsis-critical.png` |
| **Demo beat** | 1:55–2:05 |
| **Judge hook** | Zheng (maternal mortality), Mandel (zero code changes) |

**What must be visible:**
- Patient header: name/age (29F), procedure (C-section / postpartum), Day 1–3
- **CRITICAL** RiskBadge (red, ring emphasis, siren icon)
- `VitalsChart`: elevated HR (≥120), low SpO2 (≤93), rising Temp (≥38.5), high RR (≥22)
- "What triggered" card: references postpartum sepsis, lactate, WBC values
- Alert timeline: at least one CRITICAL entry

**Annotation overlay:**
- Arrow to CRITICAL badge: `"Same risk engine — zero code changes for maternal path"`
- Small stat overlay bottom-left: `"260K maternal deaths / year from sepsis"`

---

## Shot 09 — PT-009 SBAR (maternal sepsis context)

| Field | Value |
|---|---|
| **URL** | `http://localhost:3000/patients/PT-009/alerts/[use-seeded-alert-id]` |
| **File** | `docs/img/09-pt009-maternal-sbar.png` |
| **Demo beat** | 2:05–2:10 |
| **Judge hook** | Hickey (SBAR reuse), Zheng (maternal pathway), Mandel (reusability proof) |

**What must be visible:**
- Same SBAR layout as Shot 06, but content reflects **postpartum sepsis**:
  - **S**: 29F, POD1 C-section, triggered EMERGENCY sepsis
  - **A**: qSOFA = 2, CDC SRS 3/3 — sepsis CONFIRMED
  - **R**: Activate sepsis protocol, notify OB + ICU, hour-1 bundle
- EMERGENCY bar at top
- Both action buttons visible

**Annotation overlay:**
- Overlay badge top-right: `"0 lines of code changed vs postop path"`
- Callout on Assessment card: `"CDC SRS 3/3 — CONFIRMED"`

---

## Shot 10 — Marketplace, two tiles

| Field | Value |
|---|---|
| **URL** | `http://localhost:3000/marketplace` |
| **File** | `docs/img/10-marketplace.png` |
| **Demo beat** | 2:20–2:35 |
| **Judge hook** | Mandel (MCP registry, install model), Mathur + Zheng (both care paths visible) |

**What must be visible:**
- Page heading: "Vigil on the Prompt Opinion Marketplace"
- Two cards side by side:
  - Left: **Vigil MCP Server** — "4 Clinical Early-Warning Tools" — badges: `[MCP]` `[FHIR R4]` `[SHARP]` — "Install →" button (disabled)
  - Right: **Vigil Postop Sentinel** — "7-state A2A Agent, clinician-approved" — badges: `[A2A]` `[FHIR R4]` `[SHARP]` — "Subscribe →" button (disabled)
- No scrollbar visible; full page fits in one shot

**Annotation overlay:**
- Arrow to MCP tile: `"Post-op + maternal — same 4 tools"`
- Arrow to A2A tile: `"Prompt Opinion-native agent — 7-state machine"`
- Small label at bottom: `"Any SMART-on-FHIR hospital can install in minutes"`

---

## Shot 11 — Architecture splash (static render)

| Field | Value |
|---|---|
| **URL** | `docs/img/architecture.md` rendered via mermaid.live or VS Code |
| **File** | `docs/img/11-architecture.png` |
| **Demo beat** | 2:40 |
| **Judge hook** | General (system overview), Mandel (MCP + A2A protocol labels) |

**What must be visible:**
- The full system architecture flowchart from `docs/img/architecture.md`
- All three layers clearly labeled: Frontend (blue), Backend (amber), FHIR (green)
- SHARP header annotation visible on the PO → MCP edge
- LLM provider abstraction box visible (purple)
- Font readable at 1920×1080 — zoom the diagram until text is at least 14px apparent

**How to export:**
1. Open `docs/img/architecture.md` in VS Code with the Markdown Preview Mermaid plugin
2. Right-click the rendered diagram → "Export as PNG" (or use `mmdc` CLI: `mmdc -i architecture.mmd -o 11-architecture.png -w 1920 -H 1080`)
3. Alternatively, paste the mermaid block into `mermaid.live` and download SVG → convert to PNG

**Annotation overlay:**
- None — the diagram labels are self-documenting

---

## Shot 12 — Closing slide (composed in OBS / DaVinci)

| Field | Value |
|---|---|
| **URL** | N/A — compose in post-production |
| **File** | `docs/img/12-closing-slide.png` |
| **Demo beat** | 2:50–2:55 |
| **Judge hook** | General (GitHub, submission URL) |

**What must be visible:**
- Dark background (slate-950 `#020617`)
- Vigil logo centered (or `frontend/public/favicon.svg` scaled up)
- Tagline: `"One platform. Vigil."`
- GitHub URL (bottom)
- Team member names (bottom)
- No animation — this is a static hold frame

**Compose in DaVinci Resolve or Canva.** Export as PNG for the README and as a 5-second fade-in/fade-out video clip for the submission.

---

## Image optimization notes (for when PNGs are in)

Once you drop the PNG files into `docs/img/`, run:

```bash
# Compress without quality loss (install pngquant + optipng)
pngquant --quality=85-95 --strip docs/img/*.png
optipng -o2 docs/img/*.png
```

Target file sizes:
- Hero images (shots 01, 04, 06, 10): < 400 KB each
- Detail shots (02, 03, 05, 07, 08, 09): < 250 KB each
- Architecture / closing (11, 12): < 500 KB each

---

## Alt text drafts (copy into README `![alt](path)`)

| Shot | Alt text |
|---|---|
| 01 | `Vigil patient list showing four risk levels: CRITICAL, HIGH, MED, NORMAL — sorted by deterioration severity` |
| 02 | `PT-001 stable vitals chart — five flat trend lines across 8 hours, NORMAL risk badge, no alert generated` |
| 03 | `FHIR Observation resource tooltip showing live data from HAPI FHIR R4 store` |
| 04 | `PT-007 deteriorating vitals — heart rate trending up, MAP trending down over 6 hours, HIGH risk badge` |
| 05 | `Four MCP tool calls fired in sequence: screen_vital_thresholds, score_deterioration_risk, flag_sepsis_onset, generate_escalation_note` |
| 06 | `PT-007 SBAR alert card — Situation, Background, Assessment, Recommendation — Approve & send RRT button` |
| 07 | `Toast confirmation: Communication resource written to FHIR with audit trail` |
| 08 | `PT-009 postpartum patient — CRITICAL sepsis badge, elevated HR and temperature on vitals chart` |
| 09 | `PT-009 SBAR for maternal sepsis — identical structure to PT-007, zero code changes` |
| 10 | `Vigil marketplace tiles: MCP Server (4 tools) and Postop Sentinel (A2A agent) on Prompt Opinion` |
| 11 | `Vigil system architecture: Next.js dashboard, FastAPI proxy, MCP server, A2A agent, HAPI FHIR, LLM providers` |
| 12 | `Vigil closing slide — "One platform. Vigil." — logo and GitHub URL` |

---

## Caption drafts (for README section headers)

```markdown
*Vigil monitors four post-op patients in real time — risk-sorted, FHIR-backed, zero false alarms on stable cases.*

*Every number is a live FHIR Observation. Four MCP tools fire when the pattern shifts — not when a threshold is crossed.*

*The agent drafts the SBAR. The nurse sends it with one click. Closed loop — agentic action with a human in control.*

*PT-009: same four tools, same agent, zero code changes — maternal sepsis caught on the same pipeline.*

*Both care paths published as one Prompt Opinion entry. Any SMART-on-FHIR hospital, minutes to install.*
```

---

*Cross-reference: `docs/DEMO_SCRIPT.md` § 3 (beat-by-beat), `docs/FRONTEND_SPEC.md` § 3 (page wireframes)*
*Last updated: 2026-04-19*
