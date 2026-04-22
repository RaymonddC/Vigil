'use client';

import { useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
} from 'recharts';

export interface VitalsDataPoint {
  t: string;       // time label, e.g. "08:00"
  hr?: number;
  spo2?: number;
  map?: number;
  rr?: number;
  tempC?: number;
}

export interface VitalsChartProps {
  data?: VitalsDataPoint[];
  /** Initial axis view; internal toggle manages subsequent changes. */
  initialAxis?: 'all' | 'bp' | 'hr-rr' | 'spo2' | 'temp';
  /** Formatted time labels ("HH:MM") matching chart t-values where a trigger fired. */
  triggerTimes?: string[];
  height?: number;
}

type AxisMode = 'all' | 'bp' | 'hr-rr' | 'spo2' | 'temp';

const SAMPLE_DATA: VitalsDataPoint[] = [
  { t: '08:00', hr: 82,  spo2: 98, map: 88, rr: 14, tempC: 37.0 },
  { t: '09:00', hr: 94,  spo2: 96, map: 82, rr: 16, tempC: 37.4 },
  { t: '10:00', hr: 112, spo2: 94, map: 74, rr: 20, tempC: 38.1 },
  { t: '10:30', hr: 128, spo2: 91, map: 58, rr: 26, tempC: 38.9 },
];

const VITAL_CONFIG = {
  hr:    { stroke: '#DC2626', name: 'HR',   unit: 'bpm' },
  spo2:  { stroke: '#2563EB', name: 'SpO₂', unit: '%' },
  map:   { stroke: '#7C3AED', name: 'MAP',  unit: 'mmHg' },
  rr:    { stroke: '#0891B2', name: 'RR',   unit: '/min' },
  tempC: { stroke: '#D97706', name: 'Temp', unit: '°C' },
} as const;

type VitalKey = keyof typeof VITAL_CONFIG;

const AXIS_KEYS: Record<AxisMode, VitalKey[]> = {
  all:     ['hr', 'spo2', 'map', 'rr', 'tempC'],
  bp:      ['map'],
  'hr-rr': ['hr', 'rr'],
  spo2:    ['spo2'],
  temp:    ['tempC'],
};

const AXIS_LABELS: Record<AxisMode, string> = {
  all:     'All',
  bp:      'BP',
  'hr-rr': 'HR / RR',
  spo2:    'SpO₂',
  temp:    'Temp',
};

// MEWT threshold reference lines — shown only when a single vital group is selected.
// Source: CLINICAL_EVIDENCE.md §2.3 — Vigil 7-parameter MEWT implementation.
const MEWT_REFS: Partial<Record<AxisMode, Array<{ value: number; label: string; stroke: string; tier: 'warn' | 'crit' | 'info' }>>> = {
  bp: [
    { value: 100, label: 'SBP ≤100', stroke: '#D97706', tier: 'warn' },
    { value: 90,  label: 'SBP ≤90',  stroke: '#DC2626', tier: 'crit' },
  ],
  'hr-rr': [
    { value: 22,  label: 'RR ≥22',  stroke: '#0891B2', tier: 'info' },
    { value: 110, label: 'HR >110', stroke: '#D97706', tier: 'warn' },
    { value: 130, label: 'HR >130', stroke: '#DC2626', tier: 'crit' },
  ],
  spo2: [
    { value: 93, label: 'SpO₂ <93%', stroke: '#D97706', tier: 'warn' },
    { value: 90, label: 'SpO₂ <90%', stroke: '#DC2626', tier: 'crit' },
  ],
  temp: [
    { value: 36.0, label: 'Temp <36°C', stroke: '#2563EB', tier: 'info' },
    { value: 38.0, label: 'Temp >38°C', stroke: '#D97706', tier: 'warn' },
  ],
};

// Threshold bands — a soft horizontal stripe marking the danger zone above/below
// each critical reference line. Opacity kept low so patient trace stays primary.
const THRESHOLD_BANDS: Partial<Record<AxisMode, Array<{ y1: number; y2: number; fill: string }>>> = {
  bp: [
    { y1: 0, y2: 90, fill: '#FEE2E2' },
  ],
  'hr-rr': [
    { y1: 130, y2: 200, fill: '#FEE2E2' },
  ],
  spo2: [
    { y1: 0, y2: 90, fill: '#FEE2E2' },
  ],
  temp: [
    { y1: 39, y2: 45, fill: '#FEE2E2' },
  ],
};

const AXIS_MODES: AxisMode[] = ['all', 'bp', 'hr-rr', 'spo2', 'temp'];

