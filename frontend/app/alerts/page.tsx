'use client';

/**
 * FE4 — Alerts / Review Queue
 *
 * Fetches GET /api/alerts on mount, then refreshes after each approve.
 * Approve button calls POST /api/patients/{id}/alerts/{alertId}/approve
 * and shows a Sonner toast on success/failure.
 * Dismiss is client-side only (removes from local state).
 */

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { toast } from 'sonner';
import { RiskBadge } from '@/components/risk-badge';
import { ackAlert, fetchAlerts, type QueueAlert } from '@/lib/api';
import type { RiskLevel } from '@/lib/risk';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SEVERITY_LEVEL: Record<QueueAlert['severity'], RiskLevel> = {
  critical: 'critical',
  urgent:   'high',
  info:     'normal',
};

const SEVERITY_HEADLINE: Record<QueueAlert['severity'], string> = {
  critical: 'EMERGENCY — Rapid Response recommended',
  urgent:   'URGENT — Immediate attention required',
  info:     'ADVISORY — Monitor closely',
};

const SEVERITY_BAR_CLASSES: Record<QueueAlert['severity'], string> = {
  critical: 'bg-[#FEF2F2] border-[#991B1B] text-[#991B1B]',
  urgent:   'bg-[#FFF7ED] border-[#9A3412] text-[#9A3412]',
  info:     'bg-[#EFF6FF] border-[#1E40AF] text-[#1E40AF]',
};

