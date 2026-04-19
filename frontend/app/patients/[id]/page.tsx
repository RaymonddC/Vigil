import Link from 'next/link';
import { RiskBadge } from '@/components/risk-badge';
import { VitalsChart, type VitalsDataPoint } from '@/components/vitals-chart';
import { AlertTimeline, type AlertTimelineItem } from '@/components/alert-timeline';
import type { RiskLevel } from '@/lib/risk';
import { isHighOrAbove } from '@/lib/risk';
import { getPatient, getLatestAlert } from '@/lib/api';

// ─── API response types ────────────────────────────────────────────────────

interface VitalSeries {
  loinc: string;
  label: string;
  unit: string;
  points: Array<{ t: string; v: number }>;
}

interface PatientDetail {
  patient: {
    id: string;
    mrn: string;
    name: string;
    age: number | null;
    birth_date: string | null;
    gender: string | null;
  };
  encounter: { id: string; start: string | null; status: string } | null;
  vitals_timeseries: VitalSeries[];
  comorbidities: Array<{ code: string; display: string }>;
  risk: {
    qsofa_score: number | null;
    composite_risk: number | null;
    band: string;
    rationale: string;
  };
  recent_alerts: Array<{
    id: string;
    severity: string | null;
    sent: string | null;
    status: string | null;
  }>;
}

interface LatestAlertResponse {
  alert_id: string;
  severity: string | null;
  sent: string | null;
  recipient_role: string | null;
  sbar?: {
    situation: string;
    background: string;
    assessment: string;
    recommendation: string;
  } | null;
  narrative: string;
  model_used: string;
  status: string | null;
}

// ─── Sample fallback data (used when API is unavailable) ──────────────────

const SAMPLE_VITALS: VitalsDataPoint[] = [
  { t: '08:00', hr: 82,  spo2: 98, map: 88, rr: 14, tempC: 37.0 },
  { t: '09:00', hr: 94,  spo2: 96, map: 82, rr: 16, tempC: 37.4 },
  { t: '10:00', hr: 112, spo2: 94, map: 74, rr: 20, tempC: 38.1 },
  { t: '10:30', hr: 128, spo2: 91, map: 58, rr: 26, tempC: 38.9 },
];

// ─── Helpers ──────────────────────────────────────────────────────────────

function isoToHHMM(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
}

function admitHHMM(isoOrNull: string | null | undefined): string {
  return isoOrNull ? isoToHHMM(isoOrNull) : '—';
}

function daysSinceAdmit(isoOrNull: string | null | undefined): string {
  if (!isoOrNull) return 'Day 0';
  const diff = Date.now() - new Date(isoOrNull).getTime();
  return `Day ${Math.floor(diff / 86_400_000)}`;
}

// Normalize UCUM unit strings to display-friendly labels
function normalizeUnit(ucum: string): string {
  const map: Record<string, string> = {
    'mm[Hg]': 'mmHg',
    'Cel':    '°C',
    '/min':   '/min',
    '%':      '%',
  };
  return map[ucum] ?? ucum;
}

// Derive the patient-level risk level from alert severity and risk band
function deriveRiskLevel(detail: PatientDetail): RiskLevel {
  const sev = detail.recent_alerts[0]?.severity;
  if (sev === 'critical') return 'critical';
  if (sev === 'urgent')   return 'high';
  const band = detail.risk.band;
  if (band === 'high')     return 'high';
  if (band === 'moderate') return 'medium';
  if (band === 'low')      return 'low';
  return 'normal';
}

