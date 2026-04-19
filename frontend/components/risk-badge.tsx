import { CheckCircle2, Info, AlertCircle, AlertTriangle, Siren } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RiskLevel } from "@/lib/risk";

export interface RiskBadgeProps {
  level: RiskLevel;
  size?: "sm" | "md" | "lg";
  className?: string;
}

type RiskConfig = {
  label: string;
  Icon: React.ElementType;
  bg: string;
  fg: string;
  ring: string;
  darkBg: string;
  darkFg: string;
};

const RISK: Record<RiskLevel, RiskConfig> = {
  normal: {
    label: "Normal",
    Icon: CheckCircle2,
    bg: "bg-[#ECFDF5]",
    fg: "text-[#065F46]",
    ring: "",
    darkBg: "dark:bg-emerald-950/40",
    darkFg: "dark:text-emerald-300",
  },
  low: {
    label: "Low",
    Icon: Info,
    bg: "bg-[#EFF6FF]",
    fg: "text-[#1E40AF]",
    ring: "",
    darkBg: "dark:bg-blue-950/40",
    darkFg: "dark:text-blue-300",
  },
  medium: {
    label: "Medium",
    Icon: AlertCircle,
    bg: "bg-[#FFFBEB]",
    fg: "text-[#92400E]",
    ring: "",
    darkBg: "dark:bg-amber-950/40",
    darkFg: "dark:text-amber-300",
  },
  high: {
    label: "High",
    Icon: AlertTriangle,
    bg: "bg-[#FFF7ED]",
    fg: "text-[#9A3412]",
    ring: "",
    darkBg: "dark:bg-orange-950/40",
    darkFg: "dark:text-orange-300",
  },
  critical: {
    label: "CRITICAL",
    Icon: Siren,
    bg: "bg-[#FEF2F2]",
    fg: "text-[#991B1B]",
    ring: "ring-2 ring-[#991B1B]/40",
    darkBg: "dark:bg-red-950/40",
    darkFg: "dark:text-red-300",
  },
};

const SIZE: Record<NonNullable<RiskBadgeProps["size"]>, { padding: string; text: string; iconSize: number; gap: string }> = {
  sm: { padding: "px-2 py-0.5",   text: "text-xs", iconSize: 10, gap: "gap-1"   },
  md: { padding: "px-2.5 py-1",   text: "text-xs", iconSize: 12, gap: "gap-1.5" },
  lg: { padding: "px-3 py-1.5",   text: "text-sm", iconSize: 14, gap: "gap-2"   },
};

/**
 * RiskBadge — renders all 5 risk levels with icon + label + (critical) ring.
 * Color is never the only signal: icon + text label + ring on critical.
 * WCAG 2.2 AA: all bg/fg pairs ≥ 4.5:1 contrast.
 */
export function RiskBadge({ level, size = "md", className }: RiskBadgeProps) {
  const { label, Icon, bg, fg, ring, darkBg, darkFg } = RISK[level];
  const { padding, text, iconSize, gap } = SIZE[size];

  return (
    <span
      className={cn(
        "inline-flex items-center font-medium rounded-md",
        padding,
        text,
        gap,
        bg,
        fg,
        darkBg,
        darkFg,
        ring,
        className,
      )}
    >
      <Icon size={iconSize} aria-hidden="true" />
      {label}
    </span>
  );
}
