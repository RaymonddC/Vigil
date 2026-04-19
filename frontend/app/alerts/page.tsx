import Link from "next/link";
import { RiskBadge } from "@/components/risk-badge";
import type { RiskLevel } from "@/lib/risk";

export const metadata = {
  title: "Alerts — Vigil",
};

const PLACEHOLDER_ALERTS = [
  {
    id: "alert-001",
    patientId: "PT-007",
    patientName: "Reyes, Maria",
    level: "critical" as RiskLevel,
    time: "10:32",
    headline: "EMERGENCY — Rapid Response recommended",
    sbar: {
      situation: "34F, POD0 lap chole, triggered critical sepsis onset.",
      assessment: "qSOFA = 2. Lactate 4.2, WBC 19.1. Concern for early sepsis.",
    },
  },
  {
    id: "alert-002",
    patientId: "PT-009",
    patientName: "Osei, Kwame",
    level: "high" as RiskLevel,
    time: "09:58",
    headline: "HIGH — Hemodynamic deterioration trend",
    sbar: {
      situation: "58M, POD1 hip arthroplasty, sustained HR and MAP trend deviation.",
      assessment: "qSOFA = 1. MAP trend downward 12 mmHg over 2h.",
    },
  },
];

export default function AlertsPage() {
  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold font-[family-name:var(--font-geist-sans)] text-slate-900 dark:text-slate-50 tracking-tight">
          Review Queue
        </h1>
        <span className="px-2.5 py-1 text-xs font-medium bg-[#FEF2F2] text-[#991B1B] rounded-md border border-[#FECACA]">
          {PLACEHOLDER_ALERTS.length} pending
        </span>
      </div>

      {/* Alert cards */}
      <div className="space-y-4">
        {PLACEHOLDER_ALERTS.map((alert) => (
          <div
            key={alert.id}
            className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden"
          >
            {/* Alert header bar */}
            <div className={[
              "px-4 py-3 border-l-4 flex items-center justify-between gap-4",
              alert.level === "critical"
                ? "bg-[#FEF2F2] border-[#991B1B]"
                : "bg-[#FFF7ED] border-[#9A3412]",
            ].join(" ")}>
              <div className="flex items-center gap-3">
                <RiskBadge level={alert.level} />
                <span className={[
                  "text-sm font-semibold",
                  alert.level === "critical" ? "text-[#991B1B]" : "text-[#9A3412]",
                ].join(" ")}>
                  {alert.headline}
                </span>
              </div>
              <time
                dateTime={alert.time}
                className="font-[family-name:var(--font-geist-mono)] text-xs text-slate-500 shrink-0 tabular-nums"
              >
                {alert.time}
              </time>
            </div>

            {/* Patient info */}
            <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
              <span className="text-sm font-medium text-slate-900 dark:text-slate-100">{alert.patientName}</span>
              <span className="mx-2 text-slate-300 dark:text-slate-600">·</span>
              <Link
                href={`/patients/${alert.patientId}`}
                className="text-xs text-[#0B5FFF] hover:underline font-[family-name:var(--font-geist-mono)]"
              >
                {alert.patientId}
              </Link>
            </div>

            {/* SBAR preview */}
            <div className="px-4 py-4 grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-1">S: Situation</p>
                <p className="text-sm text-slate-700 dark:text-slate-300">{alert.sbar.situation}</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-1">A: Assessment</p>
                <p className="text-sm text-slate-700 dark:text-slate-300">{alert.sbar.assessment}</p>
              </div>
            </div>

            {/* Action buttons */}
            <div className="px-4 py-3 bg-slate-50 dark:bg-slate-950 border-t border-slate-100 dark:border-slate-800 flex items-center gap-3">
              <button
                type="button"
                className="px-4 py-2 text-sm font-medium bg-[#0B5FFF] text-white rounded-md hover:bg-[#0950DB] transition-colors"
                aria-label={`Approve and send RRT for ${alert.patientName}`}
              >
                Approve &amp; send RRT
              </button>
              <button
                type="button"
                className="px-4 py-2 text-sm font-medium border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              >
                Dismiss
              </button>
              <Link
                href={`/patients/${alert.patientId}`}
                className="ml-auto text-xs text-slate-400 hover:text-[#0B5FFF] transition-colors"
              >
                View vitals →
              </Link>
            </div>
          </div>
        ))}
      </div>

      <p className="text-xs text-slate-400 dark:text-slate-600 text-center">
        Placeholder data — wire to <code className="font-[family-name:var(--font-geist-mono)]">GET /api/patients/*/alerts/latest</code> in Phase 3
      </p>
    </div>
  );
}
