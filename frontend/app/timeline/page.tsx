'use client';

/**
 * FE3 — A2A Agent Timeline
 *
 * Polls GET /api/events/tail?since=<ts> every 2 s.
 * Renders VigilEvents as color-coded state-machine trace rows.
 * Filterable by patient. "Tick Now" triggers POST /api/agent/tick.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
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
// Color tokens by state
// ---------------------------------------------------------------------------

const STATE_COLORS: Record<string, string> = {
  POLLING:         'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
  SCREENING:       'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300',
  RISK_SCORING:    'bg-orange-50 text-orange-700 dark:bg-orange-950 dark:text-orange-300',
  SEPSIS_CHECK:    'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300',
  ESCALATING:      'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  AWAITING_REVIEW: 'bg-purple-50 text-purple-700 dark:bg-purple-950 dark:text-purple-300',
  LLM_CALL:        'bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300',
};

function stateColor(state: string): string {
  return (
    STATE_COLORS[state] ??
    'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
  );
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

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function TimelinePage() {
  const [events, setEvents] = useState<VigilEvent[]>([]);
  const [patientFilter, setPatientFilter] = useState<string>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [tickPending, setTickPending] = useState(false);
  const [tickMessage, setTickMessage] = useState<string | null>(null);
  const [backendOffline, setBackendOffline] = useState(false);

  const lastTs = useRef<string | undefined>(undefined);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

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
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [poll]);

  const handleTickNow = async () => {
    setTickPending(true);
    setTickMessage(null);
    try {
      const res = await triggerAgentTick();
      setTickMessage(res.triggered ? 'Cycle triggered' : `Failed: ${res.detail}`);
    } catch {
      setTickMessage('Agent unreachable');
    } finally {
      setTickPending(false);
      poll(); // immediate refresh
    }
  };

  // Unique patient IDs from all events
  const patients = [
    ...new Set(events.map((e) => e.patient_id).filter((p): p is string => !!p)),
  ].sort();

  const visible =
    patientFilter === 'all'
      ? events
      : events.filter((e) => e.patient_id === patientFilter);

  return (
    <div className="p-6 space-y-6">
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-[family-name:var(--font-geist-sans)] text-slate-900 dark:text-slate-50 tracking-tight">
            A2A Agent Timeline
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Real-time state machine trace from the Postop Sentinel agent
          </p>
        </div>

        <div className="flex items-center gap-3">
          {tickMessage && (
            <span className="text-xs text-slate-500 dark:text-slate-400">
              {tickMessage}
            </span>
          )}
          <button
            type="button"
            onClick={handleTickNow}
            disabled={tickPending}
            className="px-4 py-2 text-sm font-medium bg-[#0B5FFF] text-white rounded-md hover:bg-[#0950DB] transition-colors disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px]"
            aria-label="Trigger immediate agent polling cycle"
          >
            {tickPending ? 'Triggering…' : 'Tick Now'}
          </button>
        </div>
      </div>

      {/* ── Status + Filter row ── */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-slate-500 dark:text-slate-400 shrink-0">
          Patient:
        </span>

        <button
          type="button"
          onClick={() => setPatientFilter('all')}
          className={[
            'px-2.5 py-1 text-xs rounded-md font-medium transition-colors min-h-[32px]',
            patientFilter === 'all'
              ? 'bg-[#0B5FFF] text-white'
              : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700',
          ].join(' ')}
        >
          All
        </button>

        {patients.map((pid) => (
          <button
            key={pid}
            type="button"
            onClick={() => setPatientFilter(pid)}
            className={[
              'px-2.5 py-1 text-xs rounded-md font-[family-name:var(--font-geist-mono)] font-medium transition-colors min-h-[32px]',
              patientFilter === pid
                ? 'bg-[#0B5FFF] text-white'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700',
            ].join(' ')}
          >
            {pid}
          </button>
        ))}

        <span className="ml-auto text-xs text-slate-400 dark:text-slate-600 shrink-0">
          {backendOffline ? (
            <span className="text-amber-600 dark:text-amber-400">backend offline</span>
          ) : (
            <>{visible.length} events · polling 2 s</>
          )}
        </span>
      </div>

      {/* ── Event feed ── */}
      <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        {visible.length === 0 ? (
          <div className="px-6 py-10 text-center">
            <p className="text-sm text-slate-400 dark:text-slate-600">
              {backendOffline
                ? 'Cannot reach backend — start FastAPI on :8000'
                : 'No events yet — click Tick Now to trigger the agent'}
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {visible.map((ev) => {
              const state = deriveState(ev);
              const detail = deriveDetail(ev);
              const expanded = expandedId === ev.id;

              return (
                <li key={ev.id}>
                  <button
                    type="button"
                    onClick={() => setExpandedId(expanded ? null : ev.id)}
                    aria-expanded={expanded}
                    className="w-full text-left flex items-start gap-4 px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
                  >
                    <time
                      dateTime={ev.ts}
                      className="font-[family-name:var(--font-geist-mono)] text-xs text-slate-400 dark:text-slate-500 tabular-nums shrink-0 mt-0.5 w-20"
                    >
                      {fmtTime(ev.ts)}
                    </time>

                    <span
                      className={[
                        'shrink-0 px-2 py-0.5 rounded text-xs font-medium font-[family-name:var(--font-geist-mono)] w-36 text-center',
                        stateColor(state),
                      ].join(' ')}
                    >
                      {state}
                    </span>

                    <div className="flex-1 min-w-0 text-left">
                      {ev.patient_id && (
                        <>
                          <span className="text-xs font-medium text-slate-500 dark:text-slate-400 font-[family-name:var(--font-geist-mono)]">
                            {ev.patient_id}
                          </span>
                          <span className="mx-2 text-slate-300 dark:text-slate-700">·</span>
                        </>
                      )}
                      <span className="text-sm text-slate-700 dark:text-slate-300">
                        {detail}
                      </span>
                    </div>

                    <span className="text-[10px] text-slate-300 dark:text-slate-700 shrink-0 mt-1">
                      {expanded ? '▲' : '▼'}
                    </span>
                  </button>

                  {expanded && (
                    <div className="px-4 pb-3 bg-slate-50 dark:bg-slate-950 border-t border-slate-100 dark:border-slate-800">
                      <p className="text-[10px] text-slate-400 dark:text-slate-600 uppercase tracking-wider mb-1.5 pt-2">
                        Tool-call payload
                      </p>
                      <pre className="text-xs bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded p-3 overflow-x-auto text-slate-700 dark:text-slate-300 font-[family-name:var(--font-geist-mono)]">
                        {JSON.stringify(ev.payload, null, 2)}
                      </pre>
                      <p className="text-[10px] text-slate-400 dark:text-slate-600 mt-1.5">
                        request_id: {ev.request_id} · event_id: {ev.id}
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
