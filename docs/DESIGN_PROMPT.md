# Vigil — Claude Design prompt

Paste this verbatim as the first message of the Claude Design conversation.

---

Design the complete UI for a clinical dashboard called **Vigil**.

**What Vigil does.** An autonomous AI agent watches postoperative and postpartum hospital patients for early signs of deterioration, drafts a formal handoff note when it spots a pattern, and waits for a human clinician to approve before anything is sent. Clinicians stay the decision-maker; the AI is a tireless pair of eyes that never acts unilaterally.

**Who it's for.** A nurse or resident on a 12-hour post-op shift, watching 6–8 patients on a laptop at the ward station. Mid-career, time-starved, already drowning in EHR clicks, suspicious of anything that looks like consumer SaaS. They have 2 seconds per row to decide who needs attention. Mental posture: *"show me what I need and get out of my way."*

**The core user story.** Clinician opens the dashboard, sees a roster of her patients sorted by risk, notices one is red, clicks in, sees the vitals trend and an AI-drafted SBAR handoff note, reads it, clicks Approve. Total: under a minute. The approve action writes an audit-logged handoff to the electronic record attributed to her.

**Non-negotiable principles.**

1. Reads as software that already belongs in a hospital — not a startup demo. *Linear × Epic × Notion,* not *Duolingo × Figma.*
2. Information-dense, but the eye lands immediately on *the one patient that matters right now.*
3. Human-in-the-loop must be visible at the approve moment — every approved alert shows who approved it.
4. The same pipeline works for post-op AND postpartum patients. The UI should make the cross-ward reusability obvious — no different branding, no separate flows.
5. Desktop-first (13"+) as the canonical canvas — that's where the nurse-at-station workflow lives and where the demo video is recorded — but every screen must also render legibly on a 10" tablet in portrait (rounds use case). Phone not required. Fully keyboard accessible, WCAG 2.2 AA, light + dark mode on every surface. No stock healthcare photography, no patient photos.

**Invent whatever you want.** Palette, typography, spacing scale, iconography, layout shell, component anatomy — all yours. Surprise me.

**Design these eight routes:**

| Route | What it's for |
|---|---|
| `/` | Product landing page — pitches Vigil to first-time visitors. |
| `/patients` | Roster table of all patients on the ward, sorted by risk. The most-used screen. |
| `/patients/[id]` | Single patient detail — vitals chart, risk card with reasoning, comorbidities, recent alerts, the AI-drafted SBAR. The hero screen. |
| `/patients/[id]/alerts/[alertId]` | Alert detail — full SBAR, approve/dismiss actions, attribution to the clinician after approve. |
| `/alerts` | Global queue of all pending alerts across all patients, card list. |
| `/timeline` | Live feed of the AI agent's 7-state machine (IDLE → POLLING → SCREENING → RISK_SCORING → SEPSIS_CHECK → ESCALATING → AWAITING_REVIEW), polling every 2 seconds. "Tick Now" button to trigger an agent cycle manually. |
| `/marketplace` | Two listings on the Prompt Opinion Marketplace: the MCP tool library and the A2A agent. |
| `/settings` | System health — LLM provider, FHIR connectivity, agent heartbeat, review queue depth. |

**Cross-cutting elements that need design once and reused everywhere:**

- **Risk indicator** — five levels (normal / low / medium / high / critical). The single most-repeated visual element. Must be glanceable and accessible (color alone is not enough).
- **Clinician identity switcher** in the top nav — four hardcoded demo clinicians (Sarah Chen RN, Maya Lee Charge Nurse, Dr. Amit Patel Intensivist, Dr. Lindsay Park Rapid Response). Feels like a clinical user picker, not a social profile card.
- **SBAR card** — the AI-drafted handoff note, four sections (Situation / Background / Assessment / Recommendation). The central artifact of the product.
- **Approve action** — the decisive CTA. Success state must attribute the approval visibly ("approved by Dr. Patel").
- **Vitals chart** — 24 hours of multiple vital-sign series over time. Judges will stare at this for 30 seconds during the demo; make it beautiful and honest.
- **Agent state trace row** — each event in the timeline reads as progression, not log dump.
- **Empty / loading / error states** — treat as first-class, not afterthoughts.

**Demo beats the UI must support** (these are the narrative moments in a 3-minute video):

1. Roster view — 10 patients, top one visibly critical.
2. Stable patient — NORMAL, contrast moment.
3. Deteriorating patient — vitals chart shows the pattern, agent timeline shows 4 tool calls firing.
4. Approve moment — SBAR rendered, clinician approves, attributed toast.
5. Postpartum patient — same pipeline, EMERGENCY severity, no code change.
6. Marketplace listings — both published.
7. Closing.

**Deliverables.**

Light + dark mock of every route. Key interaction states (hover / focus / loading / empty / error / approved-success) where relevant. Named design tokens (palette, type scale, spacing, radii, shadows, motion durations) that I can translate directly into a Tailwind config. Component-anatomy diagrams for the cross-cutting elements above. A short storyboard of the 7 demo beats rendered in sequence so I can judge whether the narrative lands visually.

**Start here.** Give me your proposed **design language** first — palette, typography, tone, one or two adjective words for the overall feel — before any specific screen mocks. Once I sign off on the language, work screen by screen in this order: `/patients` → `/patients/[id]` → alert detail → `/timeline` → everything else. I'll iterate with you between screens.
