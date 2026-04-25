# Vigil redesign — visual QA report

_Generated 2026-04-25 by `visual-qa` teammate_

## Method

- **Browser:** Playwright + Chromium (headless), via `frontend/node_modules/.pnpm/playwright@1.59.1`.
- **Viewports:** desktop `1440×900`, tablet `768×1024`.
- **Theme toggle:** `page.addInitScript` sets `localStorage.setItem('vigil-theme', 'dark'|'light')` before navigation, picked up by the inline `themeBootstrap` in `app/layout.tsx` to apply `.dark` to `<html>` pre-paint.
- **What's running:** Next.js dev server only (`pnpm dev`, Turbopack, port 3000). FastAPI proxy on `:8000` and HAPI on `:8080` are **down** — Docker is not active in WSL on this host so `make demo` was not run. RSC fetches from `getPatients`, `getStatus`, etc. fail with `ECONNREFUSED 127.0.0.1:8000`.
- **Capture script:** `/tmp/qa-capture.js` (saved out-of-tree).
- **Screenshots:** 30 PNGs in `docs/design/qa-screenshots/` plus `_console-errors.json`.
- **Compare against:** `docs/design/project/ui_kits/app/Screens.jsx` and `app.css` (port targets); `docs/design/project/README.md` for content & voice rules.

> **Caveat — backend offline.** The patient-detail two-column layout, the SBAR/Approve climax, the alerts queue list, and the timeline event stream are all gated on backend response. Their offline fallback panels render correctly, but the design's intended interior (vitals chart, SBAR card, approve bar, attribution toast, agent trace) cannot be visually verified end-to-end here. Settings paradoxically renders its 2×2 grid because of a stale Next.js RSC cache from an earlier successful fetch (`revalidate: 10`) — the data shown is real and matches the design, but it is cached, not live.

---

## Route-by-route findings

### `/` — landing page

**Screenshots:** [`root-light.png`](qa-screenshots/root-light.png), [`root-dark.png`](qa-screenshots/root-dark.png), [`root-tablet-light.png`](qa-screenshots/root-tablet-light.png), [`root-tablet-dark.png`](qa-screenshots/root-tablet-dark.png).

> **The dev server is serving stale compiled output for `/`.** `frontend/app/page.tsx` (per filesystem read) contains the new "A second pair of eyes on every post-op bed" hero from `marketing-impl`. The live render at `localhost:3000/` shows an older "Postop + maternal deterioration sentinel" hero with stat cards (`4.2M / 260K / 30–60s / 8+`) and a "two paths, one FHIR-native core" section. `grep` confirms the live text is **only** in `.next/dev/server/chunks/ssr/...` — it is not in any source file. Either Turbopack failed to HMR, or the dev server was started before the marketing-impl edits and needs a restart. **Re-screenshot once `marketing-impl` signals done and the dev server has been bounced.**

- ✅ matches (against the *live* stale render): brand wordmark + shield in nav, top nav layout (48px tall, sticky, blurred), tab structure (Roster / Alerts / Timeline / Marketplace / Settings), clinician pill on the right with `RN` role badge in mono uppercase.
- ⚠️ deviations vs. the new design in `app/page.tsx`:
  - **HIGH** — Live render does not match source. The `mkt-pill`, `mkt-h1` "A second pair of eyes on *every post-op bed.*", `mkt-sub`, primary "Open the dashboard →" CTA, principles band, "The SBAR card is the artifact" anatomy section, standards strip, and footer are all defined in source but **not visible in any captured screenshot**. Cannot QA the new landing page until the dev server is rebuilt.
  - **MEDIUM** — Two CTAs visible on the stale render ("Open Dashboard ↗" and a "Watch agent run" / "GitHub" pair) use a different button vocabulary than the design's `mkt-cta--primary` + `mkt-cta--ghost` pair.
- The hero gradient on the stale render uses a blue-cyan gradient on the headline word ("deterioration sentinel"); the new design specifies `mkt-h1 em { color: var(--ink-700) }` (deep institutional indigo, no gradient). Whichever ships, **gradient on the headline contradicts the README rule "Gradients are forbidden except one: the risk-critical pulse"** — flag this if the `marketing-impl` final render keeps the gradient.

