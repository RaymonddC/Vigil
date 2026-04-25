import * as React from "react";
import type { RiskLevel } from "@/lib/risk";

const RISK_GLYPH: Record<RiskLevel, string> = {
  normal: "○",
  low: "◔",
  medium: "◐",
  high: "◕",
  critical: "●",
};

const RISK_LABEL: Record<RiskLevel, string> = {
  normal: "Normal",
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

export interface RiskChipProps {
  level: RiskLevel;
  className?: string;
}

/**
 * RiskChip — pill with paired typographic glyph. Color is never the only
 * signal: glyph + label + ARIA text carry the severity for screen readers
 * and color-blind users alike.
 */
export function RiskChip({ level, className }: RiskChipProps) {
  return (
    <span
      className={["rchip", `rchip--${level}`, className].filter(Boolean).join(" ")}
      role="status"
      aria-label={`Risk ${RISK_LABEL[level]}`}
    >
      <span className="g" aria-hidden="true">
        {RISK_GLYPH[level]}
      </span>
      {RISK_LABEL[level]}
    </span>
  );
}
