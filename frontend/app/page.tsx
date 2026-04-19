import Link from "next/link";
import type { Metadata } from "next";
import { Activity, Bot, Database, ShieldCheck, ArrowRight } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export const metadata: Metadata = {
  title: "Vigil — Postop + Maternal Deterioration Sentinel",
  description:
    "4 reusable clinical early-warning MCP tools + 1 autonomous A2A agent. Built on FHIR R4. Published to the Prompt Opinion Marketplace.",
};

// ─── Types ────────────────────────────────────────────────────────────────────

type Stat = {
  value: string;
  unit?: string;
  label: string;
  detail: string;
  citation?: string;
};

type Feature = {
  Icon: LucideIcon;
  badge: string;
  badgeClass: string;
  title: string;
  body: string;
};

// ─── Data ────────────────────────────────────────────────────────────────────

const STATS: Stat[] = [
  {
    value: "4.2M",
    label: "postoperative deaths per year",
    detail: "More than TB, HIV/AIDS, and malaria each.",
    citation: "Nepogodiev 2019, Lancet Global Health",
  },
  {
    value: "260K",
    label: "maternal deaths per year",
    detail: "One woman every 2 minutes — mostly haemorrhage or sepsis.",
    citation: "WHO 2023",
  },
  {
    value: "30–60",
    unit: "min",
    label: "before crisis, signs appear",
    detail: "The danger lives in patterns, not single thresholds.",
  },
  {
    value: "8+",
    unit: " pts",
    label: "patients per nurse post-surgery",
    detail: "No human can hold that multivariate pattern for all of them.",
  },
];

