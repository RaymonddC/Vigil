# Vigil Design System

**Vigil** is a clinical monitoring dashboard. An autonomous AI agent watches postoperative and postpartum hospital patients for early signs of deterioration, drafts a formal SBAR handoff note when it spots a pattern, and waits for a human clinician to approve before anything is sent. Clinicians stay the decision-maker; the AI is a tireless pair of eyes that never acts unilaterally.

**Audience.** Nurses and residents on 12-hour post-op or postpartum shifts, watching 6–8 patients on a laptop at the ward station. Mid-career, time-starved, suspicious of anything that looks like consumer SaaS. Mental posture: *"show me what I need and get out of my way."*

**Reference comp.** *Linear × Epic × Notion.* Not *Duolingo × Figma.*

---

## Sources

This design system was generated from a written product brief only. **No codebase, Figma file, existing logo, or sample screens were provided.** Every visual decision — palette, typography, iconography, layout shell, component anatomy — was invented to fit the brief's stated principles:

1. Reads as software that already belongs in a hospital.
2. Information-dense; the eye lands on *the one patient that matters right now.*
3. Human-in-the-loop is visible at the approve moment.
4. Same pipeline works for post-op AND postpartum — one visual language.
5. Desktop-first (13"+) for the nurse-at-station workflow, with legible rendering on a 10" tablet in portrait for ward rounds. No phone. WCAG 2.2 AA, light + dark mode.

If/when real product artifacts arrive (Figma, codebase, existing brand guidelines), this system should be reconciled against them — the current version is a considered first pass, not a recovery of an existing brand.

---

## Design Language (the short version)

> **Vigilant, clinical, quietly serious.** An instrument panel, not a product.

- **Neutrals** do 80% of the work. A warm-cool gray spine (hint of blue) carries structure.
- **Ink** — a deep institutional indigo — is the only brand accent. Used sparingly.
- **Risk scale** is the workhorse palette: five steps from normal → critical, each paired with a glyph so color is never load-bearing alone.
- **Typography** is Geist (UI) + JetBrains Mono (numerals). Every vital, timestamp, ID, and dose is tabular.
- **Motion** is functional. 120–180ms ease-out. No bounces, no springs, no shimmer. A pulse means "live."
- **Shape** is square-ish. 4px and 6px radii only. 1px borders carry structure; shadows are rare.

---

## Index

| Path | What's in it |
|---|---|
| `README.md` | This file. Design language, content fundamentals, visual foundations, iconography. |
| `colors_and_type.css` | All design tokens as CSS vars — palette, type scale, spacing, radii, shadows, motion. Both light and dark. |
| `SKILL.md` | Front-matter entry point when this system is used as a Claude Code Agent Skill. |
| `fonts/` | Geist and JetBrains Mono web font files. |
| `assets/` | Logo, wordmark, icon set (Lucide CDN), background textures. |
| `preview/` | Swatches and specimens that populate the Design System tab. |
| `ui_kits/app/` | The clinical dashboard UI kit — roster, patient detail, alert detail, timeline, settings. |
| `ui_kits/marketing/` | The public `/` landing page UI kit. |

---

## Content Fundamentals

**Voice.** Direct, clinical, unglamorous. We write like the charge nurse's shift huddle notes, not like a startup blog. Every sentence earns its place. No exclamation marks ever. No em-dash flourishes. No emoji in product UI. Periods on full sentences in body copy; no periods on labels, table cells, or button text.

**Tense and person.** Product surfaces use *third person* about the patient (*"Patient is tachycardic"*) and *second person* to the clinician (*"Review the draft before approving"*). The AI is referred to as "the agent" or "Vigil" — never "I," never anthropomorphized. Avoid "we."

**Casing.**
- Sentence case everywhere. Not title case.
- `UPPER` only for: status chips (`NORMAL`, `CRITICAL`), agent states (`AWAITING_REVIEW`), and keyboard shortcuts (`⌘K`).
- Numeric units are always lowercase and space-separated from the number: `98 bpm`, `37.2 °C`, `2 mg`.

**Density and brevity.** Labels are 1–3 words. Table columns are nouns (`MRN`, `Ward`, `Risk`). Buttons are verbs (`Approve`, `Dismiss`, `Tick now`). No "Click here." No "Please." No "Oops."

**Severity words, ranked.** *Normal → Low concern → Watch → Elevated → Critical.* We never say "emergency" in-product except for postpartum-specific `EMERGENCY` severity (the brief's term). We never say "alert!" — just `Alert`.

**The AI.** Speak about it in plain language. *"Vigil flagged this patient at 14:02 based on a 3-hour MAP trend and a rising lactate."* Not *"Our AI has identified..."* The clinician is the expert; Vigil is an observation tool.

**Approve moment copy (the critical string).**
> *Approved by Dr. Amit Patel · 14:07 · written to EHR*

Never "Submitted" or "Sent!" The audit attribution is the message.

**Examples — landing page.**

- Hero: *"A second pair of eyes on every post-op bed."*
- Sub: *"Vigil reads vitals, drafts the handoff, and waits for you to approve."*
- Feature: *"Never acts alone. Every alert is approved by a clinician before it touches the record."*

**Examples — product toasts.**

- Success: *Handoff written to EHR for Bed 12.*
- Pending: *Vigil is drafting. Usually ready in 4–6 seconds.*
- Empty: *No pending alerts. Vigil is watching 8 patients.*
- Error: *Couldn't reach the FHIR gateway. Retrying in 10 s.*

---

## Visual Foundations

### Palette

**Neutrals — the spine.** A 12-step warm-cool gray with a hint of blue. Paper (`#FAFBFC`) to ink (`#0B0F14`). Dark mode uses a slightly green-leaning near-black (`#0E1116`) rather than pure black — pure black vibrates at ward-station brightness.

**Brand ink.** `#2B3A67` — a deep institutional indigo. Used for primary actions, the logo mark, and active nav state. Chosen because it reads "chart" and "record," not "consumer app."

**Risk scale — the workhorse.** Five levels, each with a paired glyph. Saturation is deliberately restrained; critical is the only color that approaches true saturation, so it earns the eye's attention.

| Level | Light | Dark | Glyph |
|---|---|---|---|
| `NORMAL` | slate 500 | slate 400 | `○` hollow dot |
| `LOW` | teal 600 | teal 400 | `◔` quarter |
| `MEDIUM` | amber 600 | amber 400 | `◐` half |
| `HIGH` | orange 700 | orange 400 | `◕` three-quarter |
| `CRITICAL` | red 700 | red 500 | `●` filled + pulse |

**Semantic.** Success = muted green (`#2F7D5C`), not bright. Info = the brand ink. Warning = amber (reused from risk). Danger = red (reused from risk).

### Typography

| Role | Face | Notes |
|---|---|---|
| UI body | **Geist** 400/500/600 | Google Fonts substitution for Söhne/Inter-tight feel. Tabular numerals on by default. |
| Numeric (vitals, IDs, time) | **JetBrains Mono** 400/500 | `font-variant-numeric: tabular-nums` mandatory. |
| Marketing display | Geist 600–700 | No separate display face. |

**Type scale (rem, 16px root).** 12 / 13 / 14 / 16 / 18 / 22 / 28 / 36 / 48. Body default is 14px — this is a dense application. Line-heights 1.35 (display), 1.5 (body), 1.25 (table rows).

> ⚠️ **Font substitution notice.** The brief didn't ship with font files, so I've used **Geist** (Google Fonts) as the UI face and **JetBrains Mono** for numerics. If you have a licensed face in mind (Söhne, Inter, ABC Diatype, etc.), drop the `.woff2` into `fonts/` and swap the `@font-face` block in `colors_and_type.css` — the rest of the system is face-agnostic.

### Spacing

A 4-point grid. Tokens `space-0` through `space-12` = `0, 2, 4, 6, 8, 12, 16, 20, 24, 32, 40, 56, 80`. Table row padding is `8 12` (vertical horizontal). Card padding is `16 20`. Page gutter is `24`.

### Radii

Only three: `radius-sm = 4px` (inputs, chips), `radius-md = 6px` (cards, buttons), `radius-lg = 10px` (modals). **No pills** except status chips, which use `radius-full` intentionally to signal "status, not action."

### Borders and dividers

Structure is carried by **1px borders**, not shadows. Two border weights: `border-subtle` (near-invisible for dense tables) and `border-default` (visible but quiet). Dividers in dense tables use `border-subtle` on bottom only.

### Shadows

Shadows are rare and quiet.
- `shadow-xs`: `0 1px 2px rgba(11,15,20,.04)` — cards on hover only
- `shadow-sm`: `0 2px 8px rgba(11,15,20,.06)` — popovers
- `shadow-md`: `0 12px 32px rgba(11,15,20,.10)` — modals
- No `shadow-lg`. If you need it, you need a modal.

### Backgrounds, imagery, textures

**No stock healthcare photography. No patient photos. No illustrations of people.** The brief is explicit about this and I agree — it's the right call.

Backgrounds are flat neutrals. The one allowed texture is a **1px dotted grid** (`assets/texture-grid.svg`) used behind hero marketing sections and on the empty states for charts. Never behind data.

**Gradients are forbidden** except one: the risk-critical pulse state uses a radial `red-700 → red-800` gradient on the dot glyph, 1200ms ease-in-out.

### Motion

| Token | Value | Use |
|---|---|---|
| `motion-instant` | 80ms linear | hover color changes |
| `motion-fast` | 120ms ease-out | button press, chip flip |
| `motion-base` | 180ms ease-out | panel slide-in, toast enter |
| `motion-slow` | 320ms ease-out | route change, modal |
| `motion-pulse` | 1200ms ease-in-out infinite | critical risk indicator only |

Easing is always `cubic-bezier(0.2, 0, 0, 1)` (ease-out) or `linear`. **No bounces, no springs.** A bounce in a hospital tool reads as unserious.

### Hover, focus, press

- **Hover:** background shifts from `surface-1` to `surface-2`; no scale, no shadow growth.
- **Focus:** 2px `accent-ink` ring at 2px offset, never a blue browser ring. Keyboard-only (`:focus-visible`).
- **Press:** background goes one step darker, no scale-down. A scale-down on a `Dismiss alert` button would feel toy-like.
- **Disabled:** 40% opacity + `cursor: not-allowed`, no color shift.

### Transparency and blur

Used sparingly. The top nav uses `backdrop-filter: saturate(180%) blur(10px)` only when content scrolls under it. Modals have a 40%-opacity neutral scrim; no blur — clinicians need to see what's behind the modal to orient.

### Cards

- 1px `border-default`, `radius-md` (6px), `surface-1` background.
- **No shadow at rest.** `shadow-xs` on hover if the card is clickable.
- Internal padding `16 20`.
- A card with a colored left border means "risk-coded row" — reserved for patient rows and alert cards. Never decorative.

### Layout rules

- **Top nav is 48px tall, sticky.** Contains logo, route tabs, clinician switcher (right-aligned).
- **Content max-width is 1440px** but tables go edge-to-edge with 24px gutters.
- Two-column patient detail: 720px vitals chart column, 400px SBAR column, 24px gap.
- Page titles are 22px, not 28px — this is not a CMS.

### Responsive rules (desktop + 10" tablet portrait)

Canonical canvas is desktop (1280–1920px wide, 13"+ laptop at the ward station). A 10" tablet in portrait (~768×1024 CSS px) is the secondary target for rounds — the clinician walking the ward with the device in hand. Phone is **not supported**.

- **Breakpoint:** `--bp-tablet: 900px`. Below that, switch to the tablet layout.
- **Nav:** 48px tall desktop → 56px tall tablet (bigger tap targets). Clinician switcher collapses to avatar-only.
- **Patient detail:** two-column (720 + 400) desktop → stacked single column on tablet. Vitals chart always first, SBAR below, side-nav collapses to an accordion of sections.
- **Roster table:** drop the `Ward`, `Admitted`, and `Last vitals` columns on tablet; keep `Risk`, `Bed`, `Patient`, `Alert`. Risk chip moves to the leading cell.
- **Hit targets:** on tablet, every interactive element is a minimum 44×44px (WCAG 2.2 AA target size). Buttons grow from 32px → 40px height; icon buttons get 12px surrounding padding.
- **Type:** body stays 14px — dense is the point — but row-heights grow from 40px → 48px for touch. Headings unchanged.
- **Gestures:** still keyboard-first. Tablet adds tap-to-open on rows; no swipe, no pinch. Don't invent gestures clinicians won't discover.

### Dark mode

Not an inversion — a rebalance. Paper becomes `#0E1116`, ink-text becomes `#E6E9EE`, brand ink lightens to `#6B7FB8`. Risk colors all desaturate slightly and lighten (a dark-mode red-700 would look brown). See `colors_and_type.css` for the full mapping.

---

## Iconography

**System:** [Lucide](https://lucide.dev) via CDN. Reason: stroke-based (not filled), 24px native grid, MIT license, huge coverage including clinical-adjacent glyphs (`activity`, `heart-pulse`, `stethoscope`, `shield-check`, `user-round`). Visual weight matches Geist.

**Substitution flag.** Lucide is a substitution, not a brand asset — if you have a custom icon set, drop SVGs into `assets/icons/` and swap the `<i data-lucide>` references.

**Rules of use.**
- Default size **16px** in UI (beside labels), **20px** in empty states, **14px** inside chips.
- Stroke width **1.75** globally. Not 2 — feels heavy next to Geist.
- Color always inherits `currentColor`. Never multi-color.
- Never decorative. Every icon is labeled or tooltipped.
- **No emoji anywhere in the product.** The marketing page may use a single Unicode arrow (→) in CTAs, nothing else.

**Risk glyphs.** Hand-defined, not from Lucide — they're typographic characters: `○ ◔ ◐ ◕ ●`. This keeps them glanceable at 10px and screen-reader-labeled consistently.

**Logo.** A 1px-stroke open eye inside a squared-off shield outline. Wordmark is `Vigil` set in Geist 600 with tracking `-0.02em`. See `assets/logo.svg` and `assets/wordmark.svg`.

---

*Continue to `colors_and_type.css` for the full token set, or jump to `ui_kits/app/index.html` for a live prototype.*
