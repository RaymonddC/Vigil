---
name: vigil-design
description: Use this skill to generate well-branded interfaces and assets for Vigil, the clinical monitoring dashboard — either for production or throwaway prototypes, mocks, decks, and storyboards. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

Read the `README.md` file within this skill, and explore the other available files — `colors_and_type.css` (all tokens), `preview/` (swatches), `ui_kits/app/` (clinical dashboard), `ui_kits/marketing/` (landing page), `assets/` (logo, icons).

**Vigil is a clinical tool.** Reads as software that already belongs in a hospital — Linear × Epic × Notion, not Duolingo × Figma. The brand voice is direct, clinical, unglamorous. No exclamation marks, no emoji, no stock healthcare photography.

**The five non-negotiables:**
1. Human in the loop must be visible at the approve moment
2. Information-dense; the eye lands on the one patient that matters
3. Post-op and postpartum share the same pipeline and UI
4. Desktop-first (13"+) with 10" tablet portrait as secondary. No phone.
5. WCAG 2.2 AA, light + dark mode on every surface.

If creating visual artifacts (slides, mocks, throwaway prototypes), copy assets out of this skill folder and create static HTML files that link to them. Always pull design tokens from `colors_and_type.css` rather than inventing new colors — especially for the risk scale, which is the single most-repeated visual element.

If working on production code, read the rules in `README.md` to become an expert in designing with this brand. The `ui_kits/app/` components (`Atoms.jsx`, `ClinicalAtoms.jsx`, `Screens.jsx`, `Shell.jsx`) are reference recreations — reuse structure and visuals, not implementation.

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions, and act as an expert designer who outputs HTML artifacts or production code depending on the need.
