import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { RiskChip } from "@/components/risk-chip";
import { Panel } from "@/components/panel";
import { SBARCard } from "@/components/sbar-card";
import { ApproveBar } from "@/components/approve-bar";
import { getAlert } from "@/lib/api";
import type { RiskLevel } from "@/lib/risk";
import { formatTime } from "@/lib/format";

export const metadata = { title: "Alert detail — Vigil" };

interface Props {
  params: Promise<{ id: string; alertId: string }>;
}

function severityToRisk(severity: string | null): RiskLevel {
  if (severity === "critical") return "critical";
  if (severity === "urgent") return "high";
  if (severity === "info") return "low";
  return "medium";
}

export default async function AlertDetailPage({ params }: Props) {
  const { id, alertId } = await params;

  let alert: Awaited<ReturnType<typeof getAlert>> | null = null;
  try {
    alert = await getAlert(id, alertId);
  } catch {
    notFound();
  }

  if (!alert) notFound();

  const riskLevel = severityToRisk(alert.severity);
  const sbar = alert.sbar ?? null;
  const time = alert.sent ? formatTime(alert.sent) : undefined;
  const approved = alert.status === "completed";

  return (
    <div className="page">
      <div className="page__hd">
        <Link
          href={`/patients/${id}`}
          className="btn btn--ghost btn--sm"
          aria-label="Back to patient"
        >
          <ArrowLeft size={14} strokeWidth={1.75} aria-hidden="true" />
          Patient
        </Link>
        <h1 className="page__title">Alert {alertId.slice(0, 8)}</h1>
        <RiskChip level={riskLevel} />
        {alert.model_used && (
          <span className="page__sub">via {alert.model_used}</span>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {sbar ? (
          <>
            <SBARCard
              sbar={sbar}
              patientLabel={`Patient ${id}`}
              time={time}
              approved={approved}
            />
            <ApproveBar
              patientId={id}
              alertId={alertId}
              initialApproved={approved}
            />
          </>
        ) : (
          <Panel title="Narrative">
            <p className="text-[13px] text-[var(--fg-2)] leading-relaxed">
              {alert.narrative}
            </p>
          </Panel>
        )}

        <Panel
          title="Recipient"
          meta={alert.recipient_role?.replace(/_/g, " ") ?? "rapid response"}
        >
          <p className="text-[12px] text-[var(--fg-3)] leading-relaxed">
            Approval writes a FHIR Communication and AuditEvent to the clinical
            record. Dismiss closes this view without a network call.
          </p>
        </Panel>
      </div>
    </div>
  );
}
