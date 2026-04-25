# Vigil App — UI Kit

Interactive, click-thru prototype of the clinical dashboard. Routes implemented:

- **`/patients`** — Roster (default view)
- **`/patients/:id`** — Patient detail (hero screen)
- **`/patients/:id/alerts/:alertId`** — Alert detail with SBAR + approve
- **`/alerts`** — Global queue
- **`/timeline`** — Agent state trace
- **`/settings`** — System health

Open `index.html` and use the top-nav tabs, or click any patient row.

**Components (`*.jsx`):**

- `Shell` — top nav, routing, clinician switcher, theme toggle
- `Roster` — risk-sorted patient table
- `PatientDetail` — vitals chart + SBAR + reasoning
- `AlertDetail` — full SBAR + approve action
- `Alerts` — global queue card list
- `Timeline` — live agent trace
- `Settings` — system health panel
- `RiskChip`, `SBARCard`, `VitalsChart`, `ApproveButton`, `AgentTrace` — shared atoms

Responsive behavior matches the spec: desktop-first, collapses to single-column below 900px for 10" tablet portrait.