const FEATURES: Feature[] = [
  {
    Icon: Activity,
    badge: "Path A · MCP",
    badgeClass: "bg-[#EFF6FF] text-[#1E40AF]",
    title: "4 Clinical Early-Warning Tools",
    body: "screen_vital_thresholds, score_deterioration_risk, flag_sepsis_onset, generate_escalation_note — each enforces published standards (MEWT, qSOFA, CDC ASE) deterministically, then layers an LLM reasoning pass.",
  },
  {
    Icon: Bot,
    badge: "Path B · A2A",
    badgeClass: "bg-[#ECFDF5] text-[#065F46]",
    title: "Autonomous Postop Sentinel Agent",
    body: "15-minute monitoring loop: IDLE → POLLING → SCREENING → RISK_SCORING → SEPSIS_CHECK → ESCALATING → AWAITING_REVIEW. Calls all 4 MCP tools in sequence. Never acts without clinician sign-off — every RRT alert requires one-tap approval.",
  },
  {
    Icon: Database,
    badge: "FHIR R4",
    badgeClass: "bg-[#FFFBEB] text-[#92400E]",
    title: "HAPI FHIR Interoperability",
    body: "Reads Patient + Observation bundles. Writes Communication + AuditEvent on approval. Tenant routing via 3 SHARP headers: x-fhir-server-url, x-fhir-access-token, x-patient-id.",
  },
  {
    Icon: ShieldCheck,
    badge: "Safety · Human-in-loop",
    badgeClass: "bg-[#FFF7ED] text-[#9A3412]",
    title: "Clinician Approves Before Alert Fires",
    body: "AI drafts the SBAR note. The clinician reviews and taps Approve. One click sends the RRT Communication to FHIR and logs the AuditEvent. Zero autonomous escalation.",
  },
];

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function LandingPage() {
  return (
    <div className="min-h-full flex flex-col">
      {/* ── Hero ─────────────────────────────────────────────────── */}
      <section
        className="flex-none px-8 pt-12 pb-10 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900"
        aria-label="Product overview"
      >
        <div className="max-w-2xl">
          {/* Eyebrow */}
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mb-5">
            <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium bg-[#EFF5FF] text-[#0B5FFF]">
              Agents Assemble — Healthcare AI Endgame
            </span>
            <span className="text-slate-300 dark:text-slate-600 select-none" aria-hidden="true">
              ·
            </span>
            <span className="text-xs text-slate-500 dark:text-slate-400">Option B · MCP + A2A</span>
          </div>

          {/* H1 */}
          <h1 className="font-[family-name:var(--font-geist-sans)] text-[2.25rem] font-bold leading-[1.15] tracking-tight text-slate-900 dark:text-slate-50 mb-4">
            Postop + maternal
            <br />
            deterioration sentinel.
          </h1>

          {/* Pitch */}
          <p className="text-base text-slate-600 dark:text-slate-300 leading-relaxed mb-8 max-w-xl">
            Four reusable clinical MCP tools + one autonomous A2A agent. Detects
            sepsis patterns{" "}
            <strong className="font-semibold text-slate-800 dark:text-slate-200">
              30–60 minutes before crisis
            </strong>
            . Published to the Prompt Opinion Marketplace.
          </p>

          {/* CTAs */}
          <nav aria-label="Quick links" className="flex flex-wrap items-center gap-3">
            <Link
              href="/patients"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md text-sm font-medium bg-[#0B5FFF] text-white hover:bg-[#0950DB] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF] min-h-[44px]"
            >
              Open Dashboard
              <ArrowRight size={15} aria-hidden="true" />
            </Link>
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="View source on GitHub (opens in new tab)"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md text-sm font-medium bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700/60 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF] min-h-[44px]"
            >
              {/* GitHub mark (inline SVG, no external request) */}
              <svg
                width="15"
                height="15"
                viewBox="0 0 24 24"
                fill="currentColor"
                aria-hidden="true"
              >
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
              </svg>
              GitHub
            </a>
          </nav>
        </div>
      </section>

      {/* ── Stats ────────────────────────────────────────────────── */}
      <section
        className="flex-none px-8 py-8 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950"
        aria-label="Problem scope"
      >
        <dl className="grid grid-cols-2 gap-x-6 gap-y-7 max-w-2xl lg:grid-cols-4">
          {STATS.map((s) => (
            <div key={s.label} className="flex flex-col gap-0.5">
              <dt className="sr-only">{s.label}</dt>
              <dd
                className="font-[family-name:var(--font-geist-sans)] text-[2rem] font-bold tracking-tight text-slate-900 dark:text-slate-50 leading-none"
                aria-label={`${s.value}${s.unit ?? ""} — ${s.label}`}
              >
                {s.value}
                {s.unit && (
                  <span className="text-base font-semibold text-slate-500 dark:text-slate-400 ml-0.5">
                    {s.unit}
                  </span>
                )}
              </dd>
              <p className="text-xs font-medium text-slate-600 dark:text-slate-300 mt-1">
                {s.label}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400 leading-snug">
                {s.detail}
              </p>
              {s.citation && (
                <p className="text-[11px] text-slate-400 dark:text-slate-500 italic mt-0.5">
                  {s.citation}
                </p>
              )}
            </div>
          ))}
        </dl>
      </section>

      {/* ── Features ─────────────────────────────────────────────── */}
      <section className="flex-1 px-8 py-8" aria-label="Product features">
        <h2 className="font-[family-name:var(--font-geist-sans)] text-lg font-semibold tracking-tight text-slate-900 dark:text-slate-50 mb-5">
          What Vigil does
        </h2>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 max-w-2xl">
          {FEATURES.map(({ Icon, badge, badgeClass, title, body }) => (
            <article
              key={title}
              className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 p-5 shadow-sm hover:shadow-md transition-shadow"
            >
              {/* Header */}
              <div className="flex items-start justify-between mb-3">
                <div className="p-2 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                  <Icon size={18} aria-hidden="true" />
                </div>
                <span
                  className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${badgeClass}`}
                >
                  {badge}
                </span>
              </div>

              {/* Copy */}
              <h3 className="font-[family-name:var(--font-geist-sans)] text-sm font-semibold text-slate-900 dark:text-slate-50 mb-2 leading-snug">
                {title}
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                {body}
              </p>
            </article>
          ))}
        </div>
      </section>

      {/* ── Footer note ─────────────────────────────────────────── */}
      <footer className="flex-none px-8 py-4 border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
        <p className="text-[11px] text-slate-400 dark:text-slate-500 leading-relaxed">
          Clinical standards: MEWT vital thresholds · qSOFA sepsis criteria · CDC
          Adult Sepsis Event (ASE) surveillance · SBAR handoff framework. Zero real
          PHI. All data is synthetic FHIR bundles.
        </p>
      </footer>
    </div>
  );
}
