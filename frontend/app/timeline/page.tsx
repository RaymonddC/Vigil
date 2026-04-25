"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { fetchEvents, triggerAgentTick, type VigilEvent } from "@/lib/api";

// ─── State derivation ────────────────────────────────────────────────────

const TOOL_STATE: Record<string, string> = {
  screen_vital_thresholds: "SCREENING",
  score_deterioration_risk: "RISK_SCORING",
  flag_sepsis_onset: "SEPSIS_CHECK",
  generate_escalation_note: "ESCALATING",
};

const EVENT_STATE: Record<string, string> = {
  agent_tick: "POLLING",
  llm_call: "LLM_CALL",
  alert_approved: "AWAITING_REVIEW",
};

function deriveState(event: VigilEvent): string {
  if (event.event_type === "tool_call") {
    return (
      TOOL_STATE[event.payload.tool as string] ?? event.event_type.toUpperCase()
    );
  }
  return EVENT_STATE[event.event_type] ?? event.event_type.toUpperCase();
}

function deriveDetail(event: VigilEvent): string {
  const p = event.payload as Record<string, unknown>;
  switch (event.event_type) {
    case "tool_call": {
      const status = p.status as string | undefined;
      const tool = p.tool as string | undefined;
      return tool ? `${tool}${status ? ` — ${status}` : ""}` : "tool call";
    }
    case "llm_call": {
      const provider = p.provider as string | undefined;
      const model = p.model as string | undefined;
      const prompt = p.prompt_tokens as number | undefined;
      const completion = p.completion_tokens as number | undefined;
      return `${provider ?? ""}/${model ?? ""}${
        prompt != null && completion != null
          ? ` — ${prompt}+${completion} tok`
          : ""
      }`;
    }
    case "agent_tick": {
      const ok = p.success as boolean | undefined;
      return ok ? "polling cycle triggered" : `tick failed: ${p.detail ?? ""}`;
    }
    case "alert_approved": {
      return `alert ${p.alert_id ?? ""} approved`;
    }
    default:
      return JSON.stringify(event.payload).slice(0, 80);
  }
}

function fmtTimeOnly(isoTs: string): string {
  try {
    const d = new Date(isoTs);
    return `${String(d.getHours()).padStart(2, "0")}:${String(
      d.getMinutes()
    ).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
  } catch {
    return isoTs.slice(11, 19);
  }
}

function durationMs(event: VigilEvent): number | null {
  const p = event.payload as Record<string, unknown>;
  const v = p.duration_ms;
  if (typeof v === "number" && Number.isFinite(v)) return v;
  return null;
}

// ─── Page ────────────────────────────────────────────────────────────────

export default function TimelinePage() {
  const router = useRouter();
  const [events, setEvents] = React.useState<VigilEvent[]>([]);
  const [tickPending, setTickPending] = React.useState(false);
  const [offline, setOffline] = React.useState(false);
  const lastTs = React.useRef<string | undefined>(undefined);

  const poll = React.useCallback(async () => {
    try {
      const data = await fetchEvents(lastTs.current);
      setOffline(false);
      if (Array.isArray(data.events) && data.events.length > 0) {
        setEvents((prev) => {
          // Backend returns oldest-first; we display newest-first.
          const incoming = [...data.events].reverse();
          return [...incoming, ...prev].slice(0, 200);
        });
      }
      if (data.server_ts) lastTs.current = data.server_ts;
    } catch {
      setOffline(true);
    }
  }, []);

  React.useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    poll();
    const id = setInterval(poll, 2000);
    return () => clearInterval(id);
  }, [poll]);

  async function handleTick() {
    if (tickPending) return;
    setTickPending(true);
    try {
      const res = await triggerAgentTick();
      if (res.triggered) {
        toast.success("Agent cycle triggered", {
          description: "Polling HAPI · running MCP tools · scoring risk",
          duration: 3500,
        });
        router.refresh();
      } else {
        toast.error("Tick failed", {
          description: res.detail ?? "Agent returned an error",
        });
      }
    } catch {
      toast.error("Agent unreachable", {
        description: "FastAPI proxy is not responding — check :8000",
      });
    } finally {
      setTickPending(false);
      poll();
    }
  }

  // Newest event is "active" — shown with a pulsing ink dot. Older are "done".
  const rendered = events.map((ev, idx) => ({
    ev,
    state: deriveState(ev),
    detail: deriveDetail(ev),
    ms: durationMs(ev),
    active: idx === 0,
    done: idx > 0,
  }));

  return (
    <div className="page">
      <div className="page__hd">
        <h1 className="page__title">Agent timeline</h1>
        <span className="page__sub">
          7-state machine · polling every 2 s
        </span>
        <span style={{ marginLeft: "auto" }}>
          <button
            type="button"
            className="btn btn--primary"
            onClick={handleTick}
            disabled={tickPending}
            aria-busy={tickPending}
          >
            {tickPending ? "Ticking…" : "Tick now"}
          </button>
        </span>
      </div>

      <div className="trace">
        <div className="trace__hd">
          <span className="live">
            <span className="dot" />
            {offline ? "OFFLINE" : "LIVE"}
          </span>
          <span className="s">
            {offline ? "backend unreachable" : "next poll in ≤ 2 s"}
          </span>
        </div>

        {rendered.length === 0 && (
          <div className="empty">
            {offline
              ? "Cannot reach backend. Start FastAPI on :8000."
              : "Awaiting events. Tap Tick now to trigger the agent."}
          </div>
        )}

        {rendered.map(({ ev, state, detail, ms, active, done }) => (
          <div
            key={ev.id}
            className={`evt${done ? " done" : ""}${active ? " active" : ""}`}
          >
            <span className="t">{fmtTimeOnly(ev.ts)}</span>
            <span className="dot" aria-hidden="true" />
            <span>
              <span className="lbl">{state}</span>
              <span className="detail">{detail}</span>
            </span>
            <span className="ms">{ms != null ? `${ms} ms` : "—"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
