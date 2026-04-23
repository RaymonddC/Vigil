/**
 * FE6 — Provider & FHIR status panel.
 *
 * READ-ONLY. All config is env-var controlled server-side (PROJECT_BRIEF §56).
 * No mutation controls, no swap UI.
 *
 * Fetches from GET /api/status via getStatus() (RSC, direct to FastAPI).
 */

import type { Metadata } from "next";
import { getStatus, type StatusResponse } from "@/lib/api";

export const metadata: Metadata = {
  title: "System Status — Vigil",
};

// Force dynamic rendering — fetches from backend at request time, never at
// build time. Otherwise Next.js tries to pre-render statically and blocks
// the docker build with a 60s fetch timeout when the backend isn't up yet.
export const dynamic = "force-dynamic";

// ─── Page ─────────────────────────────────────────────────────────────────────

export default async function SettingsPage() {
  let status: StatusResponse | null = null;
  let fetchError: string | null = null;

  try {
    status = await getStatus();
  } catch (err) {
    fetchError =
      err instanceof Error ? err.message : "Backend unreachable";
  }

  // Formatted timestamp for display
  const updatedAt = status?.ts
    ? formatTs(status.ts)
    : null;

  return (
    <div className="p-6 space-y-6 max-w-2xl">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold font-[family-name:var(--font-geist-sans)] text-slate-900 dark:text-slate-50 tracking-tight">
            System Status
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Read-only — configuration is controlled server-side via environment variables.
          </p>
        </div>
        {updatedAt && (
          <time
            dateTime={status!.ts}
            className="shrink-0 text-xs text-slate-400 dark:text-slate-500 mt-1 tabular-nums font-[family-name:var(--font-geist-mono)]"
          >
            Updated {updatedAt}
          </time>
        )}
      </div>

      {/* Backend unreachable banner */}
      {fetchError && (
        <div
          role="alert"
          className="flex items-start gap-3 px-4 py-3 rounded-lg border border-[#FCA5A5] bg-[#FEF2F2] text-[#991B1B] text-sm"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="shrink-0 mt-0.5"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span>
            <strong className="font-semibold">Backend unreachable</strong> — {fetchError}.
            Start the FastAPI server at{" "}
            <code className="font-[family-name:var(--font-geist-mono)] text-xs">
              http://localhost:8000
            </code>{" "}
            and refresh.
          </span>
        </div>
      )}

      {/* Status cards */}
      <div className="space-y-4">
        {/* LLM Provider */}
        <StatusCard
          title="LLM Provider"
          healthIndicator={status ? "active" : "error"}
          healthLabel={status ? "Configured" : "Unknown"}
          items={[
            {
              label: "Provider",
              value: status?.llm_provider ?? "—",
              mono: true,
            },
            {
              label: "Switched via",
              value: "LLM_PROVIDER env var",
              mono: true,
              dim: true,
            },
          ]}
        />

        {/* FHIR Server */}
        <StatusCard
          title="FHIR Server"
          healthIndicator={
            status == null
              ? "unknown"
              : status.fhir_healthy
              ? "active"
              : "error"
          }
          healthLabel={
            status == null
              ? "Unknown"
              : status.fhir_healthy
              ? "Connected"
              : "Error"
          }
          items={[
            {
              label: "Base URL",
              value: status?.fhir_url ?? "—",
              mono: true,
            },
            { label: "Version", value: "R4", mono: false },
            ...(status?.fhir_error
              ? [
                  {
                    label: "Error",
                    value: status.fhir_error,
                    mono: true,
                    error: true,
                  },
                ]
              : []),
          ]}
        />

        {/* A2A Agent */}
        <StatusCard
          title="A2A Agent"
          healthIndicator={
            status == null
              ? "unknown"
              : status.agent_healthy
              ? "active"
              : "error"
          }
          healthLabel={
            status == null
              ? "Unknown"
              : status.agent_healthy
              ? "Running"
              : "Stopped"
          }
          items={[
            {
              label: "Agent URL",
              value: status?.a2a_agent_url ?? "—",
              mono: true,
            },
            {
              label: "Poll interval",
              value: "POLL_INTERVAL_SEC (default 900 s)",
              mono: true,
              dim: true,
            },
          ]}
        />

        {/* Token usage (optional — only shown when backend reports it) */}
        {status?.token_usage &&
          Object.keys(status.token_usage).length > 0 && (
            <StatusCard
              title="Token Usage (session)"
              healthIndicator="info"
              healthLabel="Reported"
              items={Object.entries(status.token_usage).map(([k, v]) => ({
                label: k,
                value: v.toLocaleString(),
                mono: true,
              }))}
            />
          )}

        {/* SHARP headers */}
        <StatusCard
          title="Prompt Opinion SHARP Headers"
          healthIndicator="info"
          healthLabel="Runtime"
          items={[
            {
              label: "x-fhir-server-url",
              value: "Set by PO runtime",
              mono: true,
              dim: true,
            },
            {
              label: "x-fhir-access-token",
              value: "Set by PO runtime (redacted in logs)",
              mono: true,
              dim: true,
            },
            {
              label: "x-patient-id",
              value: "Set by PO runtime",
              mono: true,
              dim: true,
            },
          ]}
        />
      </div>
    </div>
  );
}

// ─── StatusCard ───────────────────────────────────────────────────────────────

type HealthState = "active" | "error" | "unknown" | "info";

type StatusItem = {
  label: string;
  value: string;
  mono?: boolean;
  dim?: boolean;
  error?: boolean;
};

function StatusCard({
  title,
  healthIndicator,
  healthLabel,
  items,
}: {
  title: string;
  healthIndicator: HealthState;
  healthLabel: string;
  items: StatusItem[];
}) {
  const dotClass: Record<HealthState, string> = {
    active:  "bg-[#059669]",
    error:   "bg-[#DC2626]",
    unknown: "bg-slate-300 dark:bg-slate-600",
    info:    "bg-[#2563EB]",
  };

  return (
    <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm p-5">
      <div className="flex items-center gap-2 mb-4">
        <h2 className="text-sm font-semibold font-[family-name:var(--font-geist-sans)] text-slate-800 dark:text-slate-200">
          {title}
        </h2>
        <span className="flex items-center gap-1.5 ml-auto" aria-label={`Status: ${healthLabel}`}>
          <span
            className={`w-2 h-2 rounded-full ${dotClass[healthIndicator]}`}
            aria-hidden="true"
          />
          <span className="text-xs text-slate-400 dark:text-slate-500">
            {healthLabel}
          </span>
        </span>
      </div>

      <dl className="space-y-2">
        {items.map(({ label, value, mono, dim, error: isError }) => (
          <div key={label} className="flex items-start gap-4 text-sm">
            <dt className="w-44 shrink-0 text-slate-500 dark:text-slate-400 text-xs pt-0.5">
              {label}
            </dt>
            <dd
              className={[
                "text-xs break-all leading-relaxed",
                mono ? "font-[family-name:var(--font-geist-mono)]" : "",
                isError
                  ? "text-[#991B1B] dark:text-[#FCA5A5]"
                  : dim
                  ? "text-slate-400 dark:text-slate-500 italic"
                  : "text-slate-700 dark:text-slate-300",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Format ISO timestamp as "HH:MM:SS" for the "Updated" label. */
function formatTs(iso: string): string {
  try {
    // Parse only the time portion to avoid hydration mismatches —
    // the server renders this and the string is stable.
    return iso.substring(11, 19);
  } catch {
    return iso;
  }
}
