import Link from "next/link";
import { RiskBadge } from "@/components/risk-badge";
import { VitalsChart } from "@/components/vitals-chart";

export const metadata = {
  title: "Patient Detail — Vigil",
};

interface Props {
  params: Promise<{ id: string }>;
}

export default async function PatientDetailPage({ params }: Props) {
  const { id } = await params;

  return (
    <div className="p-6 space-y-6">
      {/* Back link */}
      <Link
        href="/patients"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 transition-colors"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Back to roster
      </Link>

      {/* Patient header */}
      <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold font-[family-name:var(--font-geist-sans)] text-slate-900 dark:text-slate-50 tracking-tight">
              Patient {id}
            </h1>
            <div className="mt-1 flex items-center gap-3 text-sm text-slate-500 dark:text-slate-400">
              <span>MRN —</span>
              <span>·</span>
              <span>Procedure —</span>
              <span>·</span>
              <span>Day 0</span>
            </div>
          </div>
          <RiskBadge level="high" size="lg" />
        </div>
      </div>

      {/* Main content */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_20rem] gap-6">
        {/* Vitals chart */}
        <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm p-6 space-y-4">
          <h2 className="text-base font-semibold font-[family-name:var(--font-geist-sans)] text-slate-800 dark:text-slate-200">
            Vitals Trend T+0h..T+8h
          </h2>
          <VitalsChart />
        </div>

        {/* Right sidebar — Recent Alerts */}
        <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm p-6 space-y-3">
          <h2 className="text-base font-semibold font-[family-name:var(--font-geist-sans)] text-slate-800 dark:text-slate-200">
            Recent Alerts
          </h2>
          <ul className="space-y-2">
            {[
              { time: "10:32", level: "critical" as const, label: "CRIT sepsis" },
              { time: "09:58", level: "high"     as const, label: "HR trend ↑" },
              { time: "09:14", level: "medium"   as const, label: "SpO2 drop"  },
            ].map((a) => (
              <li key={a.time} className="flex items-center gap-2 text-sm">
                <time
                  dateTime={a.time}
                  className="font-[family-name:var(--font-geist-mono)] text-xs text-slate-400 dark:text-slate-500 tabular-nums"
                >
                  {a.time}
                </time>
                <RiskBadge level={a.level} size="sm" />
                <span className="text-slate-600 dark:text-slate-300">{a.label}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* What triggered card */}
      <div className="bg-[#FFF7ED] dark:bg-slate-900 rounded-lg border border-[#FED7AA] dark:border-slate-800 p-5">
        <h3 className="text-sm font-semibold text-[#9A3412] dark:text-orange-400 mb-2">What triggered this alert</h3>
        <p className="text-sm text-slate-700 dark:text-slate-300">
          Sustained HR ↑ + MAP ↓ over 12 min; qSOFA = 2. Pattern matches early sepsis signature.
          Backend data not yet connected — connect API in Phase 3 (FE1/FE2).
        </p>
      </div>
    </div>
  );
}
