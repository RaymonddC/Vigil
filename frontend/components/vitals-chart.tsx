"use client";

import * as React from "react";
import { VitalTile } from "@/components/vital-tile";
import { Panel } from "@/components/panel";

// ─── Types ─────────────────────────────────────────────────────────────────

export interface VitalSeries {
  loinc: string;
  label: string;
  unit: string;
  points: Array<{ t: string; v: number }>;
}

export interface VitalsChartProps {
  series: VitalSeries[];
  /** "updated 14:02" — small monospace stamp in the header. */
  updatedAt?: string;
  /** Optional vertical flag line (e.g. when alert fired). ISO-8601 string. */
  flagAt?: string | null;
}

// ─── Constants ─────────────────────────────────────────────────────────────

const LOINC = {
  HR: "8867-4",
  SPO2: "59408-5",
  SBP: "8480-6",
  DBP: "8462-4",
  RR: "9279-1",
  TEMP: "8310-5",
} as const;

const W = 720;
const H = 200;
const PAD_L = 36;
const PAD_R = 10;
const PAD_T = 14;
const PAD_B = 24;
const IW = W - PAD_L - PAD_R;
const IH = H - PAD_T - PAD_B;

// ─── Helpers ──────────────────────────────────────────────────────────────

function findSeries(series: VitalSeries[], loinc: string): VitalSeries | undefined {
  return series.find((s) => s.loinc === loinc);
}

function pickLatest(series?: VitalSeries): { v: number | null; t: string | null } {
  if (!series || series.points.length === 0) return { v: null, t: null };
  const sorted = [...series.points].sort(
    (a, b) => new Date(b.t).getTime() - new Date(a.t).getTime()
  );
  return { v: sorted[0].v, t: sorted[0].t };
}

/**
 * Build (sbp, dbp) → MAP series. If only SBP is present we use SBP as the
 * fallback; the design treats the middle trace as MAP regardless.
 */
function buildMapSeries(series: VitalSeries[]): { points: Array<{ t: string; v: number }>; unit: string; label: string } {
  const sbp = findSeries(series, LOINC.SBP);
  const dbp = findSeries(series, LOINC.DBP);
  if (!sbp) return { points: [], unit: "mmHg", label: "MAP" };

  const dbpMap = new Map<string, number>();
  if (dbp) {
    for (const p of dbp.points) dbpMap.set(p.t, p.v);
  }
  const points = sbp.points.map((p) => {
    const dbpVal = dbpMap.get(p.t);
    if (dbpVal != null) {
      return { t: p.t, v: Math.round((p.v + 2 * dbpVal) / 3) };
    }
    return { t: p.t, v: p.v };
  });
  return { points, unit: "mmHg", label: "MAP" };
}

/** Map a raw value into chart pixel space. */
function makeScaler(min: number, max: number) {
  return (v: number, i: number, total: number): [number, number] => {
    const x = PAD_L + (i / Math.max(1, total - 1)) * IW;
    const y = PAD_T + (1 - (v - min) / Math.max(0.0001, max - min)) * IH;
    return [x, y];
  };
}

function pathFromPoints(points: Array<[number, number]>): string {
  if (points.length === 0) return "";
  return (
    "M" +
    points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" L")
  );
}

// ─── Component ─────────────────────────────────────────────────────────────

