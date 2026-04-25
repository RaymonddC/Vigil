import Link from "next/link";
import type { Metadata } from "next";
import { ArrowRight } from "lucide-react";

export const metadata: Metadata = {
  title: "Vigil — A second pair of eyes on every post-op bed",
  description:
    "Vigil reads vitals, drafts the handoff, and waits for you to approve. A clinician-supervised early-warning agent for post-op and postpartum wards.",
};

// ─── Roster preview (decorative) ─────────────────────────────────────────────

type PreviewRow = {
  bed: string;
  name: string;
  pod: string;
  level: "critical" | "high" | "medium" | "normal";
  glyph: string;
  label: string;
};

const PREVIEW_ROWS: PreviewRow[] = [
  { bed: "B-12", name: "Martinez, A.", pod: "POD 1", level: "critical", glyph: "●", label: "CRITICAL" },
  { bed: "B-07", name: "Okafor, C.",   pod: "PPD 1", level: "high",     glyph: "◕", label: "HIGH" },
  { bed: "B-14", name: "Abramov, N.",  pod: "POD 2", level: "medium",   glyph: "◐", label: "MEDIUM" },
  { bed: "B-03", name: "Singh, R.",    pod: "POD 2", level: "normal",   glyph: "○", label: "NORMAL" },
];