export function VitalsChart({
  data = SAMPLE_DATA,
  initialAxis = 'all',
  triggerTimes = [],
  height = 320,
}: VitalsChartProps) {
  const [axis, setAxis] = useState<AxisMode>(initialAxis);
  const keys = AXIS_KEYS[axis];
  const refs = MEWT_REFS[axis] ?? [];
  const bands = THRESHOLD_BANDS[axis] ?? [];

  return (
    <div className="space-y-3">
      {/* Axis toggle pills */}
      <div
        className="flex items-center gap-1.5 flex-wrap"
        role="group"
        aria-label="Select vital sign view"
      >
        {AXIS_MODES.map((mode) => (
          <button
            key={mode}
            type="button"
            onClick={() => setAxis(mode)}
            aria-pressed={axis === mode}
            className={[
              'px-3 py-1 rounded-md text-xs font-medium transition-colors min-h-[32px]',
              'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF]',
              axis === mode
                ? 'bg-[#0B5FFF] text-white shadow-sm'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700',
            ].join(' ')}
          >
            {AXIS_LABELS[mode]}
          </button>
        ))}
      </div>

      {/* MEWT threshold legend — appears when a filtered axis is selected */}
      {refs.length > 0 && (
        <div
          className="flex items-center gap-3 flex-wrap text-[11px] text-slate-500 dark:text-slate-400"
          aria-label="MEWT thresholds"
        >
          <span className="inline-flex items-center gap-1.5 font-semibold text-slate-600 dark:text-slate-400 shrink-0 uppercase tracking-wider text-[10px]">
            MEWT
          </span>
          {refs.map((r) => (
            <span key={r.label} className="inline-flex items-center gap-1.5">
              <svg width="16" height="8" aria-hidden="true">
                <line
                  x1="0" y1="4" x2="16" y2="4"
                  stroke={r.stroke}
                  strokeWidth="1.5"
                  strokeDasharray="4 3"
                />
              </svg>
              <span style={{ color: r.stroke }} className="font-medium">{r.label}</span>
            </span>
          ))}
        </div>
      )}

      {/* Recharts multi-line chart */}
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 20, left: -4, bottom: 8 }}>
          <CartesianGrid stroke="#F1F5F9" strokeDasharray="2 4" vertical={false} />

          {/* Danger-zone bands — rendered behind trace at low opacity */}
          {bands.map((b, i) => (
            <ReferenceArea
              key={`band-${i}`}
              y1={b.y1}
              y2={b.y2}
              fill={b.fill}
              fillOpacity={0.35}
              stroke="none"
              ifOverflow="extendDomain"
            />
          ))}

          <XAxis
            dataKey="t"
            stroke="#94A3B8"
            fontSize={11}
            tickLine={false}
            axisLine={{ stroke: '#E2E8F0' }}
            tick={{ fontFamily: 'var(--font-geist-mono)', fill: '#64748B' }}
          />
          <YAxis
            stroke="#94A3B8"
            fontSize={11}
            tickLine={false}
            axisLine={false}
            tick={{ fontFamily: 'var(--font-geist-mono)', fill: '#64748B' }}
            width={40}
          />
          <Tooltip
            cursor={{ stroke: '#CBD5E1', strokeDasharray: '3 3', strokeWidth: 1 }}
            contentStyle={{
              background: '#FFFFFF',
              border: '1px solid #E2E8F0',
              borderRadius: 8,
              fontSize: 12,
              fontFamily: 'var(--font-geist-mono)',
              boxShadow: '0 4px 12px -2px rgb(15 23 42 / 0.08)',
              padding: '8px 10px',
            }}
            labelStyle={{ color: '#0F172A', fontWeight: 600, marginBottom: 4 }}
            itemStyle={{ padding: '1px 0' }}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            formatter={(rawValue: any, name: any): [string, string] => {
              const n = typeof rawValue === 'number' ? rawValue : 0;
              const cfg = Object.values(VITAL_CONFIG).find((c) => c.name === name);
              const formatted = n % 1 !== 0 ? n.toFixed(1) : String(n);
              return [`${formatted}${cfg ? ` ${cfg.unit}` : ''}`, String(name)];
            }}
          />
          <Legend
            wrapperStyle={{ fontSize: 11, fontFamily: 'var(--font-inter)', paddingTop: 8 }}
            iconType="plainline"
            iconSize={14}
          />

          {/* MEWT threshold reference lines — dashed, color-coded */}
          {refs.map((ref) => (
            <ReferenceLine
              key={`mewt-${ref.value}`}
              y={ref.value}
              stroke={ref.stroke}
              strokeDasharray="4 3"
              strokeWidth={1}
              strokeOpacity={ref.tier === 'crit' ? 0.9 : 0.6}
            />
          ))}

          {/* Trigger markers — vertical dashed lines at alert-fire timestamps */}
          {triggerTimes.map((t, i) => (
            <ReferenceLine
              key={`trigger-${i}-${t}`}
              x={t}
              stroke="#DC2626"
              strokeWidth={1.5}
              strokeDasharray="6 3"
              label={{ value: '▼', position: 'top', fontSize: 10, fill: '#DC2626' }}
            />
          ))}

          {/* Vital sign lines — no dots for clean demo recording */}
          {keys.map((key) => (
            <Line
              key={key}
              type="monotone"
              dataKey={key}
              stroke={VITAL_CONFIG[key].stroke}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 2, stroke: '#FFFFFF' }}
              name={VITAL_CONFIG[key].name}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
