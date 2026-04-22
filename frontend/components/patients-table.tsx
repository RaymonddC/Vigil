"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { ChevronRight, ArrowDown } from "lucide-react";
import { RiskBadge } from "@/components/risk-badge";
import { type RiskLevel, riskFromString, isHighOrAbove } from "@/lib/risk";
import { formatTime } from "@/lib/format";
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
// Initials avatar — clinical visual anchor without photo PHI
// ---------------------------------------------------------------------------

function initialsFor(name: string): string {
  const parts = name
    .replace(/[,]/g, "")
    .split(/\s+/)
    .filter(Boolean);
  if (parts.length === 0) return "??";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

// Deterministic neutral hue per patient so the roster reads as a row of
// distinct people at a glance, without leaning on color as risk signal.
function avatarToneFor(id: string): string {
  const tones = [
    "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
    "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300",
    "bg-teal-50 text-teal-700 dark:bg-teal-950/40 dark:text-teal-300",
    "bg-violet-50 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300",
    "bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300",
    "bg-sky-50 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300",
  ];
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return tones[h % tones.length];
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

  const hasRawData = patients.length > 0;

  return (
    <>
      {/* Filter pills */}
      <div
        className="flex items-center gap-2 flex-wrap"
        role="group"
        aria-label="Filter patients"
      >
        <FilterPill
          label="All"
          count={totalCount}
          active={filter === "all"}
          onClick={() => setFilter("all")}
        />
        <FilterPill
          label="High+"
          count={highCount}
          active={filter === "high+"}
          onClick={() => setFilter("high+")}
        />
        <FilterPill
          label="Triggered"
          count={triggeredCount}
          active={filter === "triggered"}
          onClick={() => setFilter("triggered")}
        />
      </div>

      {/* Patient table */}
      <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <caption className="sr-only">Post-op patient roster</caption>
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950">
              <th
                scope="col"
                className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400"
              >
                Patient
              </th>
              <th
                scope="col"
                className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400"
              >
                MRN
              </th>
              <th
                scope="col"
                className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400"
              >
                Trajectory
              </th>
              <th
                scope="col"
                aria-sort="descending"
                className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400"
              >
                <span className="inline-flex items-center gap-1">
                  Risk
                  <ArrowDown
                    size={11}
                    aria-hidden="true"
                    className="text-slate-400 dark:text-slate-500"
                  />
                </span>
              </th>
              <th
                scope="col"
                className="px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400"
              >
                Last alert
              </th>
              <th
                scope="col"
                className="px-4 py-2.5 text-center text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400"
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
                  className="px-4 py-14 text-center"
                >
                  {hasRawData ? (
                    <div className="flex flex-col items-center gap-1.5">
                      <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
                        No patients match this filter
                      </p>
                      <button
                        type="button"
                        onClick={() => setFilter("all")}
                        className="text-xs font-medium text-[#0B5FFF] hover:text-[#0950DB] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF] rounded"
                      >
                        Clear filter →
                      </button>
                    </div>
                  ) : (
                    <p className="text-sm text-slate-400 dark:text-slate-500">
                      Awaiting roster from FHIR server.
                    </p>
                  )}
                </td>
              </tr>
            )}
            {sorted.map((p) => {
              const level = bandToRiskLevel(p.latest_risk_band);
              const isCritical = level === "critical";
              const isHigh = level === "high";
              const accent = isCritical
                ? "before:bg-[#991B1B]"
                : isHigh
                ? "before:bg-[#9A3412]"
                : "before:bg-transparent";
              return (
                <tr
                  key={p.id}
                  className={[
                    "relative group cursor-pointer",
                    "transition-colors",
                    "hover:bg-slate-50/80 dark:hover:bg-slate-800/40",
                    // Left-accent bar for critical/high — clinical scanning aid
                    "before:absolute before:left-0 before:top-0 before:bottom-0 before:w-[3px]",
                    accent,
                  ].join(" ")}
                >
                  <td className="px-4 py-2.5">
                    <Link
                      href={`/patients/${p.id}`}
                      className="flex items-center gap-3 -my-2.5 py-2.5 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#0B5FFF] rounded-sm"
                    >
                      {/* Initials avatar — visual anchor, no PHI photo */}
                      <span
                        aria-hidden="true"
                        className={[
                          "shrink-0 inline-flex items-center justify-center",
                          "w-8 h-8 rounded-full",
                          "text-[11px] font-semibold tracking-wide",
                          "ring-1 ring-inset ring-white/60 dark:ring-slate-700/60",
                          avatarToneFor(p.id),
                        ].join(" ")}
                      >
                        {initialsFor(p.name)}
                      </span>
                      <span className="min-w-0">
                        <span className="block font-medium text-slate-900 dark:text-slate-50 group-hover:text-[#0B5FFF] transition-colors truncate">
                          {p.name}
                        </span>
                        {p.age !== null && (
                          <span className="block text-[11px] text-slate-400 dark:text-slate-500">
                            Age {p.age}
                          </span>
                        )}
                      </span>
                    </Link>
                  </td>
                  <td className="px-4 py-2.5 text-slate-500 dark:text-slate-400 font-[family-name:var(--font-geist-mono)] text-xs tabular-nums">
                    {p.mrn}
                  </td>
                  <td className="px-4 py-2.5 text-slate-600 dark:text-slate-300 capitalize text-xs">
                    {p.trajectory}
                  </td>
                  <td className="px-4 py-2.5">
                    <RiskBadge level={level} />
                  </td>
                  <td className="px-4 py-2.5 text-slate-500 dark:text-slate-400 font-[family-name:var(--font-geist-mono)] tabular-nums text-xs">
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
                  <td className="px-4 py-2.5 text-center">
                    {p.unread_alerts > 0 ? (
                      <span className="inline-flex items-center justify-center min-w-[22px] h-5 px-1.5 rounded-full bg-[#FEF2F2] text-[#991B1B] dark:bg-red-950/40 dark:text-red-300 text-[11px] font-semibold tabular-nums ring-1 ring-inset ring-[#FECACA] dark:ring-red-900/60">
                        {p.unread_alerts}
                      </span>
                    ) : (
                      <span className="text-slate-300 dark:text-slate-600">
                        —
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <Link
                      href={`/patients/${p.id}`}
                      className="inline-flex items-center justify-center w-7 h-7 rounded-md text-slate-400 group-hover:text-[#0B5FFF] group-hover:bg-[#EFF5FF] dark:group-hover:bg-blue-950/30 transition-colors"
                      aria-label={`Open ${p.name}`}
                      tabIndex={-1}
                    >
                      <ChevronRight size={16} aria-hidden="true" />
                    </Link>
                  </td>
                </tr>
              );
            })}
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
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={[
        "inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border transition-colors min-h-[44px]",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF]",
        active
          ? "bg-[#0B5FFF] text-white border-[#0B5FFF] shadow-sm"
          : "bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-800/60",
      ].join(" ")}
    >
      <span>{label}</span>
      <span
        className={[
          "inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded text-[10px] font-semibold tabular-nums",
          active
            ? "bg-white/20 text-white"
            : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400",
        ].join(" ")}
      >
        {count}
      </span>
    </button>
  );
}
