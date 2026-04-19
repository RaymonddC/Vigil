export const metadata = {
  title: "Settings — Vigil",
};

// Read-only status panel — no mutation controls per FRONTEND_SPEC §FE6
export default function SettingsPage() {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

  return (
    <div className="p-6 space-y-6 max-w-2xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold font-[family-name:var(--font-geist-sans)] text-slate-900 dark:text-slate-50 tracking-tight">
          System Status
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Read-only — configuration is set server-side via environment variables.
        </p>
      </div>

      {/* Status cards */}
      <div className="space-y-4">
        {/* LLM Provider */}
        <StatusCard
          title="LLM Provider"
          items={[
            { label: "Provider",    value: process.env.LLM_PROVIDER ?? "ollama" },
            { label: "Model",       value: "llama3.2" },
          ]}
          status="active"
        />

        {/* FHIR Connection */}
        <StatusCard
          title="FHIR Server"
          items={[
            { label: "Base URL",    value: "http://localhost:8080/fhir" },
            { label: "Version",     value: "R4" },
            { label: "Auth",        value: "None (dev mode)" },
          ]}
          status="active"
        />

        {/* Backend Proxy */}
        <StatusCard
          title="Backend API"
          items={[
            { label: "Base URL",    value: apiBase },
            { label: "Agent poll",  value: "POLL_INTERVAL_SEC = 900s (default)" },
          ]}
          status="active"
        />

        {/* Prompt Opinion */}
        <StatusCard
          title="Prompt Opinion SHARP Headers"
          items={[
            { label: "x-fhir-server-url",    value: "Set by PO runtime" },
            { label: "x-fhir-access-token",  value: "Set by PO runtime (redacted in logs)" },
            { label: "x-patient-id",         value: "Set by PO runtime" },
          ]}
          status="info"
        />
      </div>
    </div>
  );
}

function StatusCard({
  title,
  items,
  status,
}: {
  title: string;
  items: Array<{ label: string; value: string }>;
  status: "active" | "error" | "info";
}) {
  const statusDot: Record<string, string> = {
    active: "bg-[#059669]",
    error:  "bg-[#DC2626]",
    info:   "bg-[#2563EB]",
  };
  const statusLabel: Record<string, string> = {
    active: "Connected",
    error:  "Error",
    info:   "Info",
  };

  return (
    <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm p-5">
      <div className="flex items-center gap-2 mb-4">
        <h2 className="text-sm font-semibold font-[family-name:var(--font-geist-sans)] text-slate-800 dark:text-slate-200">
          {title}
        </h2>
        <span className="flex items-center gap-1.5 ml-auto">
          <span
            className={`w-2 h-2 rounded-full ${statusDot[status]}`}
            aria-hidden="true"
          />
          <span className="text-xs text-slate-400 dark:text-slate-500">
            {statusLabel[status]}
          </span>
        </span>
      </div>
      <dl className="space-y-2">
        {items.map(({ label, value }) => (
          <div key={label} className="flex items-start gap-4 text-sm">
            <dt className="w-40 shrink-0 text-slate-500 dark:text-slate-400">{label}</dt>
            <dd className="text-slate-700 dark:text-slate-300 font-[family-name:var(--font-geist-mono)] text-xs break-all">
              {value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
