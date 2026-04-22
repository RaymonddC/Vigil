import Link from "next/link";
import type { Metadata } from "next";
import { Activity, Bot, Database, ShieldCheck, ArrowRight, Play } from "lucide-react";
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
  emphasis?: boolean;
};

type Feature = {
  Icon: LucideIcon;
  badge: string;
  badgeClass: string;
  iconTileClass: string;
  title: string;
  body: string;
};

// ─── Data ────────────────────────────────────────────────────────────────────

const STATS: Stat[] = [
  {
    value: "4.2M",
    label: "postoperative deaths per year",
    detail: "More than TB, HIV/AIDS, and malaria combined.",
    citation: "Nepogodiev 2019, Lancet Global Health",
    emphasis: true,
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
    iconTileClass: "bg-[#EFF6FF] text-[#1E40AF]",
    title: "4 Clinical Early-Warning Tools",
    body: "screen_vital_thresholds, score_deterioration_risk, flag_sepsis_onset, generate_escalation_note — each enforces published standards (MEWT, qSOFA, CDC ASE) deterministically, then layers an LLM reasoning pass.",
  },
  {
    Icon: Bot,
    badge: "Path B · A2A",
    badgeClass: "bg-[#ECFDF5] text-[#065F46]",
    iconTileClass: "bg-[#ECFDF5] text-[#065F46]",
    title: "Autonomous Postop Sentinel Agent",
    body: "15-minute monitoring loop: IDLE → POLLING → SCREENING → RISK_SCORING → SEPSIS_CHECK → ESCALATING → AWAITING_REVIEW. Calls all 4 MCP tools in sequence. Never acts without clinician sign-off — every RRT alert requires one-tap approval.",
  },
  {
    Icon: Database,
    badge: "FHIR R4",
    badgeClass: "bg-[#FFFBEB] text-[#92400E]",
    iconTileClass: "bg-[#FFFBEB] text-[#92400E]",
    title: "HAPI FHIR Interoperability",
    body: "Reads Patient + Observation bundles. Writes Communication + AuditEvent on approval. Tenant routing via 3 SHARP headers: x-fhir-server-url, x-fhir-access-token, x-patient-id.",
  },
  {
    Icon: ShieldCheck,
    badge: "Safety · Human-in-loop",
    badgeClass: "bg-[#FFF7ED] text-[#9A3412]",
    iconTileClass: "bg-[#FFF7ED] text-[#9A3412]",
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
        className="relative flex-none px-8 pt-14 pb-12 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden"
        aria-label="Product overview"
      >
        {/* Ambient background — faint radial blue wash, extremely subtle */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-60 dark:opacity-40"
          style={{
            background:
              "radial-gradient(circle at 85% 10%, rgba(11,95,255,0.07), transparent 45%), radial-gradient(circle at 15% 90%, rgba(11,95,255,0.05), transparent 50%)",
          }}
        />

        <div className="relative max-w-3xl">
          {/* Eyebrow */}
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mb-6">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-[#EFF5FF] text-[#0B5FFF] ring-1 ring-inset ring-[#0B5FFF]/15">
              <span className="relative inline-flex w-1.5 h-1.5" aria-hidden="true">
                <span className="absolute inline-flex h-full w-full rounded-full bg-[#0B5FFF] opacity-60 animate-ping" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-[#0B5FFF]" />
              </span>
              Agents Assemble — Healthcare AI Endgame
            </span>
            <span className="text-slate-300 dark:text-slate-600 select-none" aria-hidden="true">
              ·
            </span>
            <span className="text-xs text-slate-500 dark:text-slate-400 font-medium">
              Option B · MCP + A2A
            </span>
          </div>

          {/* H1 */}
          <h1 className="font-[family-name:var(--font-geist-sans)] text-[2.5rem] sm:text-[3rem] font-bold leading-[1.1] tracking-tight text-slate-900 dark:text-slate-50 mb-5">
            Postop + maternal<br />
            <span className="bg-gradient-to-r from-[#0B5FFF] via-[#1E40AF] to-[#0B5FFF] bg-clip-text text-transparent">
              deterioration sentinel.
            </span>
          </h1>

          {/* Pitch */}
          <p className="text-base sm:text-lg text-slate-600 dark:text-slate-300 leading-relaxed mb-8 max-w-2xl">
            Four reusable clinical MCP tools plus one autonomous A2A agent.
            Detects sepsis patterns{" "}
            <strong className="font-semibold text-[#0B5FFF] dark:text-[#3B82F6]">
              30–60 minutes before crisis
            </strong>
            . Clinician approves every alert. Published to the Prompt Opinion
            Marketplace.
          </p>

          {/* CTAs */}
          <nav aria-label="Quick links" className="flex flex-wrap items-center gap-3">
            <Link
              href="/patients"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md text-sm font-semibold bg-[#0B5FFF] text-white shadow-sm shadow-[#0B5FFF]/20 hover:bg-[#0950DB] hover:shadow-md hover:shadow-[#0B5FFF]/25 transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF] min-h-[44px]"
            >
              Open Dashboard
              <ArrowRight size={15} strokeWidth={2.5} aria-hidden="true" />
            </Link>
            <Link
              href="/timeline"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md text-sm font-medium text-slate-700 dark:text-slate-200 hover:text-[#0B5FFF] dark:hover:text-[#3B82F6] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF] min-h-[44px]"
            >
              <Play size={13} fill="currentColor" aria-hidden="true" />
              Watch agent run
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
        className="flex-none px-8 py-10 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950"
        aria-label="Problem scope"
      >
        {/* Section eyebrow */}
        <p className="text-[10px] font-semibold tracking-wider uppercase text-slate-500 dark:text-slate-400 mb-5">
          The scope of the problem
        </p>

        <dl className="grid grid-cols-2 gap-x-6 gap-y-8 max-w-3xl lg:grid-cols-4">
          {STATS.map((s) => (
            <div
              key={s.label}
              className={[
                "flex flex-col gap-1 relative",
                s.emphasis
                  ? "lg:pr-6 lg:border-r lg:border-slate-200 dark:lg:border-slate-800"
                  : "",
              ].join(" ")}
            >
              <dt className="sr-only">{s.label}</dt>
              <dd
                className={[
                  "font-[family-name:var(--font-geist-sans)] font-bold tracking-tight leading-none",
                  s.emphasis
                    ? "text-[2.75rem] sm:text-[3.25rem] bg-gradient-to-br from-[#991B1B] via-[#B91C1C] to-[#DC2626] bg-clip-text text-transparent"
                    : "text-[2rem] text-slate-900 dark:text-slate-50",
                ].join(" ")}
                aria-label={`${s.value}${s.unit ?? ""} — ${s.label}`}
              >
                {s.value}
                {s.unit && (
                  <span
                    className={[
                      "font-semibold ml-0.5",
                      s.emphasis
                        ? "text-lg text-slate-500 dark:text-slate-400 bg-none"
                        : "text-base text-slate-500 dark:text-slate-400",
                    ].join(" ")}
                  >
                    {s.unit}
                  </span>
                )}
              </dd>
              <p
                className={[
                  "font-medium text-slate-700 dark:text-slate-200 mt-1.5",
                  s.emphasis ? "text-sm" : "text-xs",
                ].join(" ")}
              >
                {s.label}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400 leading-snug">
                {s.detail}
              </p>
              {s.citation && (
                <p className="text-[11px] text-slate-400 dark:text-slate-500 italic mt-0.5 font-[family-name:var(--font-geist-mono)]">
                  {s.citation}
                </p>
              )}
            </div>
          ))}
        </dl>
      </section>

      {/* ── Features ─────────────────────────────────────────────── */}
      <section className="flex-1 px-8 py-10" aria-label="Product features">
        <div className="mb-6 max-w-3xl">
          <p className="text-[10px] font-semibold tracking-wider uppercase text-slate-500 dark:text-slate-400 mb-2">
            How Vigil works
          </p>
          <h2 className="font-[family-name:var(--font-geist-sans)] text-xl font-semibold tracking-tight text-slate-900 dark:text-slate-50">
            Two paths, one FHIR-native core
          </h2>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 max-w-3xl">
          {FEATURES.map(({ Icon, badge, badgeClass, iconTileClass, title, body }) => (
            <article
              key={title}
              className="group bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 p-5 shadow-sm hover:shadow-md hover:border-slate-300 dark:hover:border-slate-700 transition-all"
            >
              {/* Header */}
              <div className="flex items-start justify-between mb-3">
                <div className={`p-2 rounded-md ${iconTileClass}`}>
                  <Icon size={18} strokeWidth={2} aria-hidden="true" />
                </div>
                <span
                  className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold font-[family-name:var(--font-geist-mono)] ${badgeClass}`}
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
