import type { RiskLevel } from "@/lib/risk";

const COLOR: Record<RiskLevel, string> = {
  normal: "var(--risk-normal)",
  low: "var(--risk-low)",
  medium: "var(--risk-medium)",
  high: "var(--risk-high)",
  critical: "var(--risk-critical)",
};

/** 4×30 stripe planted in the leading cell of each roster row. */
export function RiskStripe({ level }: { level: RiskLevel }) {
  return <div className="roster__stripe" style={{ background: COLOR[level] }} aria-hidden="true" />;
}
