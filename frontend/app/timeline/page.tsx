export const metadata = {
  title: "Timeline — Vigil",
};

const PLACEHOLDER_EVENTS = [
  { id: "e1", time: "10:32", state: "AWAITING_REVIEW", patient: "PT-007", detail: "SBAR draft generated — CRITICAL sepsis onset detected" },
  { id: "e2", time: "10:31", state: "ESCALATING",      patient: "PT-007", detail: "Escalation note generation triggered via LLM" },
  { id: "e3", time: "10:30", state: "SEPSIS_CHECK",    patient: "PT-007", detail: "CDC ASE criteria met — lactate ≥ 4, WBC ≥ 18" },
  { id: "e4", time: "10:29", state: "RISK_SCORING",    patient: "PT-007", detail: "qSOFA = 2, risk_band = high" },
  { id: "e5", time: "10:28", state: "SCREENING",       patient: "PT-007", detail: "MEWT thresholds breached — HR 128, MAP 58, RR 26" },
  { id: "e6", time: "10:27", state: "POLLING",         patient: "PT-007", detail: "Vitals polled from FHIR — 6 observations retrieved" },
  { id: "e7", time: "10:15", state: "POLLING",         patient: "PT-001", detail: "Vitals polled — all within normal limits" },
];

const STATE_COLORS: Record<string, string> = {
  IDLE:             "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
  POLLING:          "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  SCREENING:        "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  RISK_SCORING:     "bg-orange-50 text-orange-700 dark:bg-orange-950 dark:text-orange-300",
  SEPSIS_CHECK:     "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300",
  ESCALATING:       "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  AWAITING_REVIEW:  "bg-purple-50 text-purple-700 dark:bg-purple-950 dark:text-purple-300",
};

export default function TimelinePage() {
  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold font-[family-name:var(--font-geist-sans)] text-slate-900 dark:text-slate-50 tracking-tight">
            A2A Agent Timeline
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Real-time state machine trace from the Postop Sentinel agent
          </p>
        </div>
        <button
          type="button"
          className="px-4 py-2 text-sm font-medium bg-[#0B5FFF] text-white rounded-md hover:bg-[#0950DB] transition-colors"
          aria-label="Trigger immediate agent polling cycle"
        >
          Tick Now
        </button>
      </div>

      {/* Event feed */}
      <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        <div className="border-b border-slate-200 dark:border-slate-800 px-4 py-3 bg-slate-50 dark:bg-slate-950">
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Polling every 2s · Connect backend in Phase 3 (FE3/B9)
          </p>
        </div>
        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
          {PLACEHOLDER_EVENTS.map((ev) => (
            <li key={ev.id} className="flex items-start gap-4 px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
              <time
                dateTime={ev.time}
                className="font-[family-name:var(--font-geist-mono)] text-xs text-slate-400 dark:text-slate-500 tabular-nums shrink-0 mt-0.5"
              >
                {ev.time}
              </time>
              <span className={[
                "shrink-0 px-2 py-0.5 rounded text-xs font-medium font-[family-name:var(--font-geist-mono)]",
                STATE_COLORS[ev.state] ?? "bg-slate-100 text-slate-600",
              ].join(" ")}>
                {ev.state}
              </span>
              <div className="flex-1 min-w-0">
                <span className="text-xs font-medium text-slate-500 dark:text-slate-400 font-[family-name:var(--font-geist-mono)]">
                  {ev.patient}
                </span>
                <span className="mx-2 text-slate-300 dark:text-slate-600">·</span>
                <span className="text-sm text-slate-700 dark:text-slate-300">{ev.detail}</span>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <p className="text-xs text-slate-400 dark:text-slate-600 text-center">
        Placeholder data — wire to <code className="font-[family-name:var(--font-geist-mono)]">GET /api/events/tail</code> in Phase 3
      </p>
    </div>
  );
}
