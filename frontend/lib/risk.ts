export type RiskLevel = 'normal' | 'low' | 'medium' | 'high' | 'critical';

const RISK_ORDER: Record<RiskLevel, number> = {
  normal: 0,
  low: 1,
  medium: 2,
  high: 3,
  critical: 4,
};

export function compareRisk(a: RiskLevel, b: RiskLevel): number {
  return RISK_ORDER[a] - RISK_ORDER[b];
}

export function sortByRiskDesc<T>(items: T[], getRisk: (item: T) => RiskLevel): T[] {
  return [...items].sort((a, b) => compareRisk(getRisk(b), getRisk(a)));
}

export function isHighOrAbove(level: RiskLevel): boolean {
  return RISK_ORDER[level] >= RISK_ORDER['high'];
}

export function riskLabel(level: RiskLevel): string {
  const labels: Record<RiskLevel, string> = {
    normal: 'Normal',
    low: 'Low',
    medium: 'Medium',
    high: 'High',
    critical: 'CRITICAL',
  };
  return labels[level];
}

export function riskFromString(s: string): RiskLevel {
  const normalized = s.toLowerCase() as RiskLevel;
  if (normalized in RISK_ORDER) return normalized;
  return 'normal';
}
