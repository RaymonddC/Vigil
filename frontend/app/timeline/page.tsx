'use client';

/**
 * FE3 — A2A Agent Timeline
 *
 * Polls GET /api/events/tail?since=<ts> every 2 s.
 * Renders VigilEvents as color-coded state-machine trace rows.
 * Filterable by patient. "Tick Now" triggers POST /api/agent/tick.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import {
  Zap,
  Search,
  Activity,
  AlertTriangle,
  Send,
  Brain,
  ChevronDown,
  ChevronUp,
  Radio,
  Play,
  WifiOff,
  Terminal,
} from 'lucide-react';
import { fetchEvents, triggerAgentTick, type VigilEvent } from '@/lib/api';

// ---------------------------------------------------------------------------
// State derivation from VigilEvent
// ---------------------------------------------------------------------------

const TOOL_STATE: Record<string, string> = {
  screen_vital_thresholds:  'SCREENING',
  score_deterioration_risk: 'RISK_SCORING',
  flag_sepsis_onset:        'SEPSIS_CHECK',
  generate_escalation_note: 'ESCALATING',
};

const EVENT_STATE: Record<string, string> = {
  agent_tick:     'POLLING',
  llm_call:       'LLM_CALL',
  alert_approved: 'AWAITING_REVIEW',
};

function deriveState(event: VigilEvent): string {
  if (event.event_type === 'tool_call') {
    return TOOL_STATE[event.payload.tool as string] ?? event.event_type.toUpperCase();
  }
  return EVENT_STATE[event.event_type] ?? event.event_type.toUpperCase();
}

function deriveDetail(event: VigilEvent): string {
  const p = event.payload as Record<string, unknown>;
  switch (event.event_type) {
    case 'tool_call': {
      const status = p.status as string;
      const duration = p.duration_ms as number;
      const tool = p.tool as string;
      return `${tool} — ${duration}ms (${status})`;
    }
    case 'llm_call': {
      const provider = p.provider as string;
      const model = p.model as string;
      const prompt = p.prompt_tokens as number;
      const completion = p.completion_tokens as number;
      return `${provider}/${model} — ${prompt} prompt + ${completion} completion tokens`;
    }
    case 'agent_tick': {
      const ok = p.success as boolean;
      return ok ? 'Agent polling cycle triggered' : `Tick failed: ${p.detail as string}`;
    }
    case 'alert_approved': {
      return `Alert ${p.alert_id as string} approved — comm ${p.comm_id as string}`;
    }
    default:
      return JSON.stringify(event.payload).slice(0, 120);
  }
}

// ---------------------------------------------------------------------------
// Visual tokens by state (Clinical Slate + Medical Blue)
// ---------------------------------------------------------------------------

type StateTone = {
  chip: string;      // badge background + text
  accent: string;    // left accent bar color
  Icon: typeof Zap;  // lucide icon component
  iconTint: string;  // icon color class
};

const STATE_TONE: Record<string, StateTone> = {
  POLLING: {
    chip: 'bg-[#EFF5FF] text-[#0B5FFF] dark:bg-blue-950 dark:text-blue-300',
    accent: 'bg-[#0B5FFF]',
    Icon: Radio,
    iconTint: 'text-[#0B5FFF]',
  },
  SCREENING: {
    chip: 'bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
    accent: 'bg-amber-500',
    Icon: Search,
    iconTint: 'text-amber-600',
  },
  RISK_SCORING: {
    chip: 'bg-orange-50 text-orange-800 dark:bg-orange-950 dark:text-orange-300',
    accent: 'bg-orange-500',
    Icon: Activity,
    iconTint: 'text-orange-600',
  },
  SEPSIS_CHECK: {
    chip: 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300',
    accent: 'bg-red-600',
    Icon: AlertTriangle,
    iconTint: 'text-red-600',
  },
  ESCALATING: {
    chip: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    accent: 'bg-[#991B1B]',
    Icon: Send,
    iconTint: 'text-[#991B1B]',
  },
  AWAITING_REVIEW: {
    chip: 'bg-purple-50 text-purple-800 dark:bg-purple-950 dark:text-purple-300',
    accent: 'bg-purple-600',
    Icon: Send,
    iconTint: 'text-purple-600',
  },
  LLM_CALL: {
    chip: 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
    accent: 'bg-emerald-500',
    Icon: Brain,
    iconTint: 'text-emerald-600',
  },
};

const FALLBACK_TONE: StateTone = {
  chip: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
  accent: 'bg-slate-400',
  Icon: Zap,
  iconTint: 'text-slate-400',
};

function stateTone(state: string): StateTone {
  return STATE_TONE[state] ?? FALLBACK_TONE;
}

// ---------------------------------------------------------------------------
// Time formatting (client-only — no SSR, so no hydration mismatch)
// ---------------------------------------------------------------------------

function fmtTime(isoTs: string): string {
  try {
    return new Date(isoTs).toLocaleTimeString('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  } catch {
    return isoTs.slice(11, 19) || isoTs;
  }
}

function fmtRelative(isoTs: string, nowMs: number): string {
  try {
    const diffSec = Math.max(0, Math.floor((nowMs - new Date(isoTs).getTime()) / 1000));
    if (diffSec < 5) return 'just now';
    if (diffSec < 60) return `${diffSec}s ago`;
    const m = Math.floor(diffSec / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    return `${h}h ago`;
  } catch {
    return '';
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function TimelinePage() {
  const router = useRouter();
  const [events, setEvents] = useState<VigilEvent[]>([]);
  const [patientFilter, setPatientFilter] = useState<string>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [tickPending, setTickPending] = useState(false);
  const [backendOffline, setBackendOffline] = useState(false);
  const [nowMs, setNowMs] = useState<number>(() => Date.now());

  const lastTs = useRef<string | undefined>(undefined);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const clockRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async () => {
    try {
      const data = await fetchEvents(lastTs.current);
      setBackendOffline(false);
      if (Array.isArray(data.events) && data.events.length > 0) {
        setEvents((prev) => {
          // Incoming batch is chronological (oldest first) — reverse for newest-first display
          const incoming = Array.from(data.events).reverse();
          return [...incoming, ...prev].slice(0, 500);
        });
      }
      // Always update cursor so subsequent polls only fetch new events
      if (data.server_ts) lastTs.current = data.server_ts;
    } catch {
      setBackendOffline(true);
    }
  }, []);

  useEffect(() => {
    poll();
    intervalRef.current = setInterval(poll, 2000);
    clockRef.current = setInterval(() => setNowMs(Date.now()), 10_000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (clockRef.current) clearInterval(clockRef.current);
    };
  }, [poll]);

  const handleTickNow = async () => {
    setTickPending(true);
    try {
      const res = await triggerAgentTick();
      if (res.triggered) {
        toast.success('Agent cycle triggered', {
          description: 'Polling HAPI · running MCP tools · scoring risk',
          duration: 3500,
        });
        // Bust the Next.js router cache so /patients RSC re-fetches fresh
        // risk bands + alert counts on next navigation without a hard reload.
        router.refresh();
      } else {
        toast.error('Tick failed', {
          description: res.detail ?? 'Agent returned an error',
        });
      }
    } catch {
      toast.error('Agent unreachable', {
        description: 'FastAPI proxy is not responding — check server on :8000',
      });
    } finally {
      setTickPending(false);
      poll(); // immediate timeline refresh
    }
  };

  // Unique patient IDs from all events + per-patient counts
  const patientCounts = useMemo(() => {
    const map = new Map<string, number>();
    for (const e of events) {
      if (e.patient_id) map.set(e.patient_id, (map.get(e.patient_id) ?? 0) + 1);
    }
    return map;
  }, [events]);

  const patients = useMemo(
    () => Array.from(patientCounts.keys()).sort(),
    [patientCounts],
  );

  const visible =
    patientFilter === 'all'
      ? events
      : events.filter((e) => e.patient_id === patientFilter);

  return (
    <div className="p-6 space-y-6">
      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold font-[family-name:var(--font-geist-sans)] text-slate-900 dark:text-slate-50 tracking-tight">
            A2A Agent Timeline
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Real-time trace from the Postop Sentinel agent · MCP tool calls · LLM reasoning
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Live / offline pill */}
          <div
            className={[
              'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium',
              backendOffline
                ? 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300'
                : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300',
            ].join(' ')}
            aria-live="polite"
          >
            {backendOffline ? (
              <>
                <WifiOff size={11} aria-hidden="true" />
                <span>Offline</span>
              </>
            ) : (
              <>
                <span className="relative inline-flex w-2 h-2" aria-hidden="true">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                </span>
                <span>Live · polling 2s</span>
              </>
            )}
          </div>

          {/* Tick Now button — primary CTA, visually weighty */}
          <button
            type="button"
            onClick={handleTickNow}
            disabled={tickPending}
            className={[
              'inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold rounded-md min-h-[44px]',
              'bg-[#0B5FFF] text-white shadow-sm shadow-[#0B5FFF]/20',
              'hover:bg-[#0950DB] hover:shadow-md hover:shadow-[#0B5FFF]/25 transition-all',
              'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF]',
              'disabled:opacity-60 disabled:cursor-not-allowed disabled:shadow-none',
            ].join(' ')}
            aria-label="Trigger immediate agent polling cycle"
          >
            {tickPending ? (
              <Loader />
            ) : (
              <Play size={14} strokeWidth={2.5} fill="currentColor" aria-hidden="true" />
            )}
            <span>{tickPending ? 'Triggering…' : 'Tick Now'}</span>
          </button>
        </div>
      </div>

      {/* ── Event feed card ── */}
      <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        {/* Card header — filter row */}
        <div className="flex items-center gap-2 flex-wrap px-4 py-3 border-b border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950/40">
          <span className="text-[10px] font-semibold tracking-wider uppercase text-slate-500 dark:text-slate-400 shrink-0 mr-1">
            Patient
          </span>

          <FilterPill
            active={patientFilter === 'all'}
            onClick={() => setPatientFilter('all')}
            label="All"
            count={events.length}
          />

          {patients.map((pid) => (
            <FilterPill
              key={pid}
              active={patientFilter === pid}
              onClick={() => setPatientFilter(pid)}
              label={pid}
              count={patientCounts.get(pid) ?? 0}
              mono
            />
          ))}

          <span className="ml-auto text-[11px] text-slate-400 dark:text-slate-500 font-[family-name:var(--font-geist-mono)] tabular-nums shrink-0">
            {visible.length} event{visible.length === 1 ? '' : 's'}
          </span>
        </div>

        {/* Event feed */}
        {visible.length === 0 ? (
          <div className="px-6 py-12 text-center space-y-3">
            <div className="mx-auto w-10 h-10 flex items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
              <Terminal size={18} className="text-slate-400" aria-hidden="true" />
            </div>
            <p className="text-sm font-medium text-slate-600 dark:text-slate-300">
              {backendOffline ? 'Backend unreachable' : 'Awaiting events'}
            </p>
            <p className="text-xs text-slate-400 dark:text-slate-500">
              {backendOffline
                ? 'Start FastAPI on :8000 to stream agent events'
                : 'Click Tick Now to trigger the agent and watch the trace'}
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800" aria-live="polite">
            {visible.map((ev) => {
              const state = deriveState(ev);
              const tone = stateTone(state);
              const detail = deriveDetail(ev);
              const expanded = expandedId === ev.id;
              const Icon = tone.Icon;

              return (
                <li key={ev.id} className="relative">
                  {/* Left accent rail — subtle, colored by state */}
                  <span
                    className={['absolute left-0 top-0 bottom-0 w-[2px]', tone.accent].join(' ')}
                    aria-hidden="true"
                  />

                  <button
                    type="button"
                    onClick={() => setExpandedId(expanded ? null : ev.id)}
                    aria-expanded={expanded}
                    className="w-full text-left flex items-start gap-3 px-4 py-3 pl-5 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#0B5FFF]"
                  >
                    {/* Time column — primary + relative */}
                    <div className="shrink-0 w-24 mt-0.5 space-y-0.5">
                      <time
                        dateTime={ev.ts}
                        className="block font-[family-name:var(--font-geist-mono)] text-[13px] font-medium text-slate-700 dark:text-slate-200 tabular-nums"
                      >
                        {fmtTime(ev.ts)}
                      </time>
                      <span className="block text-[10px] text-slate-400 dark:text-slate-600">
                        {fmtRelative(ev.ts, nowMs)}
                      </span>
                    </div>

                    {/* Icon + state chip */}
                    <div className="shrink-0 flex items-center gap-2 w-44 mt-0.5">
                      <Icon size={14} className={tone.iconTint} aria-hidden="true" />
                      <span
                        className={[
                          'px-2 py-0.5 rounded text-[11px] font-semibold font-[family-name:var(--font-geist-mono)] tracking-wide',
                          tone.chip,
                        ].join(' ')}
                      >
                        {state}
                      </span>
                    </div>

                    {/* Detail */}
                    <div className="flex-1 min-w-0 text-left mt-0.5">
                      {ev.patient_id && (
                        <>
                          <span className="text-xs font-semibold text-slate-600 dark:text-slate-300 font-[family-name:var(--font-geist-mono)]">
                            {ev.patient_id}
                          </span>
                          <span className="mx-2 text-slate-300 dark:text-slate-700">·</span>
                        </>
                      )}
                      <span className="text-sm text-slate-700 dark:text-slate-300">
                        {detail}
                      </span>
                    </div>

                    {/* Chevron */}
                    <span className="shrink-0 text-slate-400 dark:text-slate-600 mt-1" aria-hidden="true">
                      {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </span>
                  </button>

                  {expanded && (
                    <div className="px-5 pb-4 bg-slate-50 dark:bg-slate-950/60 border-t border-slate-100 dark:border-slate-800">
                      <div className="flex items-center gap-1.5 pt-3 pb-2">
                        <Terminal size={11} className="text-slate-400" aria-hidden="true" />
                        <p className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider font-semibold">
                          Payload
                        </p>
                      </div>
                      <pre className="text-[11.5px] leading-relaxed bg-slate-900 dark:bg-slate-950 text-slate-100 dark:text-slate-200 border border-slate-800 rounded-md p-3.5 overflow-x-auto font-[family-name:var(--font-geist-mono)] shadow-sm">
                        {JSON.stringify(ev.payload, null, 2)}
                      </pre>
                      <p className="text-[10px] text-slate-400 dark:text-slate-600 mt-2 font-[family-name:var(--font-geist-mono)] tabular-nums">
                        request_id <span className="text-slate-500 dark:text-slate-400">{ev.request_id}</span>
                        <span className="mx-2 text-slate-300 dark:text-slate-700">·</span>
                        event_id <span className="text-slate-500 dark:text-slate-400">{ev.id}</span>
                      </p>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Subcomponents
// ---------------------------------------------------------------------------

function FilterPill({
  active,
  onClick,
  label,
  count,
  mono = false,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  count: number;
  mono?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={[
        'inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md font-medium transition-colors min-h-[32px]',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0B5FFF]',
        mono ? 'font-[family-name:var(--font-geist-mono)]' : '',
        active
          ? 'bg-[#0B5FFF] text-white shadow-sm'
          : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700',
      ].join(' ')}
    >
      <span>{label}</span>
      <span
        className={[
          'px-1.5 rounded text-[10px] tabular-nums font-[family-name:var(--font-geist-mono)]',
          active ? 'bg-white/20 text-white' : 'bg-white dark:bg-slate-900 text-slate-500 dark:text-slate-400',
        ].join(' ')}
      >
        {count}
      </span>
    </button>
  );
}

function Loader() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      className="animate-spin"
      aria-hidden="true"
    >
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  );
}