### `/patients` — roster

**Screenshots:** [`patients-light.png`](qa-screenshots/patients-light.png), [`patients-dark.png`](qa-screenshots/patients-dark.png), [`patients-tablet-light.png`](qa-screenshots/patients-tablet-light.png), [`patients-tablet-dark.png`](qa-screenshots/patients-tablet-dark.png).

**This is the strongest route in the redesign — it lands almost exactly on the design.**

- ✅ matches:
  - Sort order: critical/high first, low at bottom (HIGH B-010 → B-004, then LOW B-001 → B-003). `RISK_RANK` map in `patients-table.tsx` ordered `critical:0, high:1, …, normal:4`.
  - Roster table chrome: 1px `border-default`, 6px radius, header bar in `surface-0` with uppercase mono labels.
  - Risk stripe — 4px wide, 30px tall, 2px left margin, color from `var(--risk-{level})`. Visible orange stripe on HIGH rows, teal on LOW rows.
  - Risk chip — pill with paired typographic glyph (`◕ HIGH`, `◔ LOW`), rounded `--radius-full`, uppercase 11px tracked.
  - Monospace MRN, age, bed (`B-010`, `MRN-100010`, `29y`).
  - Ward labels uppercase mono (`POSTPARTUM`, `POSTOP`).
  - Page header — `Roster` 22px / mono sub-line with mono `Ward 4N · 10 patients · sorted by risk`.
  - Tablet collapse: drops `Latest alert`, `HR · MAP · SpO₂`, `Ward` columns; keeps `Bed | Patient | Risk`. Nav grows to 56px and clinician switcher collapses to icon-only avatar. Per design rule.
  - Dark mode — risk-bg desaturates correctly, body becomes `--gray-0: #0E1116`, no rendering issues.
- ⚠️ deviations:
  - **MEDIUM** — Patient row label reads `MRN MRN-100010 · 29y`. The literal word "MRN" appears twice (label + ID prefix). Source: `patients-table.tsx:104` writes `MRN {p.mrn}` but `p.mrn` from the backend is itself `"MRN-100010"`. Fix: drop one — either render `MRN-100010 · 29y` (mono only) or strip the prefix from the value.
  - **MEDIUM** — `Latest alert` cell wraps "Vitals trending out of range" onto two lines and pushes the `22:16` time onto its own line, breaking the inline `· {time}` pattern from the design (`Screens.jsx:31`). The 200px column width in `app.css:41` is too narrow for the `alertHeadline()` strings produced by `patients-table.tsx`. Either widen the column or shorten the headline (e.g. "Vitals out of range" / "Trend out of range") — the latter also matches the design's terser voice.
  - **LOW** — `HR · MAP · SpO₂` column shows `1 unread` for HIGH rows (because `PatientSummary` from the backend has no current vitals carried in the list endpoint) and `— · — · —` for LOW rows. Design intent (`Screens.jsx:32`) is the actual vital triplet — when the backend list payload doesn't carry vitals, the fallback "1 unread" reuses the column for unread-alert count, which is mildly confusing. Either rename the column or fetch vitals in the list endpoint.
  - **LOW** — Bottom-left a small black circle with white "N" overlays the page in every screenshot. It's the **Next.js dev-mode indicator**, not a design bug — but verify it does not appear in production builds before the demo.

### `/patients/{id}` — patient detail

**Screenshots:** [`patients-detail-light.png`](qa-screenshots/patients-detail-light.png), [`patients-detail-dark.png`](qa-screenshots/patients-detail-dark.png), [`patients-detail-tablet-light.png`](qa-screenshots/patients-detail-tablet-light.png), [`patients-detail-tablet-dark.png`](qa-screenshots/patients-detail-tablet-dark.png), and `…-approved-{light,dark}.png` (identical content because the approve button never appears with backend down).

