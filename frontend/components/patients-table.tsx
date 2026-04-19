"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { RiskBadge } from "@/components/risk-badge";
import { type RiskLevel, riskFromString, isHighOrAbove } from "@/lib/risk";
import { formatTimeSince, formatTime } from "@/lib/format";
import type { PatientSummary } from "@/lib/api";

// ---------------------------------------------------------------------------
// Risk sort order: critical(4) > high(3) > medium(2) > low(1) > normal(0)
// ---------------------------------------------------------------------------

const RISK_ORDER: Record<string, number> = {
  critical: 4,
  high: 3,
  moderate: 3, // backend uses "moderate" for "high"
  medium: 2,
  low: 1,
  normal: 0,
};

function riskOrd(band: string): number {
  return RISK_ORDER[band.toLowerCase()] ?? 0;
}

/** Map backend risk_band values to RiskLevel display values */
function bandToRiskLevel(band: string): RiskLevel {
  if (band === "moderate") return "high";
  return riskFromString(band);
}

// ---------------------------------------------------------------------------
// Filter types
// ---------------------------------------------------------------------------

type Filter = "all" | "high+" | "triggered";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PatientsTable({ patients }: { patients: PatientSummary[] }) {
  const [filter, setFilter] = useState<Filter>("all");

  // Filter
  const filtered = useMemo(() => {
    switch (filter) {
      case "high+":
        return patients.filter((p) =>
          isHighOrAbove(bandToRiskLevel(p.latest_risk_band))
        );
      case "triggered":
        return patients.filter((p) => p.latest_alert_at !== null);
      default:
        return patients;
    }
  }, [patients, filter]);

  // Sort: risk desc, then time-since-latest-alert asc (most recent first)
  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const riskDiff = riskOrd(b.latest_risk_band) - riskOrd(a.latest_risk_band);
      if (riskDiff !== 0) return riskDiff;
      // Secondary: patients with alerts first, then by alert recency
      if (a.latest_alert_at && !b.latest_alert_at) return -1;
      if (!a.latest_alert_at && b.latest_alert_at) return 1;
      if (a.latest_alert_at && b.latest_alert_at) {
        return (
          new Date(b.latest_alert_at).getTime() -
          new Date(a.latest_alert_at).getTime()
        );
      }
      return 0;
    });
  }, [filtered]);

  const totalCount = patients.length;
  const highCount = patients.filter((p) =>
    isHighOrAbove(bandToRiskLevel(p.latest_risk_band))
  ).length;
  const triggeredCount = patients.filter(
    (p) => p.latest_alert_at !== null
  ).length;

  return (
    <>
      {/* Filter pills */}
      <div className="flex items-center gap-2" role="group" aria-label="Filter patients">
        <FilterPill
          label={`All ${totalCount}`}
          active={filter === "all"}
          onClick={() => setFilter("all")}
        />
        <FilterPill
          label={`High+ ${highCount}`}
          active={filter === "high+"}
          onClick={() => setFilter("high+")}
        />
        <FilterPill
          label={`Triggered ${triggeredCount}`}
          active={filter === "triggered"}
          onClick={() => setFilter("triggered")}
        />
      </div>

      {/* Patient table */}
      <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <caption className="sr-only">Post-op patient roster</caption>
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950">
              <th
                scope="col"
                className="px-4 py-3 text-left font-medium text-slate-500 dark:text-slate-400"
              >
                Name
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-left font-medium text-slate-500 dark:text-slate-400 font-[family-name:var(--font-geist-mono)]"
              >
                MRN
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-left font-medium text-slate-500 dark:text-slate-400"
              >
                Trajectory
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-left font-medium text-slate-500 dark:text-slate-400"
              >
                Risk
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-left font-medium text-slate-500 dark:text-slate-400 font-[family-name:var(--font-geist-mono)]"
              >
                Alert
              </th>
              <th
                scope="col"
                className="px-4 py-3 text-left font-medium text-slate-500 dark:text-slate-400"
              >
                Unread
              </th>
              <th scope="col" className="w-10">
                <span className="sr-only">Open</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {sorted.length === 0 && (
              <tr>
                <td
                  colSpan={7}
                  className="px-4 py-12 text-center text-slate-400 dark:text-slate-500"
                >
                  No patients match the current filter.
                </td>
              </tr>
            )}
            {sorted.map((p) => (
              <tr
                key={p.id}
                className="hover:bg-slate-50 dark:hover:bg-slate-800/50 cursor-pointer transition-colors group"
              >
                <td className="px-4 py-3 font-medium text-slate-900 dark:text-slate-50">
                  <Link
                    href={`/patients/${p.id}`}
                    className="block hover:text-[#0B5FFF] transition-colors"
                  >
                    {p.name}
                  </Link>
                </td>
                <td className="px-4 py-3 text-slate-500 dark:text-slate-400 font-[family-name:var(--font-geist-mono)] text-xs tabular-nums">
                  {p.mrn}
                </td>
                <td className="px-4 py-3 text-slate-600 dark:text-slate-300 capitalize">
                  {p.trajectory}
                </td>
                <td className="px-4 py-3">
                  <RiskBadge level={bandToRiskLevel(p.latest_risk_band)} />
                </td>
                <td className="px-4 py-3 text-slate-500 dark:text-slate-400 font-[family-name:var(--font-geist-mono)] tabular-nums text-xs">
                  {p.latest_alert_at ? (
                    <time dateTime={p.latest_alert_at}>
                      {formatTime(p.latest_alert_at)}
                    </time>
                  ) : (
                    <span className="text-slate-300 dark:text-slate-600">
                      —
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-center">
                  {p.unread_alerts > 0 ? (
                    <span className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full bg-[#FEF2F2] text-[#991B1B] text-xs font-semibold tabular-nums">
                      {p.unread_alerts}
                    </span>
                  ) : (
                    <span className="text-slate-300 dark:text-slate-600">
                      —
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-right">
                  <Link
                    href={`/patients/${p.id}`}
                    className="text-slate-400 hover:text-[#0B5FFF] transition-colors"
                    aria-label={`Open ${p.name}`}
                    tabIndex={-1}
                  >
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      aria-hidden="true"
                    >
                      <polyline points="9 18 15 12 9 6" />
                    </svg>
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// FilterPill
// ---------------------------------------------------------------------------

function FilterPill({
  label,
  active,
  onClick,
}: {
  label: string;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={[
        "px-3 py-1.5 text-xs font-medium rounded-md border transition-colors min-h-[36px]",
        active
          ? "bg-[#0B5FFF] text-white border-[#0B5FFF]"
          : "bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600",
      ].join(" ")}
    >
      {label}
    </button>
  );
}