export function VitalsChart({ series, updatedAt, flagAt }: VitalsChartProps) {
  const hr = findSeries(series, LOINC.HR);
  const spo2 = findSeries(series, LOINC.SPO2);
  const temp = findSeries(series, LOINC.TEMP);
  const mapBuilt = buildMapSeries(series);

  // Chronological ordering — earliest first → "now" on the right.
  const sortedHr   = hr   ? [...hr.points].sort((a, b) => new Date(a.t).getTime() - new Date(b.t).getTime())   : [];
  const sortedMap  = [...mapBuilt.points].sort((a, b) => new Date(a.t).getTime() - new Date(b.t).getTime());
  const sortedSpo2 = spo2 ? [...spo2.points].sort((a, b) => new Date(a.t).getTime() - new Date(b.t).getTime()) : [];

  const scaleHr  = makeScaler(50, 160);
  const scaleMap = makeScaler(40, 100);
  const scaleSp  = makeScaler(85, 100);

  const hrPts   = sortedHr.map((p, i) => scaleHr (p.v, i, sortedHr.length));
  const mapPts  = sortedMap.map((p, i) => scaleMap(p.v, i, sortedMap.length));
  const spo2Pts = sortedSpo2.map((p, i) => scaleSp(p.v, i, sortedSpo2.length));

  // Optional flag x-position (proportion of HR series timespan).
  let flagX: number | null = null;
  if (flagAt && sortedHr.length > 1) {
    const flagMs = new Date(flagAt).getTime();
    const t0 = new Date(sortedHr[0].t).getTime();
    const tN = new Date(sortedHr[sortedHr.length - 1].t).getTime();
    if (tN > t0 && flagMs >= t0 && flagMs <= tN) {
      const frac = (flagMs - t0) / (tN - t0);
      flagX = PAD_L + frac * IW;
    }
  }

  // Latest values for the tile row underneath.
  const latestHr   = pickLatest(hr).v;
  const latestMap  = sortedMap.length > 0 ? sortedMap[sortedMap.length - 1].v : null;
  const latestSpo2 = pickLatest(spo2).v;
  const latestTemp = pickLatest(temp).v;

  const fmt = (v: number | null, decimals = 0) =>
    v == null ? "—" : decimals > 0 ? v.toFixed(decimals) : Math.round(v).toString();

  return (
    <Panel
      title="Vitals · 24 hours"
      meta={updatedAt ? `updated ${updatedAt}` : undefined}
      right={
        <span
          style={{
            display: "flex",
            gap: 14,
            fontFamily: "var(--font-mono)",
            fontSize: 10,
            color: "var(--fg-3)",
          }}
        >
          <LegendChip color="var(--risk-critical)" label="HR" />
          <LegendChip color="var(--ink-700)" label="MAP" />
          <LegendChip color="var(--success)" label="SpO₂" />
        </span>
      }
      bodyClassName=""
    >
      <div className="panel__body" style={{ padding: "10px 14px 4px" }}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          style={{ width: "100%", height: 200, display: "block" }}
          role="img"
          aria-label="24-hour trend of HR, MAP, SpO₂"
        >
          {/* gridlines */}
          <g stroke="var(--border-subtle)" strokeWidth="1">
            {[0, 0.25, 0.5, 0.75, 1].map((f, i) => (
              <line
                key={i}
                x1={PAD_L}
                x2={W - PAD_R}
                y1={PAD_T + f * IH}
                y2={PAD_T + f * IH}
              />
            ))}
          </g>
          {/* y-axis labels (HR scale 50–160) */}
          <g fill="var(--fg-3)" fontFamily="var(--font-mono)" fontSize="10">
            <text x="4" y={PAD_T + 4}>160</text>
            <text x="4" y={PAD_T + IH / 2 + 4}>105</text>
            <text x="4" y={PAD_T + IH + 4}>50</text>
          </g>
          {/* flag line */}
          {flagX != null && (
            <line
              x1={flagX}
              x2={flagX}
              y1={PAD_T}
              y2={PAD_T + IH}
              stroke="var(--risk-critical)"
              strokeWidth="1"
              strokeDasharray="2 3"
            />
          )}
          {/* traces */}
          {hrPts.length > 0 && (
            <path d={pathFromPoints(hrPts)} stroke="var(--risk-critical)" strokeWidth="1.5" fill="none" />
          )}
          {mapPts.length > 0 && (
            <path d={pathFromPoints(mapPts)} stroke="var(--ink-700)" strokeWidth="1.5" fill="none" />
          )}
          {spo2Pts.length > 0 && (
            <path d={pathFromPoints(spo2Pts)} stroke="var(--success)" strokeWidth="1.5" fill="none" />
          )}
          {/* x-axis labels */}
          <g fill="var(--fg-3)" fontFamily="var(--font-mono)" fontSize="10">
            {["−24h", "−18", "−12", "−6", "now"].map((label, i) => (
              <text
                key={i}
                x={PAD_L + (i / 4) * IW}
                y={H - 6}
                textAnchor={i === 0 ? "start" : i === 4 ? "end" : "middle"}
              >
                {label}
              </text>
            ))}
          </g>
          {/* empty-state hint when zero data */}
          {hrPts.length === 0 && mapPts.length === 0 && spo2Pts.length === 0 && (
            <text
              x={W / 2}
              y={H / 2}
              textAnchor="middle"
              fill="var(--fg-3)"
              fontFamily="var(--font-mono)"
              fontSize="11"
            >
              No vitals recorded in the last 24 h.
            </text>
          )}
        </svg>
      </div>

      <div className="vital-grid">
        <VitalTile label="HR"   value={fmt(latestHr)}      unit="bpm"  alert={latestHr   != null && latestHr   > 110} />
        <VitalTile label="MAP"  value={fmt(latestMap)}     unit="mmHg" alert={latestMap  != null && latestMap  < 65} />
        <VitalTile label="SpO₂" value={fmt(latestSpo2)}    unit="%"    alert={latestSpo2 != null && latestSpo2 < 95} />
        <VitalTile label="Temp" value={fmt(latestTemp, 1)} unit="°C"   alert={latestTemp != null && latestTemp > 38} />
      </div>
    </Panel>
  );
}

function LegendChip({ color, label }: { color: string; label: string }) {
  return (
    <span style={{ whiteSpace: "nowrap" }}>
      <span
        style={{
          display: "inline-block",
          width: 10,
          height: 2,
          background: color,
          marginRight: 4,
          verticalAlign: "middle",
        }}
      />
      {label}
    </span>
  );
}