function RosterPreview() {
  return (
    <div
      className="mkt-screen"
      role="img"
      aria-label="Vigil dashboard preview: a roster of four patients sorted by deterioration risk, with one critical patient at the top."
    >
      <div className="mkt-screen__chrome" aria-hidden="true">
        <span className="mkt-screen__dot" />
        <span className="mkt-screen__dot" />
        <span className="mkt-screen__dot" />
        <span className="mkt-screen__url">vigil.health/patients</span>
      </div>
      <div className="mkt-screen__rows">
        {PREVIEW_ROWS.map((r) => (
          <div
            key={r.bed}
            className={
              r.level === "critical"
                ? "mkt-screen__row mkt-screen__row--critical"
                : "mkt-screen__row"
            }
          >
            <div
              className="mkt-screen__stripe"
              style={{ background: `var(--risk-${r.level})` }}
              aria-hidden="true"
            />
            <div className="mkt-screen__bed">{r.bed}</div>
            <div className="mkt-screen__nm">
              {r.name}
              <span className="pod">· {r.pod}</span>
            </div>
            <div className="mkt-screen__chipcell">
              <span className={`rchip rchip--${r.level}`}>
                <span className="g" aria-hidden="true">{r.glyph}</span>
                {r.label}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── SBAR preview (decorative) ───────────────────────────────────────────────

function SbarPreview() {
  return (
    <div
      className="sbar"
      role="img"
      aria-label="Example SBAR draft for a post-op patient with rising lactate, awaiting clinician approval. Approved by Dr. Amit Patel at 14:07 and written to the EHR."
    >
      <div className="sbar__hd">
        <span className="mkt-sbar-tag">SBAR · DRAFT</span>
        <span className="sbar__title">Martinez, A.</span>
        <span className="sbar__time">Bed 12 · POD 1</span>
      </div>
      <div className="sbar__sec">
        <span className="sbar__k">Situation</span>
        <span className="sbar__v">
          Tachycardia and hypotension since 11:40, now with rising lactate{" "}
          <span className="mkt-sbar-cite">1.4 → 3.2</span>.
        </span>
      </div>
      <div className="sbar__sec">
        <span className="sbar__k">Assessment</span>
        <span className="sbar__v">
          Concern for early septic physiology.{" "}
          <span className="mkt-sbar-cite">qSOFA 2 · NEWS2 8</span>.
        </span>
      </div>
      <div className="sbar__sec">
        <span className="sbar__k">Recommend</span>
        <span className="sbar__v">
          Bedside eval within 15 min. Repeat lactate, cultures, crystalloid.
        </span>
      </div>
      <div className="mkt-sbar-attr">
        <span className="av" aria-hidden="true">AP</span>
        <span className="txt">Approved by Dr. Amit Patel · 14:07 · written to EHR</span>
      </div>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function LandingPage() {
  return (
    <div className="mkt">
      {/* ── Hero ─────────────────────────────────────────────── */}
      <section className="mkt-hero" aria-labelledby="hero-h">
        <div className="mkt-hero__bg" aria-hidden="true" />
        <div className="mkt-hero__inner">
          <div>
            <span className="mkt-pill">
              <span className="mkt-pill__dot" aria-hidden="true" />
              Designed for post-op and postpartum wards
            </span>
            <h1 id="hero-h" className="mkt-h1">
              A second pair of eyes on <em>every post-op bed.</em>
            </h1>
            <p className="mkt-sub">
              Vigil reads vitals, drafts the handoff, and waits for you to approve.
            </p>
            <div className="mkt-ctas">
              <Link href="/patients" className="mkt-cta mkt-cta--primary">
                Open the dashboard
                <ArrowRight size={16} strokeWidth={1.75} aria-hidden="true" />
              </Link>
              <a href="#how" className="mkt-cta mkt-cta--ghost">
                See how it works
              </a>
            </div>
          </div>
          <RosterPreview />
        </div>
      </section>

      {/* ── Principles ───────────────────────────────────────── */}
      <div className="mkt-band">
        <section className="mkt-section" id="principles" aria-label="Principles">
          <div className="mkt-principles">
            <article className="mkt-principle">
              <div className="mkt-principle__num">01 · Never acts alone</div>
              <h2 className="mkt-principle__h">Human in the loop by design.</h2>
              <p className="mkt-principle__p">
                Every alert is approved by a clinician before it touches the
                record. The audit trail attributes each action to a named
                person.
              </p>
            </article>
            <article className="mkt-principle">
              <div className="mkt-principle__num">02 · Information-dense</div>
              <h2 className="mkt-principle__h">
                The eye lands on the patient that matters.
              </h2>
              <p className="mkt-principle__p">
                A roster sorted by risk, a five-level scale readable in under a
                second, and tabular vitals on every screen. Designed for a
                12-hour shift, not a product demo.
              </p>
            </article>
            <article className="mkt-principle">
              <div className="mkt-principle__num">03 · Post-op and postpartum</div>
              <h2 className="mkt-principle__h">One pipeline, two wards.</h2>
              <p className="mkt-principle__p">
                The same deterministic agent watches surgical recovery and
                postpartum care. Clinicians move between wards without
                relearning the tool.
              </p>
            </article>
          </div>
        </section>
      </div>

      {/* ── Anatomy / How it works ───────────────────────────── */}
      <section className="mkt-section" id="how" aria-labelledby="anatomy-h">
        <div className="mkt-anatomy">
          <div>
            <p className="mkt-eyebrow">How Vigil watches</p>
            <h2 id="anatomy-h" className="mkt-anatomy__h">
              The SBAR card is the artifact.
            </h2>
            <p className="mkt-anatomy__p">
              The agent watches FHIR vitals, runs MEWT and qSOFA, evaluates
              trends, and when a pattern emerges it drafts a Situation /
              Background / Assessment / Recommendation note — the format every
              clinician already trusts.
            </p>
            <ul className="mkt-anatomy__list">
              <li>Every claim cites the specific vitals and lab values</li>
              <li>Clinicians edit inline before approving</li>
              <li>Approved notes land in the EHR attributed to the approver</li>
              <li>Dismissed drafts are retained for audit, not silently discarded</li>
            </ul>
          </div>
          <SbarPreview />
        </div>
      </section>

      {/* ── Standards strip ──────────────────────────────────── */}
      <div className="mkt-band">
        <section
          className="mkt-section"
          aria-labelledby="standards-h"
          style={{ paddingTop: "48px", paddingBottom: "48px" }}
        >
          <h2 id="standards-h" className="mkt-eyebrow" style={{ marginBottom: "16px" }}>
            Built on open standards
          </h2>
          <div className="mkt-bar">
            <span className="mkt-bar__lbl">Interop</span>
            <span className="mkt-bar__item">FHIR R4</span>
            <span className="mkt-bar__sep" aria-hidden="true">·</span>
            <span className="mkt-bar__item">Model Context Protocol</span>
            <span className="mkt-bar__sep" aria-hidden="true">·</span>
            <span className="mkt-bar__item">Agent-to-Agent Protocol</span>
            <span className="mkt-bar__sep" aria-hidden="true">·</span>
            <span className="mkt-bar__item">SHARP context headers</span>
            <span className="mkt-bar__sep" aria-hidden="true">·</span>
            <span className="mkt-bar__item">SBAR handoff</span>
            <span className="mkt-bar__sep" aria-hidden="true">·</span>
            <span className="mkt-bar__item">WCAG 2.2 AA</span>
            <Link
              href="/marketplace"
              className="mkt-bar__item"
              style={{ marginLeft: "auto", color: "var(--fg-link)" }}
            >
              View on the marketplace →
            </Link>
          </div>
        </section>
      </div>

      {/* ── Footer ───────────────────────────────────────────── */}
      <footer className="mkt-foot">
        <div className="mkt-foot__grow">
          © 2026 Vigil · An instrument, not a replacement. Submitted for
          Agents Assemble — Healthcare AI Endgame.
        </div>
        <Link href="/patients">Dashboard</Link>
        <Link href="/timeline">Timeline</Link>
        <Link href="/marketplace">Marketplace</Link>
        <Link href="/settings">Settings</Link>
      </footer>
    </div>
  );
}
