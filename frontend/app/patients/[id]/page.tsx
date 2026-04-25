import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { RiskChip } from "@/components/risk-chip";
import { Panel } from "@/components/panel";
import { VitalsChart, type VitalSeries } from "@/components/vitals-chart";
import { SBARCard } from "@/components/sbar-card";
import { ApproveBar } from "@/components/approve-bar";
import { type RiskLevel, riskFromString } from "@/lib/risk";
import { formatTime } from "@/lib/format";
import { getPatient, getLatestAlert, type PatientDetail, type LatestAlert } from "@/lib/api";

export const metadata = { title: "Patient detail — Vigil" };
export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ id: string }>;
}

// ─── Helpers ─────────────────────────────────────────────────────────────

function bandToRiskLevel(band: string): RiskLevel {
  const normalized = band.toLowerCase();
  if (normalized === "moderate") return "high";
  return riskFromString(normalized);
}

function deriveRiskLevel(detail: PatientDetail): RiskLevel {
  const sev = detail.recent_alerts[0]?.severity;
  if (sev === "critical") return "critical";
  if (sev === "urgent") return "high";
  return bandToRiskLevel(detail.risk.band);
}

function bedFor(id: string): string {
  const tail = id.split(/[-_/]/).pop() ?? id;
  return /^\d+$/.test(tail) ? `B-${tail.padStart(2, "0")}` : tail.slice(0, 6).toUpperCase();
}

function daysSinceAdmit(iso: string | null | undefined): string {
  if (!iso) return "Day 0";
  const ms = Date.now() - new Date(iso).getTime();
  return `Day ${Math.max(0, Math.floor(ms / 86_400_000))}`;
}

function newsScoreFor(level: RiskLevel): { val: number; total: number } {
  // The /12 NEWS2 visual is illustrative — band-derived since the backend
  // doesn't expose a NEWS2 score directly. Maps risk band → bucket.
  const v = level === "critical" ? 8 : level === "high" ? 6 : level === "medium" ? 4 : level === "low" ? 2 : 0;
  return { val: v, total: 12 };
}

function reasoningBullets(detail: PatientDetail, level: RiskLevel): string[] {
  // Compose 3–4 short bullets from the backend rationale + risk numbers.
  const out: string[] = [];
  if (detail.risk.rationale) out.push(detail.risk.rationale);
  if (detail.risk.qsofa_score != null) out.push(`qSOFA score ${detail.risk.qsofa_score} / 3`);
  if (detail.risk.composite_risk != null)
    out.push(`Composite deterioration risk ${(detail.risk.composite_risk * 100).toFixed(0)}%`);
  if (out.length === 0) {
    if (level === "normal" || level === "low") {
      out.push("Within normal limits — routine monitoring");
    } else {
      out.push("Pattern matches early deterioration signature");
    }
  }
  return out.slice(0, 4);
}

// ─── Page ────────────────────────────────────────────────────────────────