function fmtTime(isoTs: string): string {
  try {
    return new Date(isoTs).toLocaleTimeString('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  } catch {
    return isoTs.slice(11, 16) || isoTs;
  }
}

// ---------------------------------------------------------------------------
// AlertCard
// ---------------------------------------------------------------------------

function AlertCard({
  alert,
  approvingIds,
  onApprove,
  onDismiss,
}: {
  alert: QueueAlert;
  approvingIds: Set<string>;
  onApprove: (alert: QueueAlert) => void;
  onDismiss: (id: string) => void;
}) {
  const level    = SEVERITY_LEVEL[alert.severity];
  const barClass = SEVERITY_BAR_CLASSES[alert.severity];
  const pending  = approvingIds.has(alert.id);

  return (
    <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
      {/* Alert header bar */}
      <div className={`px-4 py-3 border-l-4 flex items-center justify-between gap-4 ${barClass}`}>
        <div className="flex items-center gap-3 min-w-0">
          <RiskBadge level={level} />
          <span className="text-sm font-semibold truncate">
            {SEVERITY_HEADLINE[alert.severity]}
          </span>
        </div>
        <time
          dateTime={alert.created_at}
          className="font-[family-name:var(--font-geist-mono)] text-xs text-slate-500 shrink-0 tabular-nums"
        >
          {fmtTime(alert.created_at)}
        </time>
      </div>

      {/* Patient info */}
      <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800 flex items-center gap-2">
        <Link
          href={`/patients/${alert.patient_id}`}
          className="text-sm font-medium text-[#0B5FFF] hover:underline font-[family-name:var(--font-geist-mono)]"
        >
          {alert.patient_id}
        </Link>
        <span className="text-xs text-slate-400 dark:text-slate-600">·</span>
        <span className="text-xs text-slate-500 dark:text-slate-400">
          {alert.recipient_role.replace(/_/g, ' ')} · {alert.model_used}
        </span>
      </div>

      {/* SBAR preview — 2-column */}
      <div className="px-4 py-4 grid grid-cols-2 gap-4">
        <div>
          <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-1">
            S: Situation
          </p>
          <p className="text-sm text-slate-700 dark:text-slate-300 line-clamp-3">
            {alert.sbar.situation}
          </p>
        </div>
        <div>
          <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-1">
            A: Assessment
          </p>
          <p className="text-sm text-slate-700 dark:text-slate-300 line-clamp-3">
            {alert.sbar.assessment}
          </p>
        </div>
      </div>

      {/* Action row */}
      <div className="px-4 py-3 bg-slate-50 dark:bg-slate-950 border-t border-slate-100 dark:border-slate-800 flex items-center gap-3">
        <button
          type="button"
          onClick={() => onApprove(alert)}
          disabled={pending}
          className="px-4 py-2 text-sm font-medium bg-[#0B5FFF] text-white rounded-md hover:bg-[#0950DB] transition-colors disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px]"
          aria-label={`Approve and send RRT for ${alert.patient_id}`}
        >
          {pending ? 'Approving…' : 'Approve & send RRT'}
        </button>

        <button
          type="button"
          onClick={() => onDismiss(alert.id)}
          disabled={pending}
          className="px-4 py-2 text-sm font-medium border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors disabled:opacity-50 min-h-[44px]"
        >
          Dismiss
        </button>

        <Link
          href={`/patients/${alert.patient_id}`}
          className="ml-auto text-xs text-slate-400 hover:text-[#0B5FFF] transition-colors"
        >
          View vitals →
        </Link>
      </div>

      {/* Superseded history footer — only shown when prior alerts were replaced */}
      {(alert.superseded_count ?? 0) > 0 && (
        <div className="px-4 py-2 border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50">
          <p className="text-xs text-slate-400 dark:text-slate-500">
            ↳{' '}
            <Link
              href={`/patients/${alert.patient_id}`}
              className="hover:text-slate-600 dark:hover:text-slate-300 transition-colors underline underline-offset-2"
            >
              {alert.superseded_count} prior alert{alert.superseded_count !== 1 ? 's' : ''} superseded by re-ticks
            </Link>
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AlertsPage() {
  const [alerts, setAlerts]       = useState<QueueAlert[]>([]);
  const [loading, setLoading]     = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [approvingIds, setApprovingIds] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    try {
      const data = await fetchAlerts();
      setAlerts(data.alerts);
      setLoadError(null);
    } catch {
      setLoadError('Cannot reach backend — start FastAPI on :8000');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleApprove = async (alert: QueueAlert) => {
    setApprovingIds((prev) => new Set(prev).add(alert.id));
    try {
      const res = await ackAlert(alert.patient_id, alert.id);
      toast.success(`Communication ${res.alert_id} written — audit ${res.audit_id}`);
      setAlerts((prev) => prev.filter((a) => a.id !== alert.id));
    } catch {
      toast.error('Write failed — retry');
    } finally {
      setApprovingIds((prev) => {
        const next = new Set(prev);
        next.delete(alert.id);
        return next;
      });
    }
  };

  const handleDismiss = (id: string) => {
    setAlerts((prev) => prev.filter((a) => a.id !== id));
  };

  return (
    <div className="p-6 space-y-6">
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold font-[family-name:var(--font-geist-sans)] text-slate-900 dark:text-slate-50 tracking-tight">
          Review Queue
        </h1>

        {!loading && !loadError && (
          <span
            className={[
              'px-2.5 py-1 text-xs font-medium rounded-md border',
              alerts.length > 0
                ? 'bg-[#FEF2F2] text-[#991B1B] border-[#FECACA]'
                : 'bg-slate-100 text-slate-500 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700',
            ].join(' ')}
          >
            {alerts.length} pending
          </span>
        )}
      </div>

      {/* ── Loading skeleton ── */}
      {loading && (
        <div className="space-y-4">
          {[0, 1].map((i) => (
            <div
              key={i}
              className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 h-48 animate-pulse"
            />
          ))}
        </div>
      )}

      {/* ── Error state ── */}
      {!loading && loadError && (
        <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 px-6 py-10 text-center">
          <p className="text-sm text-amber-600 dark:text-amber-400">{loadError}</p>
          <button
            type="button"
            onClick={load}
            className="mt-3 text-xs text-[#0B5FFF] hover:underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* ── Empty state ── */}
      {!loading && !loadError && alerts.length === 0 && (
        <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 px-6 py-12 text-center">
          <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
            No pending alerts
          </p>
          <p className="text-xs text-slate-400 dark:text-slate-600 mt-1">
            All clear — the agent has not flagged any patients requiring review.
          </p>
        </div>
      )}

      {/* ── Alert cards ── */}
      {!loading && !loadError && alerts.length > 0 && (
        <div className="space-y-4" role="list" aria-label="Pending alerts">
          {alerts.map((alert) => (
            <div key={alert.id} role="listitem">
              <AlertCard
                alert={alert}
                approvingIds={approvingIds}
                onApprove={handleApprove}
                onDismiss={handleDismiss}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
