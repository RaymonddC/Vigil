"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { RiskChip } from "@/components/risk-chip";
import { Panel } from "@/components/panel";
import { fetchAlerts, type QueueAlert } from "@/lib/api";
import type { RiskLevel } from "@/lib/risk";
import { formatTime } from "@/lib/format";

const SEVERITY_LEVEL: Record<QueueAlert["severity"], RiskLevel> = {
  critical: "critical",
  urgent: "high",
  info: "low",
};

const RISK_RANK: Record<RiskLevel, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  normal: 4,
};

export default function AlertsPage() {
  const [alerts, setAlerts] = React.useState<QueueAlert[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const router = useRouter();

  const load = React.useCallback(async () => {
    try {
      const data = await fetchAlerts();
      setAlerts(data.alerts);
      setError(null);
    } catch {
      setError("Cannot reach backend — start FastAPI on :8000");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const sorted = React.useMemo(() => {
    return [...alerts].sort((a, b) => {
      const ra = RISK_RANK[SEVERITY_LEVEL[a.severity]];
      const rb = RISK_RANK[SEVERITY_LEVEL[b.severity]];
      if (ra !== rb) return ra - rb;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
  }, [alerts]);

  const wards = "across 2 wards";

  return (
    <div className="page">
      <div className="page__hd">
        <h1 className="page__title">Pending alerts</h1>
        <span className="page__sub">
          {loading
            ? "loading…"
            : `${sorted.length} awaiting review · ${wards}`}
        </span>
      </div>

      {error && !loading && (
        <Panel title="Backend unreachable" meta="cannot reach FastAPI proxy">
          <p className="text-[13px] text-[var(--fg-2)]">{error}</p>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            style={{ marginTop: 8 }}
            onClick={load}
          >
            Retry
          </button>
        </Panel>
      )}

      {!loading && !error && sorted.length === 0 && (
        <div className="empty">
          No pending alerts. Vigil is watching the roster.
        </div>
      )}

      {!loading && !error && sorted.length > 0 && (
        <div className="alerts-list" role="list" aria-label="Pending alerts">
          {sorted.map((alert) => {
            const level = SEVERITY_LEVEL[alert.severity];
            const href = `/patients/${alert.patient_id}/alerts/${alert.id}`;
            const ariaLabel = `Review alert for Patient ${alert.patient_id} — ${alert.severity.toUpperCase()}`;
            return (
              <Link
                key={alert.id}
                href={href}
                role="listitem"
                className="alert-card"
                aria-label={ariaLabel}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    router.push(href);
                  }
                }}
              >
                <RiskChip level={level} />
                <div>
                  <div className="who">
                    Patient {alert.patient_id}
                    <span className="bed">
                      · routed to {alert.recipient_role.replace(/_/g, " ")}
                    </span>
                  </div>
                  <div className="msg">{alert.sbar.assessment}</div>
                </div>
                <div className="meta">
                  flagged {formatTime(alert.created_at)}
                  <br />
                  <span style={{ color: "var(--fg-2)" }}>→ review</span>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
