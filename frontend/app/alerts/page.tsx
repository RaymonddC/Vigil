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
import { Siren, AlertTriangle, Info, Check, ArrowUpRight, RefreshCw } from 'lucide-react';
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

/** Per-severity visual style: left accent thickness + bar tint + icon */
const SEVERITY_STYLE: Record<
  QueueAlert['severity'],
  {
    bar: string;        // top banner bg + text
    accent: string;     // left rail color
    railWidth: string;  // left rail width
    Icon: typeof Siren;
    iconTint: string;
    cardRing: string;
  }
> = {
  critical: {
    bar:       'bg-[#FEF2F2] text-[#991B1B]',
    accent:    'bg-[#991B1B]',
    railWidth: 'w-1.5',
    Icon:      Siren,
    iconTint:  'text-[#991B1B]',
    cardRing:  'ring-[#FECACA] dark:ring-red-900/50',
  },
  urgent: {
    bar:       'bg-[#FFF7ED] text-[#9A3412]',
    accent:    'bg-[#9A3412]',
    railWidth: 'w-1',
    Icon:      AlertTriangle,
    iconTint:  'text-[#9A3412]',
    cardRing:  'ring-[#FED7AA] dark:ring-orange-900/50',
  },
  info: {
    bar:       'bg-[#EFF6FF] text-[#1E40AF]',
    accent:    'bg-[#1E40AF]',
    railWidth: 'w-1',
    Icon:      Info,
    iconTint:  'text-[#1E40AF]',
    cardRing:  'ring-[#BFDBFE] dark:ring-blue-900/50',
  },
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
  const level   = SEVERITY_LEVEL[alert.severity];
  const style   = SEVERITY_STYLE[alert.severity];
  const pending = approvingIds.has(alert.id);
  const Icon    = style.Icon;

  return (
    <div
      className={[
        'relative overflow-hidden bg-white dark:bg-slate-900 rounded-lg shadow-sm',
        'ring-1 ring-inset',
        style.cardRing,
      ].join(' ')}
    >
      {/* Left severity rail — spans full card */}
      <span
        aria-hidden="true"
        className={`absolute left-0 top-0 bottom-0 ${style.railWidth} ${style.accent}`}
      />

      {/* Severity banner */}
      <div className={`pl-5 pr-4 py-3 flex items-center justify-between gap-4 ${style.bar}`}>
        <div className="flex items-center gap-3 min-w-0">
          <Icon size={18} className={`shrink-0 ${style.iconTint}`} aria-hidden="true" />
          <RiskBadge level={level} />
          <span className="text-sm font-semibold truncate">
            {SEVERITY_HEADLINE[alert.severity]}
          </span>
        </div>
        <time
          dateTime={alert.created_at}
          className="font-[family-name:var(--font-geist-mono)] text-xs tabular-nums shrink-0 opacity-80"
        >
          {fmtTime(alert.created_at)}
        </time>
      </div>

      {/* Patient meta row */}
      <div className="pl-5 pr-4 py-2.5 border-b border-slate-100 dark:border-slate-800 flex items-center gap-2 flex-wrap">
        <Link
          href={`/patients/${alert.patient_id}`}
          className="inline-flex items-center gap-1 text-sm font-semibold text-slate-900 dark:text-slate-50 hover:text-[#0B5FFF] transition-colors font-[family-name:var(--font-geist-mono)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF] rounded"
        >
          {alert.patient_id}
          <ArrowUpRight size={12} className="text-slate-400" aria-hidden="true" />
        </Link>
        <span className="text-xs text-slate-300 dark:text-slate-600">·</span>
        <span className="text-xs text-slate-500 dark:text-slate-400">
          Routed to {alert.recipient_role.replace(/_/g, ' ')}
        </span>
        <span className="text-xs text-slate-300 dark:text-slate-600">·</span>
        <span className="inline-flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
          <span className="font-[family-name:var(--font-geist-mono)]">{alert.model_used}</span>
        </span>
      </div>

      {/* SBAR preview — 2-column */}
      <div className="pl-5 pr-4 py-4 grid grid-cols-1 sm:grid-cols-2 gap-5">
        <SBARBlock letter="S" label="Situation" text={alert.sbar.situation} />
        <SBARBlock letter="A" label="Assessment" text={alert.sbar.assessment} />
      </div>

      {/* Action row — Approve is primary, larger, with check icon */}
      <div className="pl-5 pr-4 py-3.5 bg-slate-50/80 dark:bg-slate-950/50 border-t border-slate-100 dark:border-slate-800 flex items-center gap-3 flex-wrap">
        <button
          type="button"
          onClick={() => onApprove(alert)}
          disabled={pending}
          className={[
            'inline-flex items-center gap-2',
            'px-5 py-2.5 text-sm font-semibold rounded-md',
            'bg-[#0B5FFF] text-white',
            'shadow-sm shadow-[#0B5FFF]/20',
            'hover:bg-[#0950DB] hover:shadow-md hover:shadow-[#0B5FFF]/25',
            'transition-all',
            'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF]',
            'disabled:opacity-60 disabled:cursor-not-allowed disabled:shadow-none',
            'min-h-[44px]',
          ].join(' ')}
          aria-label={`Approve and send RRT for ${alert.patient_id}`}
        >
          {pending ? (
            <>
              <Loader />
              Approving…
            </>
          ) : (
            <>
              <Check size={16} strokeWidth={2.5} aria-hidden="true" />
              Approve &amp; send RRT
            </>
          )}
        </button>

        <button
          type="button"
          onClick={() => onDismiss(alert.id)}
          disabled={pending}
          className="px-3 py-2 text-sm font-medium text-slate-600 dark:text-slate-300 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF] min-h-[36px]"
        >
          Dismiss
        </button>

        <Link
          href={`/patients/${alert.patient_id}`}
          className="ml-auto inline-flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400 hover:text-[#0B5FFF] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF] rounded"
        >
          View vitals
          <ArrowUpRight size={11} aria-hidden="true" />
        </Link>
      </div>

      {/* Superseded history footer — only shown when prior alerts were replaced */}
      {(alert.superseded_count ?? 0) > 0 && (
        <div className="pl-5 pr-4 py-2 border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50 flex items-center gap-2">
          <RefreshCw
            size={11}
            className="text-slate-400 dark:text-slate-500 shrink-0"
            aria-hidden="true"
          />
          <p className="text-[11px] text-slate-400 dark:text-slate-500">
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

function SBARBlock({
  letter,
  label,
  text,
}: {
  letter: string;
  label: string;
  text: string;
}) {
  return (
    <div>
      <div className="flex items-baseline gap-2 mb-1.5">
        <span
          aria-hidden="true"
          className="inline-flex items-center justify-center w-5 h-5 rounded bg-[#EFF5FF] text-[#0B5FFF] dark:bg-blue-950/40 dark:text-blue-300 font-[family-name:var(--font-geist-sans)] text-[11px] font-bold"
        >
          {letter}
        </span>
        <p className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
          {label}
        </p>
      </div>
      <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed line-clamp-3">
        {text}
      </p>
    </div>
  );
}

function Loader() {
  return (
    <svg
      className="animate-spin"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.25" />
      <path d="M22 12a10 10 0 0 1-10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
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
      toast.success('Communication written to chart', {
        description: (
          <span className="font-[family-name:var(--font-geist-mono)] text-[11px]">
            {res.alert_id.slice(0, 12)} · audit {res.audit_id.slice(0, 10)}
          </span>
        ),
        duration: 4500,
      });
      setAlerts((prev) => prev.filter((a) => a.id !== alert.id));
    } catch {
      toast.error('Write failed — retry', {
        description: 'Communication + AuditEvent were not persisted to HAPI',
      });
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

  const criticalCount = alerts.filter((a) => a.severity === 'critical').length;
  const urgentCount   = alerts.filter((a) => a.severity === 'urgent').length;

  return (
    <div className="p-6 space-y-5">
      {/* ── Header ── */}
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold font-[family-name:var(--font-geist-sans)] text-slate-900 dark:text-slate-50 tracking-tight">
            Review Queue
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Agent-drafted alerts awaiting clinician approval
          </p>
        </div>

        {!loading && !loadError && (
          <div className="flex items-center gap-2">
            {criticalCount > 0 && (
              <CountChip tone="critical" count={criticalCount} label="critical" />
            )}
            {urgentCount > 0 && (
              <CountChip tone="urgent" count={urgentCount} label="urgent" />
            )}
            <CountChip
              tone={alerts.length > 0 ? 'neutral' : 'calm'}
              count={alerts.length}
              label="pending"
            />
          </div>
        )}
      </div>

      {/* ── Loading skeleton ── */}
      {loading && (
        <div className="space-y-4">
          {[0, 1].map((i) => (
            <div
              key={i}
              className="bg-white dark:bg-slate-900 rounded-lg ring-1 ring-inset ring-slate-200 dark:ring-slate-800 h-56 animate-pulse"
            />
          ))}
        </div>
      )}

      {/* ── Error state ── */}
      {!loading && loadError && (
        <div className="bg-white dark:bg-slate-900 rounded-lg ring-1 ring-inset ring-amber-200 dark:ring-amber-900/50 px-6 py-10 text-center">
          <p className="text-sm font-medium text-amber-700 dark:text-amber-400">{loadError}</p>
          <button
            type="button"
            onClick={load}
            className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-[#0B5FFF] hover:text-[#0950DB] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF] rounded px-1 py-0.5"
          >
            <RefreshCw size={11} aria-hidden="true" />
            Retry
          </button>
        </div>
      )}

      {/* ── Empty state ── */}
      {!loading && !loadError && alerts.length === 0 && (
        <div className="bg-white dark:bg-slate-900 rounded-lg ring-1 ring-inset ring-slate-200 dark:ring-slate-800 px-6 py-12 text-center">
          <div className="mx-auto w-10 h-10 flex items-center justify-center rounded-full bg-emerald-50 dark:bg-emerald-950/40 mb-3">
            <Check
              size={18}
              strokeWidth={2.25}
              className="text-emerald-600 dark:text-emerald-400"
              aria-hidden="true"
            />
          </div>
          <p className="text-sm font-medium text-slate-600 dark:text-slate-300">
            All clear — queue is empty
          </p>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
            The agent has not flagged any patients for review.
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

// ---------------------------------------------------------------------------
// CountChip
// ---------------------------------------------------------------------------

function CountChip({
  count,
  label,
  tone,
}: {
  count: number;
  label: string;
  tone: 'critical' | 'urgent' | 'neutral' | 'calm';
}) {
  const cls = {
    critical: 'bg-[#FEF2F2] text-[#991B1B] ring-[#FECACA] dark:bg-red-950/40 dark:text-red-300 dark:ring-red-900/60',
    urgent:   'bg-[#FFF7ED] text-[#9A3412] ring-[#FED7AA] dark:bg-orange-950/40 dark:text-orange-300 dark:ring-orange-900/60',
    neutral:  'bg-slate-100 text-slate-700 ring-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:ring-slate-700',
    calm:     'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:ring-emerald-900/60',
  }[tone];
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md ring-1 ring-inset ${cls}`}
    >
      <span className="font-[family-name:var(--font-geist-mono)] font-semibold tabular-nums">
        {count}
      </span>
      <span>{label}</span>
    </span>
  );
}