// Merge vitals_timeseries (per-LOINC arrays) into flat chart data points sorted by time.
// SBP ("8480-6") occupies the `map` slot; if DBP ("8462-4") is also present, real MAP
// is calculated: MAP = (SBP + 2·DBP) / 3.
function transformVitals(timeseries: VitalSeries[]): VitalsDataPoint[] {
  type Raw = {
    hr?: number; spo2?: number; sbp?: number; dbp?: number; rr?: number; tempC?: number;
  };
  const LOINC: Record<string, keyof Raw> = {
    '8867-4':  'hr',
    '59408-5': 'spo2',
    '8480-6':  'sbp',
    '8462-4':  'dbp',
    '9279-1':  'rr',
    '8310-5':  'tempC',
  };

  const raw = new Map<string, Raw>();

  for (const series of timeseries) {
    const key = LOINC[series.loinc];
    if (!key) continue;
    for (const pt of series.points) {
      if (!raw.has(pt.t)) raw.set(pt.t, {});
      (raw.get(pt.t) as Record<string, number>)[key] = pt.v;
    }
  }

  return Array.from(raw.entries())
    .sort(([a], [b]) => new Date(a).getTime() - new Date(b).getTime())
    .map(([isoT, v]) => {
      let map: number | undefined = v.sbp;
      if (v.sbp !== undefined && v.dbp !== undefined) {
        map = Math.round((v.sbp + 2 * v.dbp) / 3);
      }
      return {
        t: isoToHHMM(isoT),
        hr: v.hr,
        spo2: v.spo2,
        map,
        rr: v.rr,
        tempC: v.tempC,
      };
    });
}

// Extract the most recent value for each key vital.
type LatestVital = { loinc: string; label: string; value: number; unit: string };

function getLatestVitals(timeseries: VitalSeries[]): LatestVital[] {
  const ORDER = ['8867-4', '8480-6', '59408-5', '9279-1', '8310-5'];
  return ORDER.flatMap((loinc) => {
    const series = timeseries.find((s) => s.loinc === loinc);
    if (!series || series.points.length === 0) return [];
    const latest = [...series.points].sort(
      (a, b) => new Date(b.t).getTime() - new Date(a.t).getTime()
    )[0];
    return [{ loinc, label: series.label, value: latest.v, unit: normalizeUnit(series.unit) }];
  });
}

// Map LOINC code + value to a MEWT alert level (CLINICAL_EVIDENCE.md §2.3)
function vitalAlertLevel(loinc: string, value: number): 'normal' | 'high' | 'critical' {
  if (loinc === '8867-4')  return value >= 130 ? 'critical' : value >= 110 ? 'high' : 'normal';
  if (loinc === '8480-6')  return value <= 90  ? 'critical' : value <= 100 ? 'high' : 'normal';
  if (loinc === '59408-5') return value <= 90  ? 'critical' : value <= 93  ? 'high' : 'normal';
  if (loinc === '9279-1')  return value >= 30  ? 'critical' : value >= 22  ? 'high' : 'normal';
  if (loinc === '8310-5')  return (value >= 39 || value <= 35) ? 'critical'
                                : (value >= 38 || value <= 36) ? 'high' : 'normal';
  return 'normal';
}

// ─── Page ─────────────────────────────────────────────────────────────────

export const metadata = { title: 'Patient Detail — Vigil' };

interface Props {
  params: Promise<{ id: string }>;
}

