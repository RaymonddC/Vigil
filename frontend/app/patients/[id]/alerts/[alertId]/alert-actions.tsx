'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { LineChart, Line, ResponsiveContainer } from 'recharts';
import { ackAlert } from '@/lib/api';

// ---------------------------------------------------------------------------
// Sparkline — 80×24 px single-line chart per signal
// ---------------------------------------------------------------------------

interface SparklineProps {
  data: Array<{ v: number }>;
  direction: 'up' | 'down' | 'flat';
}

function Sparkline({ data, direction }: SparklineProps) {
  const stroke = direction !== 'flat' ? '#9A3412' : '#64748B';
  return (
    <ResponsiveContainer width={80} height={24}>
      <LineChart data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
        <Line
          type="monotone"
          dataKey="v"
          stroke={stroke}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// Signal row data
// ---------------------------------------------------------------------------

interface Signal {
  name: string;
  unit: string;
  latest: number;
  direction: 'up' | 'down' | 'flat';
  sparkData: Array<{ v: number }>;
}

function dirArrow(dir: 'up' | 'down' | 'flat') {
  return dir === 'up' ? '↑' : dir === 'down' ? '↓' : '→';
}

// ---------------------------------------------------------------------------
// Contributing signals section (pure client — Recharts requires browser)
// ---------------------------------------------------------------------------

interface ContributingSignalsProps {
  severity: string | null;
}

function buildSignals(severity: string | null): Signal[] {
  if (severity === 'critical') {
    return [
      { name: 'HR',   unit: '/min', latest: 128, direction: 'up',   sparkData: [82,94,105,112,120,128].map(v=>({v})) },
      { name: 'MAP',  unit: 'mmHg', latest: 58,  direction: 'down', sparkData: [88,82,74,68,63,58].map(v=>({v})) },
      { name: 'RR',   unit: '/min', latest: 26,  direction: 'up',   sparkData: [14,16,18,20,23,26].map(v=>({v})) },
      { name: 'Temp', unit: '°C',   latest: 38.9,direction: 'up',   sparkData: [37.0,37.4,37.9,38.1,38.5,38.9].map(v=>({v})) },
    ];
  }
  if (severity === 'urgent') {
    return [
      { name: 'HR',   unit: '/min', latest: 112, direction: 'up',   sparkData: [82,88,94,100,106,112].map(v=>({v})) },
      { name: 'MAP',  unit: 'mmHg', latest: 74,  direction: 'down', sparkData: [88,85,82,80,77,74].map(v=>({v})) },
      { name: 'RR',   unit: '/min', latest: 20,  direction: 'up',   sparkData: [14,15,16,17,18,20].map(v=>({v})) },
      { name: 'SpO2', unit: '%',    latest: 94,  direction: 'down', sparkData: [98,97,97,96,95,94].map(v=>({v})) },
    ];
  }
  return [
    { name: 'HR',   unit: '/min', latest: 94,  direction: 'up',   sparkData: [82,84,86,88,91,94].map(v=>({v})) },
    { name: 'MAP',  unit: 'mmHg', latest: 82,  direction: 'flat', sparkData: [88,86,85,84,83,82].map(v=>({v})) },
    { name: 'SpO2', unit: '%',    latest: 96,  direction: 'flat', sparkData: [98,98,97,97,96,96].map(v=>({v})) },
  ];
}

export function ContributingSignals({ severity }: ContributingSignalsProps) {
  const signals = buildSignals(severity);
  return (
    <div className="flex flex-wrap gap-4">
      {signals.map((s) => (
        <div
          key={s.name}
          className="flex items-center gap-2 bg-slate-50 dark:bg-slate-800/50 rounded-md px-3 py-2 border border-slate-200 dark:border-slate-700"
        >
          <Sparkline data={s.sparkData} direction={s.direction} />
          <div className="ml-1">
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400">{s.name}</p>
            <p className="text-sm font-semibold font-[family-name:var(--font-geist-mono)] tabular-nums text-slate-800 dark:text-slate-200">
              {s.direction !== 'flat' && (
                <span className={s.direction === 'up' ? 'text-[#9A3412]' : 'text-[#1E40AF]'}>
                  {dirArrow(s.direction)}{' '}
                </span>
              )}
              {typeof s.latest === 'number' && s.latest % 1 !== 0
                ? s.latest.toFixed(1)
                : s.latest}
              <span className="text-xs font-normal text-slate-400 ml-0.5">{s.unit}</span>
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Approve / Dismiss action buttons
// ---------------------------------------------------------------------------

interface AlertActionsProps {
  patientId: string;
  alertId: string;
}

export function AlertActions({ patientId, alertId }: AlertActionsProps) {
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const router = useRouter();

  async function handleApprove() {
    setLoading(true);
    try {
      const result = await ackAlert(patientId, alertId);
      setDone(true);
      toast.success(
        `Communication ${result.alert_id} written — audit ${result.audit_id}`,
        { duration: 6000 }
      );
      router.refresh();
    } catch {
      toast.error('Write failed — retry', { duration: 5000 });
    } finally {
      setLoading(false);
    }
  }

  function handleDismiss() {
    router.back();
  }

  return (
    <div className="flex items-center gap-3 pt-2">
      <button
        onClick={handleApprove}
        disabled={loading || done}
        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md text-sm font-medium bg-[#0B5FFF] text-white hover:bg-[#0950DB] disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF] min-h-[44px]"
        aria-busy={loading}
      >
        {loading ? 'Sending…' : done ? 'Approved ✓' : 'Approve & send RRT'}
      </button>
      <button
        onClick={handleDismiss}
        disabled={loading}
        className="inline-flex items-center px-5 py-2.5 rounded-md text-sm font-medium border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF] min-h-[44px]"
      >
        Dismiss
      </button>
    </div>
  );
}
