"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

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
  axis?: "all" | "bp" | "hr-rr" | "spo2" | "temp";
  height?: number;
}

const SAMPLE_DATA: VitalsDataPoint[] = [
  { t: "08:00", hr: 82,  spo2: 98, map: 88, rr: 14, tempC: 37.0 },
  { t: "09:00", hr: 94,  spo2: 96, map: 82, rr: 16, tempC: 37.4 },
  { t: "10:00", hr: 112, spo2: 94, map: 74, rr: 20, tempC: 38.1 },
  { t: "10:30", hr: 128, spo2: 91, map: 58, rr: 26, tempC: 38.9 },
];

const VITAL_CONFIG = {
  hr:    { stroke: "#DC2626", name: "HR",   unit: "bpm" },
  spo2:  { stroke: "#2563EB", name: "SpO₂", unit: "%" },
  map:   { stroke: "#7C3AED", name: "MAP",  unit: "mmHg" },
  rr:    { stroke: "#0891B2", name: "RR",   unit: "/min" },
  tempC: { stroke: "#D97706", name: "Temp", unit: "°C" },
} as const;

type VitalKey = keyof typeof VITAL_CONFIG;

const AXIS_KEYS: Record<NonNullable<VitalsChartProps["axis"]>, VitalKey[]> = {
  all:    ["hr", "spo2", "map", "rr", "tempC"],
  bp:     ["map"],
  "hr-rr": ["hr", "rr"],
  spo2:   ["spo2"],
  temp:   ["tempC"],
};

export function VitalsChart({ data = SAMPLE_DATA, axis = "all", height = 320 }: VitalsChartProps) {
  const keys = AXIS_KEYS[axis];

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
        <CartesianGrid stroke="#E2E8F0" strokeDasharray="3 3" />
        <XAxis
          dataKey="t"
          stroke="#64748B"
          fontSize={12}
          tick={{ fontFamily: "var(--font-geist-mono)", fill: "#64748B" }}
        />
        <YAxis
          stroke="#64748B"
          fontSize={12}
          tick={{ fontFamily: "var(--font-geist-mono)", fill: "#64748B" }}
          width={40}
        />
        <Tooltip
          contentStyle={{
            background: "#fff",
            border: "1px solid #E2E8F0",
            borderRadius: 8,
            fontSize: 12,
            fontFamily: "var(--font-geist-mono)",
          }}
          labelStyle={{ color: "#0F172A", fontWeight: 600 }}
        />
        <Legend
          wrapperStyle={{ fontSize: 12, fontFamily: "var(--font-inter)" }}
        />
        {keys.map((key) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            stroke={VITAL_CONFIG[key].stroke}
            strokeWidth={2}
            dot={false}
            name={VITAL_CONFIG[key].name}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
