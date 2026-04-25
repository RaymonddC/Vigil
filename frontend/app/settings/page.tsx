import type { Metadata } from "next";
import { Panel } from "@/components/panel";
import { getStatus, type StatusResponse } from "@/lib/api";

export const metadata: Metadata = {
  title: "System health — Vigil",
};

export const dynamic = "force-dynamic";

function formatTs(iso: string): string {
  try {
    return iso.substring(11, 19);
  } catch {
    return iso;
  }
}

export default async function SettingsPage() {
  let status: StatusResponse | null = null;
  let error: string | null = null;

  try {
    status = await getStatus();
  } catch (e) {
    error = e instanceof Error ? e.message : "Backend unreachable";
  }

  const lastCheck = status ? formatTs(status.ts) : "—";
  const allGreen =
    status != null && status.fhir_healthy && status.agent_healthy;

  return (
    <div className="page">
      <div className="page__hd">
        <h1 className="page__title">System health</h1>
        <span className="page__sub">
          {error
            ? "backend unreachable"
            : `${allGreen ? "all green" : "partial"} · last check ${lastCheck}`}
        </span>
      </div>

      {error && (
        <Panel title="Backend unreachable" meta="cannot reach FastAPI proxy">
          <p className="text-[13px] text-[var(--fg-2)] leading-relaxed">
            Start the FastAPI server at{" "}
            <code className="mono">http://localhost:8000</code> and refresh.
          </p>
        </Panel>
      )}

      {!error && status && (
        <div className="settings-grid">
          <Panel title="LLM provider" bodyClassName="">
            <div>
              <Row k="Provider" v={status.llm_provider} />
              <Row k="Switched via" v="LLM_PROVIDER env var" />
              {status.token_usage && Object.keys(status.token_usage).length > 0 && (
                <Row
                  k="Token usage"
                  v={Object.entries(status.token_usage)
                    .map(([k, n]) => `${k} ${n}`)
                    .join(" · ")}
                />
              )}
              <StatusRow label="Status" tone="ok" text="OPERATIONAL" />
            </div>
          </Panel>

          <Panel title="FHIR gateway" bodyClassName="">
            <div>
              <Row k="Endpoint" v={status.fhir_url} />
              <Row k="Version" v="R4" />
              {status.fhir_error && <Row k="Error" v={status.fhir_error} />}
              <StatusRow
                label="Status"
                tone={status.fhir_healthy ? "ok" : "err"}
                text={status.fhir_healthy ? "OPERATIONAL" : "UNREACHABLE"}
              />
            </div>
          </Panel>

          <Panel title="Agent heartbeat" bodyClassName="">
            <div>
              <Row k="Agent URL" v={status.a2a_agent_url} />
              <Row k="Poll interval" v="POLL_INTERVAL_SEC (default 900 s)" />
              <Row k="Last check" v={lastCheck} />
              <StatusRow
                label="Status"
                tone={status.agent_healthy ? "ok" : "warn"}
                text={status.agent_healthy ? "HEARTBEAT" : "STOPPED"}
              />
            </div>
          </Panel>

          <Panel title="Prompt Opinion SHARP" bodyClassName="">
            <div>
              <Row k="x-fhir-server-url" v="set by PO runtime" />
              <Row k="x-fhir-access-token" v="redacted in logs" />
              <Row k="x-patient-id" v="set by PO runtime" />
              <StatusRow label="Status" tone="ok" text="RUNTIME" />
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="sysrow">
      <span className="k">{k}</span>
      <span className="v">{v}</span>
    </div>
  );
}

function StatusRow({
  label,
  tone,
  text,
}: {
  label: string;
  tone: "ok" | "warn" | "err";
  text: string;
}) {
  return (
    <div className="sysrow">
      <span className="k">{label}</span>
      <span className={`status status--${tone}`}>
        <span className="d" aria-hidden="true" />
        {text}
      </span>
    </div>
  );
}