export default async function PatientDetailPage({ params }: Props) {
  const { id } = await params;

  let detail: PatientDetail | null = null;
  let latestAlert: LatestAlertResponse | null = null;

  try {
    detail = await getPatient(id);
  } catch {
    // API unavailable — render with sample fallback data
  }

  if (detail) {
    try {
      latestAlert = await getLatestAlert(id);
    } catch {
      // No alert yet or API unavailable
    }
  }

  // ── Derived data ──────────────────────────────────────────────────────

  const rawChartData = detail ? transformVitals(detail.vitals_timeseries) : [];
  const chartData: VitalsDataPoint[] = rawChartData.length > 0 ? rawChartData : SAMPLE_VITALS;

  const latestVitals = detail ? getLatestVitals(detail.vitals_timeseries) : [];

  // Trigger markers: alert-fire timestamps formatted to match chart "HH:MM" t-values
  const triggerTimes = (detail?.recent_alerts ?? [])
    .filter((a) => a.sent)
    .map((a) => isoToHHMM(a.sent!));

  const riskLevel: RiskLevel = detail ? deriveRiskLevel(detail) : 'high';
  const showTriggerCard = isHighOrAbove(riskLevel);

  const patient = detail?.patient;
  const encounter = detail?.encounter;

  const genderLabel =
    patient?.gender === 'female' ? 'F' : patient?.gender === 'male' ? 'M' : '';
  const ageGender = [patient?.age ? String(patient.age) : null, genderLabel]
    .filter(Boolean)
    .join(' ');

  const timelineItems: AlertTimelineItem[] = (detail?.recent_alerts ?? []).map((a) => ({
    id: a.id,
    timestamp: a.sent ?? new Date().toISOString(),
    level: a.severity === 'critical' ? 'critical'
         : a.severity === 'urgent'   ? 'high'
         : 'low',
    headline:
      a.severity === 'critical' ? 'Critical deterioration alert'
      : a.severity === 'urgent' ? 'High risk — vital trend ↑'
      : 'Monitoring alert',
  }));

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div className="p-6 space-y-6">

      {/* Back link */}
      <Link
        href="/patients"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 transition-colors"
      >
        <svg
          width="16" height="16" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" strokeWidth="2"
          aria-hidden="true"
        >
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Back to roster
      </Link>

      {/* ── Patient header ─────────────────────────────────────────────── */}
      <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold font-[family-name:var(--font-geist-sans)] text-slate-900 dark:text-slate-50 tracking-tight">
              {patient?.name ?? `Patient ${id}`}
              {ageGender && (
                <span className="text-xl font-normal text-slate-500 dark:text-slate-400 ml-3">
                  {ageGender}
                </span>
              )}
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-500 dark:text-slate-400">
              {patient?.mrn && (
                <span className="font-[family-name:var(--font-geist-mono)] tabular-nums">
                  MRN {patient.mrn}
                </span>
              )}
              {encounter?.start && (
                <>
                  <span aria-hidden="true">·</span>
                  <span>
                    Admit{' '}
                    <time
                      dateTime={encounter.start}
                      className="font-[family-name:var(--font-geist-mono)] tabular-nums"
                    >
                      {admitHHMM(encounter.start)}
                    </time>
                  </span>
                </>
              )}
              <span aria-hidden="true">·</span>
              <span>{daysSinceAdmit(encounter?.start)}</span>
            </div>
            {detail?.comorbidities && detail.comorbidities.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {detail.comorbidities.map((c) => (
                  <span
                    key={c.code}
                    className="inline-flex px-2 py-0.5 rounded-md text-xs bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300"
                  >
                    {c.display}
                  </span>
                ))}
              </div>
            )}
          </div>
          <RiskBadge level={riskLevel} size="lg" />
        </div>
      </div>

      {/* ── Latest vitals cards ───────────────────────────────────────── */}
      {latestVitals.length > 0 && (
        <section aria-label="Current vital signs">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {latestVitals.map((v) => {
              const level = vitalAlertLevel(v.loinc, v.value);
              const borderCls =
                level === 'critical'
                  ? 'border-red-300 dark:border-red-800'
                  : level === 'high'
                  ? 'border-amber-300 dark:border-amber-700'
                  : 'border-slate-200 dark:border-slate-700';
              const valueCls =
                level === 'critical'
                  ? 'text-red-600 dark:text-red-400'
                  : level === 'high'
                  ? 'text-amber-700 dark:text-amber-400'
                  : 'text-slate-900 dark:text-slate-50';
              const displayVal =
                v.value % 1 !== 0 ? v.value.toFixed(1) : String(Math.round(v.value));
              return (
                <div
                  key={v.loinc}
                  className={`bg-white dark:bg-slate-900 rounded-lg border shadow-sm p-4 ${borderCls}`}
                >
                  <p className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                    {v.label}
                  </p>
                  <p
                    className={`mt-1 text-2xl font-semibold tabular-nums font-[family-name:var(--font-geist-mono)] ${valueCls}`}
                  >
                    {displayVal}
                    <span className="text-sm font-normal text-slate-400 dark:text-slate-500 ml-1">
                      {v.unit}
                    </span>
                  </p>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* ── Main grid: vitals chart + alert timeline ──────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_20rem] gap-6">

        {/* Vitals chart */}
        <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm p-6 space-y-4">
          <h2 className="text-base font-semibold font-[family-name:var(--font-geist-sans)] text-slate-800 dark:text-slate-200">
            Vitals Trend
            <span className="ml-2 font-normal text-slate-400 dark:text-slate-500 text-sm">
              {daysSinceAdmit(encounter?.start)}
            </span>
          </h2>
          <VitalsChart
            data={chartData}
            triggerTimes={triggerTimes}
            height={320}
          />
        </div>

        {/* Alert timeline */}
        <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm p-6">
          <h2 className="text-base font-semibold font-[family-name:var(--font-geist-sans)] text-slate-800 dark:text-slate-200 mb-4">
            Recent Alerts
          </h2>
          <AlertTimeline patientId={id} items={timelineItems} />
        </div>
      </div>

      {/* ── What triggered (risk >= HIGH only) ───────────────────────── */}
      {showTriggerCard && (
        <div className="bg-[#FFF7ED] dark:bg-slate-900 rounded-lg border border-[#FED7AA] dark:border-slate-800 p-5">
          <h3 className="text-sm font-semibold text-[#9A3412] dark:text-orange-400 mb-2">
            What triggered this alert
          </h3>
          <p className="text-sm text-slate-700 dark:text-slate-300">
            {detail?.risk.rationale ??
              'Sustained HR ↑ + MAP ↓ over 12 min; qSOFA = 2. Pattern matches early sepsis signature.'}
          </p>
          {detail?.risk.qsofa_score != null && (
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-medium text-slate-500 dark:text-slate-400">qSOFA</span>
                <span
                  className={`font-[family-name:var(--font-geist-mono)] text-sm font-semibold tabular-nums ${
                    detail.risk.qsofa_score >= 2
                      ? 'text-red-600 dark:text-red-400'
                      : 'text-slate-700 dark:text-slate-300'
                  }`}
                >
                  {detail.risk.qsofa_score} / 3
                </span>
              </div>
              {detail.risk.composite_risk != null && (
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                    Composite risk
                  </span>
                  <span className="font-[family-name:var(--font-geist-mono)] text-sm font-semibold tabular-nums text-slate-700 dark:text-slate-300">
                    {(detail.risk.composite_risk * 100).toFixed(0)}%
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── LLM narrative panel (SBAR from generate_escalation_note) ─── */}
      {latestAlert?.sbar && (
        <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
            <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
              SBAR Escalation Note
            </h3>
            <span className="text-xs text-slate-400 dark:text-slate-500 font-[family-name:var(--font-geist-mono)]">
              {latestAlert.model_used}
            </span>
          </div>

          {/* 2×2 SBAR grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-slate-200 dark:divide-slate-700">
            {(
              [
                { key: 'S', label: 'Situation',     text: latestAlert.sbar.situation },
                { key: 'B', label: 'Background',    text: latestAlert.sbar.background },
                { key: 'A', label: 'Assessment',    text: latestAlert.sbar.assessment },
                { key: 'R', label: 'Recommendation', text: latestAlert.sbar.recommendation },
              ] as const
            ).map(({ key, label, text }) => (
              <div key={key} className="p-5">
                <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wide mb-1.5">
                  {key} · {label}
                </p>
                <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
                  {text}
                </p>
              </div>
            ))}
          </div>

          {/* Footer: link to full alert */}
          <div className="px-5 py-3 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 flex justify-end">
            <Link
              href={`/patients/${id}/alerts/${latestAlert.alert_id}`}
              className="text-xs font-medium text-[#0B5FFF] hover:text-[#0950DB] dark:text-blue-400 dark:hover:text-blue-300 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF] rounded"
            >
              View full alert & approve →
            </Link>
          </div>
        </div>
      )}

    </div>
  );
}
