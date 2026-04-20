import Link from 'next/link';
import { notFound } from 'next/navigation';
import { RiskBadge } from '@/components/risk-badge';
import { getAlert } from '@/lib/api';
import type { RiskLevel } from '@/lib/risk';
import { AlertActions, ContributingSignals } from './alert-actions';

export const metadata = { title: 'Alert Detail — Vigil' };

interface Props {
  params: Promise<{ id: string; alertId: string }>;
}

function severityToRisk(severity: string | null): RiskLevel {
  if (severity === 'critical') return 'critical';
  if (severity === 'urgent')   return 'high';
  if (severity === 'info')     return 'low';
  return 'medium';
}

function recipientLabel(role: string | null): string {
  if (!role) return 'Rapid Response recommended';
  const map: Record<string, string> = {
    rapid_response: 'Rapid Response recommended',
    charge_nurse:   'Charge Nurse notification',
    attending:      'Attending Physician alert',
  };
  return map[role] ?? role.replace(/_/g, ' ');
}

function isoToHHMM(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
}

// ─── Skeleton placeholder (reused in loading.tsx if added later) ──────────

function SBARSkeleton() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 animate-pulse">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="bg-slate-100 dark:bg-slate-800 rounded-lg p-5 h-28" />
      ))}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────

export default async function AlertDetailPage({ params }: Props) {
  const { id, alertId } = await params;

  let alert: Awaited<ReturnType<typeof getAlert>> | null = null;

  try {
    alert = await getAlert(id, alertId);
  } catch {
    notFound();
  }

  const riskLevel = severityToRisk(alert?.severity ?? null);
  const isCritical = riskLevel === 'critical';

  const sbar = alert?.sbar ?? null;

  return (
    <div className="p-6 space-y-6">

      {/* Breadcrumb */}
      <Link
        href={`/patients/${id}`}
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 transition-colors"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Patient
      </Link>

      {/* Emergency bar */}
      <div
        className={`rounded-lg border-l-4 px-5 py-4 flex items-center justify-between gap-4 ${
          isCritical
            ? 'bg-[#FEF2F2] border-[#991B1B] text-[#991B1B] dark:bg-red-950/40 dark:border-red-400 dark:text-red-300'
            : 'bg-[#FFF7ED] border-[#9A3412] text-[#9A3412] dark:bg-orange-950/40 dark:border-orange-400 dark:text-orange-300'
        }`}
        role="alert"
      >
        <div className="flex items-center gap-3">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          <span className="font-semibold text-sm">
            {isCritical ? 'EMERGENCY' : 'HIGH RISK'} — {recipientLabel(alert?.recipient_role ?? null)}
          </span>
        </div>
        {alert?.sent && (
          <time
            dateTime={alert.sent}
            className="text-xs font-[family-name:var(--font-geist-mono)] tabular-nums opacity-75 shrink-0"
          >
            {isoToHHMM(alert.sent)}
          </time>
        )}
      </div>

      {/* Patient mini-header */}
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-xl font-semibold font-[family-name:var(--font-geist-sans)] text-slate-900 dark:text-slate-50">
          Alert {alertId.slice(0, 8)}
        </h1>
        <RiskBadge level={riskLevel} size="md" />
        {alert?.model_used && (
          <span className="text-xs text-slate-400 dark:text-slate-500 font-[family-name:var(--font-geist-mono)]">
            via {alert.model_used}
          </span>
        )}
      </div>

      {/* 2×2 SBAR grid */}
      {sbar ? (
        <section aria-label="SBAR escalation note">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3">
            SBAR Escalation Note
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {(
              [
                { key: 'S', label: 'Situation',      text: sbar.situation },
                { key: 'B', label: 'Background',     text: sbar.background },
                { key: 'A', label: 'Assessment',     text: sbar.assessment },
                { key: 'R', label: 'Recommendation', text: sbar.recommendation },
              ] as const
            ).map(({ key, label, text }) => (
              <div
                key={key}
                className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm p-5"
              >
                <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wide mb-1.5">
                  {key} · {label}
                </p>
                <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
                  {text}
                </p>
              </div>
            ))}
          </div>
        </section>
      ) : (
        <SBARSkeleton />
      )}

      {/* Narrative (if SBAR absent) */}
      {!sbar && alert?.narrative && (
        <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm p-5">
          <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wide mb-1.5">
            Narrative
          </p>
          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
            {alert.narrative}
          </p>
        </div>
      )}

      {/* Contributing signals */}
      <section aria-label="Contributing vital signals">
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3">
          Contributing signals
        </h2>
        <ContributingSignals severity={alert?.severity ?? null} />
      </section>

      {/* Approve / Dismiss */}
      <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm p-5">
        <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">
          Approving will write a FHIR Communication and AuditEvent to the clinical record.
          Dismiss closes this view without a network call.
        </p>
        <AlertActions patientId={id} alertId={alertId} />
      </div>

    </div>
  );
}
