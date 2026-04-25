"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { RiskChip } from "@/components/risk-chip";
import { RiskStripe } from "@/components/risk-stripe";
import { type RiskLevel, riskFromString } from "@/lib/risk";
import { formatTime } from "@/lib/format";
import type { PatientSummary } from "@/lib/api";

// Risk severity for sort. Critical first.
const RISK_RANK: Record<RiskLevel, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  normal: 4,
};

function bandToRiskLevel(band: string): RiskLevel {
  const normalized = band.toLowerCase();
  if (normalized === "moderate") return "high";
  return riskFromString(normalized);
}

/** Derive a stable bed label from the patient id when the backend doesn't supply one. */
function bedFor(p: PatientSummary): string {
  const tail = p.id.split(/[-_/]/).pop() ?? p.id;
  // If it looks like a number, prefix with B for "Bed". Otherwise show short id.
  return /^\d+$/.test(tail) ? `B-${tail.padStart(2, "0")}` : tail.slice(0, 6).toUpperCase();
}

/** Derive a ward label from the trajectory. */
function wardFor(p: PatientSummary): string {
  if (p.trajectory) return p.trajectory.toUpperCase().replace(/_/g, " ");
  return "—";
}

/** Best-effort short alert summary. */
function alertHeadline(p: PatientSummary): string {
  if (!p.latest_alert_at) return "—";
  const level = bandToRiskLevel(p.latest_risk_band);
  if (level === "critical") return "Deterioration pattern";
  if (level === "high") return "Vitals out of range";
  if (level === "medium") return "Single-vital exceedance";
  if (level === "low") return "Monitoring";
  return "—";
}

export function PatientsTable({ patients }: { patients: PatientSummary[] }) {
  const router = useRouter();

  const sorted = React.useMemo(() => {
    return [...patients].sort((a, b) => {
      const ra = RISK_RANK[bandToRiskLevel(a.latest_risk_band)];
      const rb = RISK_RANK[bandToRiskLevel(b.latest_risk_band)];
      if (ra !== rb) return ra - rb;
      // Secondary: most recent alert first, otherwise stable by id
      const at = a.latest_alert_at ? new Date(a.latest_alert_at).getTime() : 0;
      const bt = b.latest_alert_at ? new Date(b.latest_alert_at).getTime() : 0;
      if (at !== bt) return bt - at;
      return a.id.localeCompare(b.id);
    });
  }, [patients]);

  return (
    <div className="roster" role="table" aria-label="Patient roster">
      <div className="roster__hd" role="row">
        <div role="columnheader" aria-hidden="true"></div>
        <div role="columnheader">Bed</div>
        <div role="columnheader">Patient</div>
        <div role="columnheader">Risk</div>
        <div role="columnheader" className="col-alert">Latest alert</div>
        <div role="columnheader" className="col-vitals">HR · MAP · SpO₂</div>
        <div role="columnheader" className="col-ward">Ward</div>
      </div>

      {sorted.length === 0 && (
        <div className="empty">Awaiting roster from FHIR server.</div>
      )}

      {sorted.map((p) => {
        const level = bandToRiskLevel(p.latest_risk_band);
        const href = `/patients/${p.id}`;
        return (
          <Link
            key={p.id}
            href={href}
            className="roster__row"
            role="row"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                router.push(href);
              }
            }}
          >
            <RiskStripe level={level} />
            <div className="roster__bed" role="cell">{bedFor(p)}</div>
            <div className="roster__name" role="cell">
              {p.name}
              <span className="mrn">
                {p.mrn}
                {p.age != null ? ` · ${p.age}y` : ""}
              </span>
            </div>
            <div role="cell"><RiskChip level={level} /></div>
            <div
              className={`col-alert roster__alert`}
              role="cell"
            >
              {alertHeadline(p)}
              {p.latest_alert_at && (
                <span className="time">{formatTime(p.latest_alert_at)}</span>
              )}
            </div>
            <div
              className={`col-vitals roster__vitals${
                level === "critical" || level === "high" ? " bad" : ""
              }`}
              role="cell"
            >
              {/* PatientSummary doesn't carry vitals; show a placeholder triplet
                  when no alert is active, otherwise the unread badge. */}
              {p.unread_alerts > 0
                ? `${p.unread_alerts} unread`
                : "— · — · —"}
            </div>
            <div className="col-ward roster__ward" role="cell">
              {wardFor(p)}
            </div>
          </Link>
        );
      })}
    </div>
  );
}