- ✅ matches (header bar only — body cannot be QA'd offline):
  - Page header structure: `← Roster` ghost button, `B-001 · Patient PT-001` 22px title, `RiskChip NORMAL` (with `○` glyph) inline, mono `MRN — · WARD 4N · Day 0` subline.
  - The `Backend unavailable` fallback panel uses correct `.panel` chrome (1px border, 6px radius, mono meta on header).
- ⚠️ deviations / not-verifiable:
  - **HIGH (verifiability)** — `VitalsChart` (3 traces in red/ink/green per `vitals-chart.tsx:154–157`), `SBARCard` (`SBAR · DRAFT` tag, 4 sections), `ApproveBar` (Dismiss / Edit draft / Approve handoff →), and the post-approve `attr-toast` (`Approved by {Full name} · written to EHR`) all gate on `getPatient()` succeeding. With backend down, none of them render. Source code review confirms each one is wired correctly — but the actual visual fidelity (line-widths, gridline density, MAP color, legend chip, vital-tile alert states, approval toast green) **cannot be verified from these screenshots**. Action: bring up `make demo` and re-screenshot, or rely on a separate teammate to verify the live demo.
  - **MEDIUM** — `app/patients/[id]/page.tsx:109` uses a `<Link className="btn btn--ghost btn--sm">` for the Roster back button. Design (`Screens.jsx:48`) uses `<Button variant="ghost">…<Icon name="arrow-left"/>Roster</Button>`. Visually equivalent if `.btn--ghost.btn--sm` matches the design's ghost button height (26px) — confirmed by `app.css:127` (`.btn--sm { height: 26px; }`). ✅ on inspection.
  - **LOW** — On tablet (768×1024), the `Backend unavailable` panel renders correctly inside the page gutter and the `pdetail` two-column would collapse to 1 column at this width per `app.css:573`. Cannot verify the collapse against real two-column content.

### `/patients/{id}` after Approve

**Screenshots:** [`patients-detail-approved-light.png`](qa-screenshots/patients-detail-approved-light.png), [`patients-detail-approved-dark.png`](qa-screenshots/patients-detail-approved-dark.png).

- ⚠️ **HIGH (verifiability)** — Approve button does not exist with backend down (no SBAR + ApproveBar render path), so the capture script's `button:has-text("Approve")` selector found nothing and these screenshots are identical to the un-approved offline state. The green `attr-toast` reading `Approved by Sarah Chen, RN · written to EHR · {time}` (per `approve-bar.tsx:104` + `app.css:668`) **cannot be verified visually here**. Source review only:
  - `app.css:668` `.attr-toast` uses `var(--success-bg)` background and a 30%-of-success border — green palette per design ✅.
  - The avatar circle is 22×22, success-colored, white text — matches `Screens.jsx`-equivalent in design CSS ✅.
  - Time pinned right via `margin-left: auto` ✅.
  - The string `Approved by Dr. Amit Patel · 14:07 · written to EHR` from the design has been split: `app/page.tsx:111` (marketing preview) places `· 14:07` AFTER `written to EHR`, while `approve-bar.tsx:104` (real bar) puts only `Approved by {Full name} · written to EHR` in the text and the time as a separate right-aligned span. **Per the README's "approve moment copy" critical-string rule, both forms keep the audit-attribution tone, but the order of `· {time}` differs.** Decide whether the canonical string is `Approved by … · {time} · written to EHR` (one block) or `Approved by … · written to EHR  {time}` (right-floated). The marketing preview and the real toast should agree.

### `/alerts` — pending alerts queue

**Screenshots:** [`alerts-light.png`](qa-screenshots/alerts-light.png), [`alerts-dark.png`](qa-screenshots/alerts-dark.png), [`alerts-tablet-light.png`](qa-screenshots/alerts-tablet-light.png), [`alerts-tablet-dark.png`](qa-screenshots/alerts-tablet-dark.png).

- ✅ matches (header only — empty fallback shows because backend down):
  - Header: `Pending alerts` title + mono sub-line `0 awaiting review · across 2 wards`. Note the "0" because `fetchAlerts()` resolves to empty after the catch.
  - The `Backend unreachable` panel uses correct `.panel` chrome and includes a working `Retry` ghost button.
  - Console errors: 4× `Failed to load resource: the server responded with a status of 502 (Bad Gateway)` per page load, expected because the Next.js `[...path]` API proxy returns 502 when FastAPI is down.
- ⚠️ deviations / not-verifiable:
  - **HIGH (verifiability)** — Cannot verify alert-card rendering (vertical stack, `auto 1fr auto` grid, RiskChip + name/msg + meta on right, hover `shadow-xs`) — backend down means zero alerts render.
  - **MEDIUM** — `app/alerts/page.tsx:142–159` puts three buttons (`Review`, `Dismiss`, `Approve handoff →`) **inside the alert-card's middle column**. Design (`Screens.jsx:118–129`) uses a click-the-row pattern: the entire card opens the alert detail, no inline buttons. Inline buttons make each card visually heavier than the design's terse "flagged 14:02 → review" pattern, and add a hit-target conflict (clicking a card vs. clicking a button). Recommend either:
    - Move the buttons out of the card (into the detail page), keeping cards as click-to-review rows, OR
    - Keep buttons but explicitly document this as a deliberate deviation (the design page in `Screens.jsx` doesn't show queue actions; the implementation may need them).
  - **LOW** — The header sub-line copy uses `0 awaiting review · across 2 wards` (mono). Design (`Screens.jsx:115`) uses `{n} awaiting review · across 2 wards`. ✅ matches when `n>0`.

### `/timeline` — agent timeline

**Screenshots:** [`timeline-light.png`](qa-screenshots/timeline-light.png), [`timeline-dark.png`](qa-screenshots/timeline-dark.png), [`timeline-tablet-light.png`](qa-screenshots/timeline-tablet-light.png), [`timeline-tablet-dark.png`](qa-screenshots/timeline-tablet-dark.png).

- ✅ matches:
  - Header with `Agent timeline` title + mono `7-state machine · polling every 2 s`.
  - Right-aligned primary `Tick now` button (ink-700 / `--ink-800` on hover) — matches design (`Screens.jsx:159`).
  - Trace shell — 1px border, 6px radius, mono `OFFLINE` (or `LIVE`) label with leading dot, mono "next poll in" line. The dot pulses via `rpulse` keyframes (verifiable as a green-leaning success dot in light mode).
- ⚠️ deviations / not-verifiable:
  - **HIGH (verifiability)** — Cannot verify the per-event row rendering (80px mono timestamp / 8px dot / state label + detail / 80px ms duration), the `evt.active` ink dot pulse, the `evt.done` success dot. Backend down → empty trace.
  - **LOW** — The `LIVE` dot shown by the design is `var(--success)` and pulsing via `motion-pulse: 1200ms`. With backend offline the implementation flips it to `OFFLINE` (`timeline/page.tsx:174`) but keeps the pulse on the dot — visually that's fine because it's still success-colored from `app.css:822`, but semantically a *pulsing* `OFFLINE` state is a small contradiction. Consider freezing the dot when offline (remove animation in offline branch).

### `/marketplace` — Prompt Opinion listings

**Screenshots:** [`marketplace-light.png`](qa-screenshots/marketplace-light.png), [`marketplace-dark.png`](qa-screenshots/marketplace-dark.png), [`marketplace-tablet-light.png`](qa-screenshots/marketplace-tablet-light.png), [`marketplace-tablet-dark.png`](qa-screenshots/marketplace-tablet-dark.png).

- ✅ matches:
  - Header `Prompt Opinion Marketplace` 22px + mono sub-line `2 listings · published · verified`.
  - Two listing cards (`vigil-clinical-tools`, `vigil-ward-agent`), each as a flex row: `M`/`A` glyph badge (40×40 ink-700 square, mono label) + name/desc + meta (installs + ★ rating).
  - Star rating uses `var(--warning)` (amber); installs in mono small text. Reasonable.
- ⚠️ deviations:
  - **MEDIUM** — Marketplace is **not in `Screens.jsx`** at all — the implementation reuses the `.alert-card` class for listings. This is fine semantically but means there is no design ground-truth to compare against. The current rendering looks consistent with the system (square radii, mono meta, ink-square badges) but consider whether a custom `.mkt-listing` class is warranted given how prominent this route is for the hackathon submission.
  - **LOW** — The "M" / "A" mono initials inside 40×40 ink squares feel a touch heavy next to the design's quieter surface palette. Consider replacing them with Lucide `package`/`bot` icons (1.75 stroke) to match the system's iconography rule.

### `/settings` — system health

**Screenshots:** [`settings-light.png`](qa-screenshots/settings-light.png), [`settings-dark.png`](qa-screenshots/settings-dark.png), [`settings-tablet-light.png`](qa-screenshots/settings-tablet-light.png), [`settings-tablet-dark.png`](qa-screenshots/settings-tablet-dark.png).

This route renders fully because Next's RSC cache (`revalidate: 10` in `lib/api.ts`) returned data from an earlier successful fetch.

- ✅ matches (very close to design):
  - 2×2 grid (`settings-grid`) on desktop, single column on tablet ✅.
  - Four panels: `LLM provider`, `FHIR gateway`, `Agent heartbeat`, `Prompt Opinion SHARP`. Note the design's fourth panel is `Review queue` but the implementation substituted `Prompt Opinion SHARP` — a justified change because SHARP is more relevant to the submission's compliance story than a review-queue counter.
  - Status pills: `OPERATIONAL`, `HEARTBEAT`, `RUNTIME` — each a 8px round dot + uppercase mono label. `HEARTBEAT` is a slight rename from the design's `OPERATIONAL` that's cute and fine; `RUNTIME` is new and reads well.
  - Sysrow layout: `key` left / mono `value` right, 1px subtle bottom border between rows ✅.
  - Header sub-line: `all green · last check 15:17:56` mono ✅.
- ⚠️ deviations:
  - **LOW** — The design specifies `WATCH` as a `--warning` (amber) status pill (`Screens.jsx:222`); the implementation has a `status--warn` class for that case but no panel currently renders `WATCH` — only `OPERATIONAL` / `HEARTBEAT` / `RUNTIME` are shown. Consider keeping a `WATCH` example for the demo (e.g. when the agent's `Last check` is older than `2× POLL_INTERVAL_SEC`) so the amber pill is visible.

---

## Cross-cutting findings

### Dark mode

- ✅ **Parity is good.** Risk colors desaturate as designed, panels remain legible, ink-700 lightens to `var(--ink-500)` in nav brand and active CTAs.
- ⚠️ **LOW** — In dark mode the active nav tab uses `--surface-3` (`#242B36`) which is only slightly different from `--surface-2` (`#1A2029`). On a typical laptop screen the active tab is **barely distinguishable** from the inactive ones (e.g. compare `Roster` highlight vs the rest in `patients-dark.png`). Consider darkening the active tab or adding a 1px bottom border / 1px ink-700 underline to make the active state more glanceable.
- ⚠️ **LOW** — On `settings-dark.png` the status dots (`HEARTBEAT`, `OPERATIONAL`) show fine, but the green `var(--success)` in dark mode is `#4ADE80` — quite saturated next to the rest of the desaturated palette. Slight tone-down toward `#3FA974` would feel more consistent with the design's "saturation is restrained" rule.

### Tablet (768×1024)

- ✅ Roster columns collapse correctly (Bed/Patient/Risk only).
- ✅ Settings grid collapses to single column.
- ✅ Nav grows from 48px → 56px and clinician switcher collapses to icon-only.
- ✅ Tablet capture for `/patients` has rows growing from 48px → 56px (per design rule).
- ⚠️ **LOW** — On tablet, the `clipill` becomes a bare 22×22 dot (`app.css:957–959` hides `.name` and `.role`). It works but loses the "RN" role hint. Consider showing the avatar + role pill (drop only the name) so the clinician's role still reads at a glance — this matters in a clinical setting more than the name does.

### Focus rings

- ✅ The `:where(button, a, …):focus-visible` rule in `globals.css:349–353` applies `outline: 2px solid var(--border-focus)` (= `--ink-700`) at 2px offset. Consistent with the design (README: *"2px `accent-ink` ring at 2px offset, never a blue browser ring"*).
- ⚠️ **LOW** — Could not capture focus state in screenshots (Playwright was clicking by selector, not tabbing). Recommend a manual keyboard-walk through `/patients` and `/patients/{id}` to confirm the ink ring is visible on roster rows, the Roster back link, the Approve button, and the chips.

### Voice copy deviations

(Per `docs/design/project/README.md` content rules.)

- ✅ Severity casing — `HIGH`, `LOW`, `OPERATIONAL`, `HEARTBEAT`, `RUNTIME` are all upper-cased in the right places (status chips and agent states).
- ✅ "Vigil is watching" empty-state copy is intact in patient-detail "No active alert" panel.
- ⚠️ **LOW** — `roster__alert` headlines like `Vitals trending out of range` are slightly more verbose than the design's terse voice. Consider `Vitals out of range` or `HR · MAP off-trend`.
- ⚠️ **LOW** — `app/alerts/page.tsx:38` shows `"Cannot reach backend — start FastAPI on :8000"` to clinicians. Per the voice rules ("we write like the charge nurse's shift huddle notes"), this is a developer-y string. Production should show `"Couldn't reach the FHIR gateway. Retrying in 10 s."` (the README's documented error string) and only show the developer hint in `LLM_PROVIDER=stub` / dev mode.

### Console errors

- 4× `502 Bad Gateway` per visit on `/alerts` and `/timeline` — both are client-side polling fetches (`fetchAlerts` and `fetchEvents`) that the catch-all `app/api/[...path]/route.ts` proxies to FastAPI, which is down. Expected with backend offline. **No JS exceptions, no React hydration warnings, no Next.js dev errors.**

### Stale-bundle issue at `/`

The dev server is rendering an older landing page than the source contains (see `/` section above). This appears to be a Turbopack HMR miss. **A dev-server restart is required before the new marketing page can be QA'd.** Recommend the team-lead asks `marketing-impl` to bounce the dev server when their work is done, then re-run this QA on `/` only.

---

## Recommended next actions (ordered by severity)

1. **HIGH** — Bounce the dev server (or `pnpm dev` clean) so `/` renders the new `app/page.tsx`. The "A second pair of eyes" hero is currently invisible; re-screenshot after restart.
2. **HIGH** — Bring up `make demo` (or have a teammate verify locally) so the patient-detail two-column layout, vitals chart, SBAR draft card, approve bar, and post-approve `attr-toast` can be visually QA'd. These are the demo's emotional moments and the offline fallback panel cannot validate them.
3. **MEDIUM** — Fix the doubled `MRN MRN-100010` label in `frontend/components/patients-table.tsx:104`. Drop one.
4. **MEDIUM** — Either widen the `Latest alert` column in `frontend/app/globals.css:462` and `:477` (currently `200px`) or shorten `alertHeadline()` strings in `patients-table.tsx:42–49` so the time stays inline.
5. **MEDIUM** — Decide whether `/alerts` queue cards should have inline buttons (Review/Dismiss/Approve) — design says click-the-row, implementation has buttons. Document the decision either way and align the patient-detail and alert-detail flows accordingly.
6. **MEDIUM** — Reconcile the approve-toast string between marketing preview (`app/page.tsx:111`) and the live `ApproveBar` (`approve-bar.tsx:104`) — both should produce the README's canonical `Approved by {full name} · {time} · written to EHR`.
7. **LOW** — Replace the `M`/`A` mono-letter badges on `/marketplace` with Lucide icons.
8. **LOW** — Tighten dark-mode active-tab contrast in the top nav (active tab is barely distinguishable from inactive).
9. **LOW** — Trade the developer-y `:8000` string in `/alerts` error for the README's voice (`Couldn't reach the FHIR gateway. Retrying in 10 s.`).
10. **LOW** — Stop the `LIVE` dot pulse when timeline state is `OFFLINE`.
11. **LOW** — Manually keyboard-walk the app to confirm focus rings render in the ink color on every interactive element (Playwright didn't capture this).
12. **LOW** — On tablet, surface the clinician role pill (drop only the name, keep `RN`/`MD` glyph) — useful in clinical context.
13. **NOTE** — Confirm the Next.js dev-mode "N" indicator is not in the production build before recording the demo video.
