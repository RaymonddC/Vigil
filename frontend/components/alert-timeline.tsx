import Link from 'next/link';
import { RiskBadge } from '@/components/risk-badge';
import type { RiskLevel } from '@/lib/risk';

export interface AlertTimelineItem {
  id: string;
  timestamp: string;  // ISO
  level: RiskLevel;
  headline: string;
}

export interface AlertTimelineProps {
  patientId: string;
  items: AlertTimelineItem[];
}

export function AlertTimeline({ patientId, items }: AlertTimelineProps) {
  if (items.length === 0) {
    return (
      <p className="text-sm text-slate-400 dark:text-slate-500 italic">No alerts recorded.</p>
    );
  }

  return (
    <ul className="space-y-2" aria-label="Recent patient alerts">
      {items.slice(0, 5).map((item) => {
        const d = new Date(item.timestamp);
        const hh = String(d.getUTCHours()).padStart(2, '0');
        const mm = String(d.getUTCMinutes()).padStart(2, '0');
        const displayTime = `${hh}:${mm}`;

        return (
          <li key={item.id}>
            <Link
              href={`/patients/${patientId}/alerts/${item.id}`}
              className="flex items-center gap-2 rounded-md px-2 py-2 -mx-2 min-h-[44px] hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors group"
            >
              <time
                dateTime={item.timestamp}
                className="font-[family-name:var(--font-geist-mono)] text-xs text-slate-400 dark:text-slate-500 tabular-nums shrink-0 w-11"
              >
                {displayTime}
              </time>
              <RiskBadge level={item.level} size="sm" />
              <span className="text-xs text-slate-600 dark:text-slate-300 truncate min-w-0">
                {item.headline}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
