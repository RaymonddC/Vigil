# JUDGE_HOOKS.md — Vigil (Agents Assemble hackathon)

Planning doc for judge-facing signal. Goal: every one of the 5 named judges sees at least 3 specific hooks by the end of the Devpost submission + demo video. Written 2026-04-15 for a 2026-05-11 deadline.

Ground truth of what we actually built: an MCP server exposing 4 clinical tools (`screen_vital_thresholds`, `score_deterioration_risk`, `flag_sepsis_onset`, `generate_escalation_note` — enforcing MEWT, qSOFA, and CDC Adult Sepsis Event applied to postpartum, with SBAR generation) + a Python A2A agent acting as a postoperative deterioration sentinel. The same 4 tools also fire on a postpartum patient as a cameo (single ward swap, no code change).

---

## 1. Per-judge profiles

### 1.1 Piyush Mathur, MD — Cleveland Clinic
Staff anesthesiologist and Innovation Lead, Department of Anesthesiology, Cleveland Clinic. Founder of BrainX (an AI-in-healthcare R&D company). ML/DL trained. ~1,000+ Scholar citations. ([Cleveland Clinic bio](https://my.clevelandclinic.org/staff/7622-piyush-mathur), [BrainX](https://www.brainxai.com/who-we-are), [Scholar](https://scholar.google.com/citations?user=VMphBlAAAAAJ))

**Research summary.** Mathur's work is squarely on the AI-for-perioperative / AI-for-critical-care axis. He co-authored "Artificial intelligence for the prediction of postoperative complications in the critically ill" (Crit Care Sci 2025) with Vanessa Moll and Ashish Khanna ([PMC12266812](https://pmc.ncbi.nlm.nih.gov/articles/PMC12266812/)), noting that postoperative mortality is the third greatest contributor to global deaths, per Nepogodiev 2019 *Lancet Global Health* (~4.2M deaths within 30 days of surgery per year), and that most current AI postop models show only marginal lift over traditional scores + clinician judgment. He is also lead author of "Artificial intelligence for perioperative medicine: perioperative intelligence" (2023), "Artificial intelligence in critical care" (2019), and the "AI in Healthcare: Year in Review" series (2021, 2024) — the latter sweeps >4,000 papers/year. He co-authored "Bias in artificial intelligence algorithms and recommendations for mitigation" (2023, 600+ citations) and the DECIDE-AI reporting guideline (2022, 800+ citations) ([Scholar](https://scholar.google.com/citations?user=VMphBlAAAAAJ)).

**Priorities.**
- Prospective, actionable clinical AI — he notes only 18/494 ICU AI studies were prospective.
- Postoperative complication prediction, specifically myocardial injury, sepsis, AKI.
- Integration of EHR + intraoperative waveform data.
- DECIDE-AI-style rigor in reporting: what did you evaluate, on whom, with what bias check.
- Bridging traditional risk scores (MEWS, qSOFA, APACHE) to ML, not replacing them.

**Our 3 best hooks.**
1. **"Marginal-lift problem, solved with orchestration, not a new model"** — open the README with the Crit Care Sci 2025 statistic ("4.2M postop deaths / year; current AI shows marginal lift over traditional scores") and reframe Vigil as *composing* MEWT + qSOFA deterministically rather than training yet another black box. Lands on Mathur's own thesis.
2. **Demo minute 0:30 — postop cardiac surgery patient.** Open the demo on a postop CABG patient, not a generic ICU patient. Mathur is an anesthesiologist; opening on the OR-to-ICU handoff is home turf.
3. **DECIDE-AI-flavored eval card in the repo.** A short `EVALUATION.md` with a DECIDE-AI-style table (intended use, target population, data source, bias considerations, failure modes). Costs us 30 minutes, signals to Mathur we've read him.

**Rejection triggers.**
- "Our model beats clinicians" claims without prospective data — he will roll his eyes.
- Replacing qSOFA/MEWS entirely instead of wrapping them.
- Unbounded LLM doing the scoring (he cares about auditability).
- Ignoring bias — don't demo only on one synthetic cohort.

---

### 1.2 Josh Mandel, MD — Microsoft / SMART Health IT
Chief Architect, Microsoft Healthcare; Chief Architect, SMART Health IT; Lecturer, Harvard DBMI. Creator of SMART on FHIR and CDS Hooks. ([MSR profile](https://www.microsoft.com/en-us/research/people/jmandel/), [@JoshCMandel](https://x.com/JoshCMandel), [GitHub jmandel](https://github.com/jmandel))

**Research summary.** Mandel led the SMART on FHIR specification — the "write once, run unmodified" app platform that every US-certified EHR must now support under the Patient Access API rule ([JAMIA 2016](https://academic.oup.com/jamia/article/23/5/899/2379865)). He launched the CDS Hooks project, served on the national Health IT Standards Committee, and has been a primary voice translating between HL7 FHIR working groups and practicing developers. In a Cerner podcast (Ep 50, 2017) and repeated talks ([HL7 FHIR Roundtable Duke, 2017](https://www.hl7.org/events/fhir/roundtable/2017/03/pdfs/F-34_Josh-Mandel.pdf)) he has emphasized that the original SMART pitch failed until Harvard embraced existing standards — vendors told him "this feels like a science fair project at Harvard rather than a robust technology" until FHIR landed under it ([MobiHealthNews retrospective](https://www.mobihealthnews.com/content/verilys-dr-josh-mandel-looks-back-birth-smart-health-it)). He now works on the Healthcare Agent Orchestrator connecting Microsoft's agent stack to EHRs and Fabric ([MS Community Hub blog](https://techcommunity.microsoft.com/blog/healthcareandlifesciencesblog/connecting-the-healthcare-agent-orchestrator-to-your-electronic-health-record-an/4427641)).

**Priorities.**
- FHIR R4 correctness. Real Observation/Condition/Encounter resources, not ad-hoc JSON.
- **Substitutability** — same app, any EHR, no rewrite. This is the SMART thesis.
- CDS Hooks-style event-driven clinical decision support.
- Standards over custom extensions.
- Tooling for developers new to healthcare (one of his MSR stated focus areas).

**Our 3 best hooks.**
1. **FHIR R4 in, FHIR R4 out.** Our MCP tools consume a `Bundle` of `Observation` + `Condition` + `Encounter` (HAPI FHIR server) and emit a `RiskAssessment` resource plus a `Communication` for the SBAR. README has a "FHIR R4 resources used" section listing every resource type and cardinality.
2. **Substitutability framing: "Same 4 MCP tools, two wards, zero code change."** The postpartum cameo is literally SMART's substitutable pitch applied to MCP tools. Use the phrase "substitutable clinical tools" in the Devpost tagline.
3. **CDS-Hooks-shaped trigger.** Frame the A2A sentinel as a `patient-view` / `encounter-start` analog: event fires, tool chain runs, structured recommendation comes back. One-line README mention: "A2A agent behaves like a CDS Hooks service, but over A2A+MCP instead of HTTP/JSON-schema."

**Rejection triggers.**
- Custom FHIR extensions when a standard resource exists. If we need a score, use `RiskAssessment.prediction`, not a bespoke field.
- "FHIR-inspired" JSON blobs. He will notice.
- Calling our thing "interoperable" without showing a second EHR target (we mitigate by pointing HAPI FHIR at the same bundles any Epic/Cerner sandbox would accept).
- Hand-wavy auth. Even a fake `Bearer` in the demo request is better than no auth story.

---

### 1.3 Joshua Hickey — Mayo Clinic
Principal Technical Product Manager, Mayo Clinic (patient-experience / clinical platform). Prior: Product Manager at Kaiser Permanente; ~20y Technical PM at AT&T. ([LinkedIn](https://www.linkedin.com/in/joshua-hickey-6364074/), [TheOrg](https://theorg.com/org/mayo-clinic/org-chart/joshua-hickey))

**Research summary.** *Flag: public footprint is thin.* Hickey is a product manager, not a clinician or published researcher — I could not find papers, talks, or blog posts by him. The strongest public signal is his role title ("Principal Technical Product Manager … Customer Patient Experience through data") and Mayo's broader product org (Mayo Clinic Platform, the "Plummer Project" Epic migration) ([Mayo Clinic Platform interoperability brief, 2021](https://www.mayoclinicplatform.org/2021/11/22/interoperability-moves-into-the-21st-century/), [HCPLive on Mayo+Epic](https://www.hcplive.com/view/epic-streamlines-patient-care-at-mayo-clinic)). The project brief's premise that "SBAR is Mayo's internal rapid-response format" and that he runs an OB program is **secondhand from our planning memory** and could not be confirmed in public sources — treat as rumor, don't quote it to him.

**Priorities (inferred from role + Mayo platform direction).**
- Operational rigor: does this ship, does it fit a workflow, who owns it on Monday.
- SBAR as the *lingua franca* of nurse-to-physician escalation — it's the handoff format, so emitting clean SBAR is table stakes.
- Patient-experience continuity across a long episode of care (pre-op → post-op → discharge).
- Platform thinking (Mayo Clinic Platform is explicitly a platform play).
- Low-friction integration with Epic.

**Our 3 best hooks.**
1. **SBAR is a first-class output, not an afterthought.** Show the generated SBAR on screen verbatim at demo minute 2:30, formatted the way a rapid response nurse would actually page it. Include S/B/A/R headers, vitals with units, time stamps, one-line recommendation.
2. **"Who owns this on Monday" slide.** A one-slide operational diagram in the Devpost: trigger → tools → A2A agent → SBAR → nurse pager/secure chat. Hickey's PM brain will like this more than any architecture diagram.
3. **Continuity-of-care framing.** Say explicitly: "The same sentinel wraps the patient from OR handoff through PACU through floor transfer." PMs love patient-journey language.

**Rejection triggers.**
- Demoing an alert with no recipient. "Who gets paged?" must have an answer.
- SBAR that's a paragraph blob instead of structured. Mayo staff read SBAR daily; they will spot a fake.
- Overclaiming Epic integration we don't have. Say "HAPI FHIR sandbox, Epic-compatible resource shapes."

---

### 1.4 Stephon Proctor, PhD, ABPP — CHOP
Associate Chief Health Informatics Officer for EHR Platform & Innovation, Children's Hospital of Philadelphia. Associate Professor, Penn Perelman. Board-certified clinical child psychologist; MS in Biomedical Informatics from Penn. Chair of Epic's Behavioral Health Steering Committee. ([CHOP bio](https://www.chop.edu/doctors/proctor-stephon-n), [LinkedIn](https://www.linkedin.com/in/stephon-proctor/), [stephonproctor.com](https://www.stephonproctor.com/my-experience))

**Research summary.** Proctor's publishing is clinical-psychology-flavored (ADHD, disruptive behavior, anxiety) but his public profile in 2024–2026 is overwhelmingly about bringing agentic AI into CHOP's Epic workflow. He led the rapid-prototype of **CHIPPER**, CHOP's Epic-embedded clinical co-pilot, using generative AI to write the code himself despite not being a traditional engineer ([Becker's, "Inside CHIPPER"](https://www.beckershospitalreview.com/healthcare-information-technology/ehrs/inside-chipper-chops-ai-assistant-built-for-epic/), [Becker's, "CHOP creates AI agent for Epic"](https://www.beckershospitalreview.com/healthcare-information-technology/ehrs/chop-develops-ai-agent-for-epic/), [This Week Health](https://thisweekhealth.com/news_story/chop-revolutionizes-ehr-with-ai-powered-chipper-virtual-assistant-integration/)). He has presented on "generative AI in healthcare" and "AI Triage" for provider messages.

**Priorities (direct quotes).**
- "I hope to move past AI simply delivering information efficiently and toward AI that can actually take action. You've probably heard the term 'agentic AI.' I'm interested in a point where, as a clinician, I can assign tasks to one or more AI agents, and they can handle them for me — for example, prepping for an upcoming visit, summarizing charts, ordering labs, or drafting messages." ([Becker's](https://www.beckershospitalreview.com/healthcare-information-technology/ehrs/inside-chipper-chops-ai-assistant-built-for-epic/))
- On pediatrics: "In a pediatric setting, I've got the patient, the provider, the sibling, the parent — multiple participants in the room. Even something like distinguishing voices correctly in ambient documentation becomes much harder. These tools need to be tested and validated locally." ([Becker's](https://www.beckershospitalreview.com/healthcare-information-technology/ehrs/inside-chipper-chops-ai-assistant-built-for-epic/))
- He is a full-stack-informaticist-by-vibe-coding — he respects people who actually ship.

**Our 3 best hooks.**
1. **"Agentic, not dashboard."** Lead the Devpost with: "Vigil does not show you a risk number. It *escalates* — it drafts the SBAR, opens a `Communication` resource, and routes it to the covering clinician." Use his word "agentic" literally.
2. **Demo minute 1:45 — the clinician triggers a closed-loop action on screen.** Not "here's a chart." The A2A agent returns an unpersisted SBAR draft; the clinician clicks **Approve** in the dashboard; the backend writes a `Communication` FHIR resource plus an `AuditEvent` to HAPI FHIR, and a toast confirms the write. Preserves the "no autonomous action" guarantee while still showing Proctor a real closed-loop FHIR write. This is the single highest-leverage hook for Proctor; if nothing else lands, land this.
3. **Local-validation honesty slide.** A single slide: "Validated only on MIMIC-IV subset + synthetic bundles; CHOP-style local validation required before deployment." This directly echoes his "tested and validated locally" quote and signals we actually read him.

**Rejection triggers.**
- "Alert dashboard" framing. Do not use the word "dashboard" in the Devpost at all.
- Passive "here is a risk score" flows. Every demo step must end in an *action*, not a number.
- Overclaiming. He explicitly says tools need local validation — don't claim generalizability we can't back.
- Ignoring pediatrics entirely. Even one sentence about CHOP-style validation goes a long way.

---

### 1.5 Alice Zheng, MD, MBA, MPH — Foreground Capital
Partner at Foreground Capital (women's health VC, formerly RH Capital). MD/MPH Michigan, MBA HBS, ex-McKinsey, ex-global-health East Africa / Asia. Led investments in Millie (maternity), Seven Starling (women's mental health), Evvy, Cofertility. ([Foreground](https://foreground.vc/portfolio/), [LinkedIn](https://www.linkedin.com/in/alicexzheng/), [DeciBio Q&A](https://www.decibio.com/insights/investing-in-womens-health-decibio-q-a-with-alice-zheng-principal-at-rh-capital), [HLTH 2024 speaker bio](https://hlth.com/speakers/2024/alice-zheng), [World Medical Innovation Forum 2024](https://2024.worldmedicalinnovation.org/speaker/alice-zheng-md/))

**Research summary.** Zheng is an investor, not a researcher. Her public writing lives on LinkedIn and in interviews. RH Capital's and Foreground's stated thesis: maternal health, contraception, reproductive health — "highly underestimated areas of healthcare" ([DeciBio](https://www.decibio.com/insights/investing-in-womens-health-decibio-q-a-with-alice-zheng-principal-at-rh-capital)). Foreground has explicitly backed digital-first platforms for Black women through pregnancy and postpartum ([Foreground portfolio](https://foreground.vc/portfolio/)). She was profiled on Business of the V ([podcast](https://businessofthev.com/episode/alice-zheng-rh-capital/)) and on the HLTH 2024 stage.

**Priorities.**
- Maternal mortality — especially racial disparities; the US maternal mortality rate and the Black-women gap is her pain point.
- Postpartum is a chronically underserved window (the "fourth trimester").
- Market size + defensibility — she is an investor; she wants to see TAM and moat, not just clinical validation.
- Reusable platforms beat single-condition point solutions (better capital efficiency).
- Clinical credibility (she has an MD; weak clinical grounding will read as a red flag).

**Our 3 best hooks.**
1. **Postpartum cameo is *the* Zheng moment.** Devpost section titled "One sentinel, two wards: postoperative and postpartum." Explicitly frame the postpartum sepsis scenario using CDC Adult Sepsis Event criteria applied to the postpartum population and speak to severe maternal morbidity — her vocabulary.
2. **Open the demo with a stat, not an architecture diagram.** "~700 US maternal deaths/year, 80%+ considered preventable (CDC). Vigil catches deterioration in the postpartum window using the same 4 tools that catch postop deterioration." Then swap the ward on screen live.
3. **"Capital-efficient platform" framing in the Devpost.** One line: "The same MCP toolbelt covers postop, postpartum, and any deteriorating-patient workflow — one build, many wards." She will hear "capital efficient" even if we don't say the words.

**Rejection triggers.**
- Treating maternal as a bolt-on. She will immediately see through "we added OB to check a box."
- No mention of disparities. Even one sentence about racial disparity in US maternal mortality matters to her.
- Pure-tech pitch with zero market framing. Include a 2-line "why now / who pays" note.
- Ignoring postpartum entirely and only showing L&D — the fourth trimester is the point.

---

## 2. Hook map

| # | Hook | Mathur | Mandel | Hickey | Proctor | Zheng | Where it lands |
|---|------|:---:|:---:|:---:|:---:|:---:|---|
| H1 | "4.2M postop deaths/year, marginal-lift problem" opener | X | | | | | README top, Devpost paragraph 1 |
| H2 | Demo opens on postop CABG patient | X | | X | | | Demo 0:00–0:45 |
| H3 | DECIDE-AI-flavored `EVALUATION.md` | X | X | | X | | Repo root |
| H4 | FHIR R4 resources section (Observation/Condition/Encounter/RiskAssessment/Communication) | X | X | X | | | README "Clinical Standards Used" |
| H5 | "Substitutable clinical tools" phrase | | X | | | X | Devpost tagline + README tagline |
| H6 | CDS-Hooks-shaped A2A trigger framing | | X | | X | | README "Architecture" |
| H7 | SBAR shown verbatim on screen, structured | | | X | X | | Demo 2:30 |
| H8 | "Who gets paged on Monday" ops slide | | | X | X | | Devpost "How it works" |
| H9 | Continuity-of-care OR→PACU→floor language | X | | X | | | Devpost problem section |
| H10 | "Agentic, not dashboard" — clinician clicks Approve, backend writes `Communication` + `AuditEvent`, toast confirms | | X | | X | | Demo 1:45, Devpost headline |
| H11 | Local-validation honesty slide (MIMIC-IV + synthetic) | X | | | X | | Demo 3:15, README caveats |
| H12 | Postpartum cameo, one-ward swap | | X | | | X | Demo 3:30–4:15 |
| H13 | CDC Adult Sepsis Event applied to postpartum, name-checked | | | | | X | `flag_sepsis_onset` postpartum path + Devpost |
| H14 | Maternal mortality disparities stat | | | | | X | Devpost opening for Zheng path |
| H15 | "One build, many wards" capital-efficient framing | | X | | | X | Devpost "why it matters" |

Every judge has ≥3 hooks: Mathur 5, Mandel 6, Hickey 5, Proctor 6, Zheng 5.

---

## 3. Devpost title + tagline combos (5)

Each optimized for 2–3 judge hooks.

1. **"Vigil — substitutable clinical tools for the deteriorating patient."**
   *One MCP toolbelt wraps postoperative and postpartum patients. FHIR R4 in, FHIR R4 out, SBAR to the nurse on call.*
   → Mandel (substitutable + FHIR), Zheng (postpartum), Hickey (SBAR).

2. **"Vigil — the agentic sentinel for postoperative and postpartum deterioration."**
   *Four MCP tools, one A2A agent, a real SBAR escalation — not a dashboard.*
   → Proctor (agentic, no dashboard), Mathur (postop), Zheng (postpartum).

3. **"From risk score to real escalation: Vigil drafts the SBAR; one click pages the team."**
   *MEWT + qSOFA + CDC Adult Sepsis Event + SBAR generation, composed over MCP and A2A on HAPI FHIR R4.*
   → Hickey (SBAR ops), Proctor (action-taking), Mandel (FHIR R4).

4. **"Vigil — perioperative intelligence, extended to the fourth trimester."**
   *The same 4 tools that catch postop sepsis catch postpartum severe maternal morbidity. One build, two wards.*
   → Mathur (he literally coined "perioperative intelligence"), Zheng (fourth trimester), Mandel (substitutability).

5. **"Vigil — CDS-Hooks-shaped agentic escalation for the deteriorating patient."**
   *A2A agent fires on encounter events, runs MEWT / qSOFA / CDC Adult Sepsis Event deterministically, drafts an SBAR that a clinician approves into a FHIR `Communication`.*
   → Mandel (CDS Hooks lineage), Proctor (agent takes action), Mathur (deterministic composition over black-box).

**Recommended default:** #2. It lands Proctor's single highest-value hook, Mathur's home turf, and Zheng's thesis in one breath.

---

## 4. README judge-facing sections (must-have)

1. **Clinical Standards Used** — Named list of every standard: MEWT, qSOFA (Singer 2016), CDC Adult Sepsis Event (applied to postpartum for the maternal cameo), SBAR (IHI), FHIR R4, MCP, A2A. One line each, cited. (Mandel, Hickey, Mathur)
2. **FHIR R4 Resources** — Table of every FHIR resource type we read and write, with cardinality and whether it's a vanilla resource or extended. Must say "no custom extensions." (Mandel, Hickey)
3. **Reusability: Same Tools, Different Ward** — Literal code snippet showing the only diff between postop and postpartum invocations (a ward/context arg). This is the Zheng + Mandel money shot. (Zheng, Mandel)
4. *(bonus)* **Evaluation & Limitations (DECIDE-AI-lite)** — Intended use, target population, data source, known biases, failure modes, local-validation requirement. (Mathur, Proctor)
5. *(bonus)* **Who Gets Paged** — Operational diagram: trigger → tool chain → agent → SBAR → FHIR Communication → recipient. (Hickey, Proctor)

---

## 5. Vocabulary cheat sheet

| Judge | USE (on demand) | AVOID |
|---|---|---|
| Mathur | perioperative intelligence, postoperative, prospective, bias, DECIDE-AI, marginal lift, qSOFA, MEWS, AKI, myocardial injury, waveform | "beats clinicians," black box, "replaces scoring" |
| Mandel | FHIR R4, Observation, RiskAssessment, Communication, substitutable, write-once, CDS Hooks, standards-based, patient access API | "FHIR-inspired," custom extension, proprietary format, "JSON blob" |
| Hickey | SBAR, rapid response, handoff, workflow, operationalize, paged, covering clinician, episode of care, platform | "POC," "experimental," "you'd need to wire it up," dashboard |
| Proctor | agentic, takes action, co-pilot, orders, drafts, locally validated, pediatric considerations, Epic-embedded | dashboard, alert fatigue, "shows the risk," passive, "read-only" |
| Zheng | maternal mortality, severe maternal morbidity, postpartum, fourth trimester, disparities, underserved, capital-efficient, platform | "we added OB later," "nice to have," pure-tech-no-market |

---

## 6. Worst-case fallback — the ONE hook per judge

If we only land one hook per judge, it must be these (ranked by leverage):

1. **Proctor → H10.** Agent writes a FHIR `Communication` resource on screen. Non-negotiable. If this one lands and nothing else does, we still get his vote.
2. **Zheng → H12.** Postpartum cameo demo'd live. The whole reason maternal is in scope.
3. **Mandel → H4.** "FHIR R4 Resources" README section with zero custom extensions. Cheap, high-signal.
4. **Mathur → H1.** Crit Care Sci 2025 stat in the opener + deterministic wrapping of MEWT/qSOFA.
5. **Hickey → H7.** Verbatim, structured SBAR on screen in the demo.

---

## Research confidence notes

- **Strong public signal:** Mathur, Mandel, Proctor, Zheng — multiple papers / quoted interviews / portfolio pages.
- **Weak public signal:** **Joshua Hickey.** I could not confirm publicly that (a) he runs Mayo's OB program or (b) that "SBAR is Mayo's internal rapid-response format" is his stated position. Public sources show him as a Principal Technical Product Manager working on patient experience/Epic platform work, prior AT&T/Kaiser PM background, MS from Univ. of Phoenix — no papers, no talks, no blog. Treat the memory-note framing of Hickey as a hypothesis, not a quote. Our hooks for him are inferred from his PM-at-Mayo-Platform role, not from his own words. If we can get his LinkedIn or a Mayo Clinic Platform post written by him before the deadline, rewrite §1.3.
- **Secondary unconfirmed claim:** The memory note says Proctor is "pediatric medicine background." He's actually a clinical *child psychologist* — pediatric behavioral health, not pediatric internal medicine. Our hooks work either way, but don't call him a pediatrician.