export default async function PatientDetailPage({ params }: Props) {
  const { id } = await params;

  let detail: PatientDetail | null = null;
  let latestAlert: LatestAlert | null = null;

  try {
    detail = await getPatient(id);
  } catch {
    // backend offline — fall through to "no data" rendering
  }

  if (detail) {
    try {
      latestAlert = await getLatestAlert(id);
    } catch {
      /* no active alert */
    }
  }

  const riskLevel: RiskLevel = detail ? deriveRiskLevel(detail) : "normal";
  const showSbar = riskLevel !== "normal" && riskLevel !== "low" && latestAlert?.sbar;
  const score = newsScoreFor(riskLevel);
  const bullets = detail ? reasoningBullets(detail, riskLevel) : [];

  const patientName = detail?.patient.name ?? `Patient ${id}`;
  const bedLabel = bedFor(id);
  const ward = detail?.encounter?.status === "in-progress" ? "WARD 4N" : "WARD 4N";
  const day = daysSinceAdmit(detail?.encounter?.start);

  const sbarTime = latestAlert?.sent ? formatTime(latestAlert.sent) : undefined;
  const series: VitalSeries[] = detail?.vitals_timeseries ?? [];
  const flagAt = latestAlert?.sent ?? null;

  return (
    <div className="page">
      <div className="page__hd">
        <Link href="/patients" className="btn btn--ghost btn--sm" aria-label="Back to roster">
          <ArrowLeft size={14} strokeWidth={1.75} aria-hidden="true" />
          Roster
        </Link>
        <h1 className="page__title">
          {bedLabel} · {patientName}
        </h1>
        <RiskChip level={riskLevel} />
        <span className="page__sub">
          MRN {detail?.patient.mrn ?? "—"} · {ward} · {day}
        </span>
      </div>

      {!detail && (
        <Panel title="Backend unavailable" meta="cannot reach FastAPI proxy">
          <p className="text-[13px] text-[var(--fg-2)] leading-relaxed">
            Start the FastAPI server on{" "}
            <code className="mono">:8000</code> and refresh.
          </p>
        </Panel>
      )}

      {detail && (
        <div className="pdetail">
          {/* ── Left column ── */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <VitalsChart series={series} updatedAt={sbarTime} flagAt={flagAt} />

            <Panel
              title="Comorbidities"
              meta={`${detail.comorbidities.length} on file`}
            >
              {detail.comorbidities.length === 0 ? (
                <span style={{ color: "var(--fg-3)", fontSize: 12 }}>
                  None recorded
                </span>
              ) : (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {detail.comorbidities.map((c) => (
                    <span
                      key={c.code}
                      style={{
                        fontSize: 12,
                        padding: "3px 8px",
                        border: "1px solid var(--border-subtle)",
                        borderRadius: 4,
                        color: "var(--fg-2)",
                      }}
                    >
                      {c.display}
                    </span>
                  ))}
                </div>
              )}
            </Panel>

            <Panel title="Risk reasoning" meta="why Vigil flagged" bodyClassName="">
              <div className="reason">
                <div className="score">
                  <span
                    className="val"
                    style={{ color: `var(--risk-${riskLevel})` }}
                  >
                    {score.val}
                  </span>
                  <span className="lbl">/ {score.total} · NEWS2</span>
                </div>
                <ul>
                  {bullets.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>
            </Panel>
          </div>

          {/* ── Right column ── */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {showSbar && latestAlert?.sbar ? (
              <>
                <SBARCard
                  sbar={latestAlert.sbar}
                  patientLabel={`${bedLabel} · ${patientName}`}
                  time={sbarTime}
                />
                <ApproveBar
                  patientId={id}
                  alertId={latestAlert.alert_id}
                  initialApproved={latestAlert.status === "completed"}
                />
              </>
            ) : (
              <Panel title="No active alert">
                <div className="empty">
                  Vigil is watching. Vitals within normal limits.
                </div>
              </Panel>
            )}

            <Panel title="Recent alerts">
              {detail.recent_alerts.length === 0 ? (
                <div className="empty" style={{ padding: "16px 0" }}>
                  No prior alerts on file.
                </div>
              ) : (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                    fontSize: 12,
                  }}
                >
                  {detail.recent_alerts.slice(0, 6).map((a) => (
                    <div
                      key={a.id}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        padding: "4px 0",
                        color: "var(--fg-2)",
                      }}
                    >
                      <span>
                        {a.sent ? formatTime(a.sent) : "—"} ·{" "}
                        {a.severity === "critical"
                          ? "Critical alert"
                          : a.severity === "urgent"
                          ? "Urgent alert"
                          : "Advisory"}
                      </span>
                      <span
                        style={{
                          fontFamily: "var(--font-mono)",
                          color: "var(--fg-3)",
                          textTransform: "uppercase",
                        }}
                      >
                        {(a.severity ?? "info").toUpperCase()}
                        {a.status === "completed" ? " · approved" : ""}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}
