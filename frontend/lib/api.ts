/**
 * Vigil API client.
 *
 * Two call paths:
 * - Server Components (RSC): call FastAPI backend directly via SERVER_BASE
 * - Client Components: call Next.js proxy via relative URL (keeps API keys server-side)
 *
 * FRONTEND_SPEC.md §6 / API_CONTRACTS.md §6
 */

import { z } from "zod";

// ---------------------------------------------------------------------------
// Base URLs
// ---------------------------------------------------------------------------

/** Direct backend URL — used by server components only (runs server-side) */
const SERVER_BASE =
  process.env.BACKEND_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";

// ---------------------------------------------------------------------------
// Zod response schemas — typed parsing for upstream data
// ---------------------------------------------------------------------------

export const PatientSummarySchema = z.object({
  id: z.string(),
  mrn: z.string(),
  name: z.string(),
  age: z.number().nullable(),
  trajectory: z.string(),
  latest_risk_band: z.string(),
  latest_alert_at: z.string().nullable(),
  unread_alerts: z.number(),
});
export type PatientSummary = z.infer<typeof PatientSummarySchema>;

export const PatientsResponseSchema = z.object({
  patients: z.array(PatientSummarySchema),
});
export type PatientsResponse = z.infer<typeof PatientsResponseSchema>;

export const AlertSummarySchema = z.object({
  id: z.string(),
  severity: z.string().nullable(),
  sent: z.string().nullable(),
  status: z.string().nullable(),
});

export const SBARSchema = z.object({
  situation: z.string(),
  background: z.string(),
  assessment: z.string(),
  recommendation: z.string(),
});

export const PatientDetailSchema = z.object({
  patient: z.object({
    id: z.string(),
    mrn: z.string(),
    name: z.string(),
    age: z.number().nullable(),
    birth_date: z.string().nullable(),
    gender: z.string().nullable(),
  }),
  encounter: z
    .object({
      id: z.string(),
      start: z.string().nullable(),
      status: z.string(),
    })
    .nullable(),
  vitals_timeseries: z.array(
    z.object({
      loinc: z.string(),
      label: z.string(),
      unit: z.string(),
      points: z.array(z.object({ t: z.string(), v: z.number() })),
    })
  ),
  comorbidities: z.array(
    z.object({ code: z.string(), display: z.string() })
  ),
  risk: z.object({
    qsofa_score: z.number().nullable(),
    composite_risk: z.number().nullable(),
    band: z.string(),
    rationale: z.string(),
  }),
  recent_alerts: z.array(AlertSummarySchema),
});
export type PatientDetail = z.infer<typeof PatientDetailSchema>;

export const LatestAlertSchema = z.object({
  alert_id: z.string(),
  severity: z.string().nullable(),
  sent: z.string().nullable(),
  recipient_role: z.string().nullable(),
  sbar: SBARSchema.nullable().optional(),
  narrative: z.string(),
  model_used: z.string(),
  status: z.string().nullable(),
});
export type LatestAlert = z.infer<typeof LatestAlertSchema>;

export const ApproveResponseSchema = z.object({
  alert_id: z.string(),
  status: z.string(),
  acknowledged_at: z.string(),
  audit_id: z.string(),
});
export type ApproveResponse = z.infer<typeof ApproveResponseSchema>;

export const AgentTickResponseSchema = z.object({
  triggered: z.boolean(),
  detail: z.string(),
  ts: z.string(),
});

export const StatusResponseSchema = z.object({
  llm_provider: z.string(),
  fhir_url: z.string(),
  fhir_healthy: z.boolean(),
  fhir_error: z.string().nullable(),
  agent_healthy: z.boolean(),
  a2a_agent_url: z.string(),
  token_usage: z.record(z.string(), z.number()).optional(),
  ts: z.string(),
});
export type StatusResponse = z.infer<typeof StatusResponseSchema>;

// ---------------------------------------------------------------------------
// Server-side API functions (RSC — direct to FastAPI)
// ---------------------------------------------------------------------------

/**
 * Build headers for server-side fetches. Injects X-API-Key from env so RSC
 * requests pass the FastAPI proxy's API key middleware (SEC-05). Never runs
 * in browser code — SERVER_BASE is only reachable from the server.
 */
function buildServerHeaders(): HeadersInit {
  const headers: Record<string, string> = { Accept: "application/json" };
  const apiKey = process.env.VIGIL_API_KEY;
  if (apiKey) headers["X-API-Key"] = apiKey;
  return headers;
}

export async function getPatients(): Promise<PatientsResponse> {
  const res = await fetch(`${SERVER_BASE}/api/patients`, {
    headers: buildServerHeaders(),
    next: { revalidate: 10 },
  });
  if (!res.ok) throw new Error("patients fetch failed");
  const data = await res.json();
  return PatientsResponseSchema.parse(data);
}

export async function getPatient(id: string): Promise<PatientDetail> {
  const res = await fetch(`${SERVER_BASE}/api/patients/${id}`, {
    headers: buildServerHeaders(),
    next: { revalidate: 10 },
  });
  if (!res.ok) throw new Error(`patient ${id} fetch failed`);
  const data = await res.json();
  return PatientDetailSchema.parse(data);
}

export async function getLatestAlert(pid: string): Promise<LatestAlert> {
  const res = await fetch(`${SERVER_BASE}/api/patients/${pid}/alerts/latest`, {
    headers: buildServerHeaders(),
    next: { revalidate: 5 },
  });
  if (!res.ok) throw new Error(`latest alert for ${pid} fetch failed`);
  const data = await res.json();
  return LatestAlertSchema.parse(data);
}

export async function getAlert(
  pid: string,
  aid: string
): Promise<LatestAlert> {
  const res = await fetch(
    `${SERVER_BASE}/api/patients/${pid}/alerts/${aid}`,
    { headers: buildServerHeaders(), next: { revalidate: 10 } }
  );
  if (!res.ok) throw new Error(`alert ${aid} fetch failed`);
  const data = await res.json();
  return LatestAlertSchema.parse(data);
}

export async function getStatus(): Promise<StatusResponse> {
  const res = await fetch(`${SERVER_BASE}/api/status`, {
    headers: buildServerHeaders(),
    next: { revalidate: 30 },
  });
  if (!res.ok) throw new Error("status fetch failed");
  const data = await res.json();
  return StatusResponseSchema.parse(data);
}

export async function getEvents(since?: string) {
  const url = since
    ? `${SERVER_BASE}/api/events/tail?since=${encodeURIComponent(since)}`
    : `${SERVER_BASE}/api/events/tail`;
  const res = await fetch(url, {
    headers: buildServerHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error("events fetch failed");
  return res.json();
}

// ---------------------------------------------------------------------------
// Client-side API functions (browser → Next.js proxy → FastAPI)
// These go through /api/* on the same origin, so API keys stay server-side.
// ---------------------------------------------------------------------------

export async function ackAlert(
  pid: string,
  aid: string
): Promise<ApproveResponse> {
  const res = await fetch(`/api/patients/${pid}/alerts/${aid}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      clinician_id: "prac-nurse-17",
      note: "Acknowledged, RRT dispatched.",
    }),
  });
  if (!res.ok) throw new Error("approve failed");
  const data = await res.json();
  return ApproveResponseSchema.parse(data);
}

export async function triggerAgentTick() {
  const res = await fetch("/api/agent/tick", { method: "POST" });
  if (!res.ok) throw new Error("agent tick failed");
  return res.json();
}

// ---------------------------------------------------------------------------
// Schemas + client-side functions for FE3 (Timeline) and FE4 (Alerts)
// ---------------------------------------------------------------------------

export const VigilEventSchema = z.object({
  id: z.string(),
  ts: z.string(),
  event_type: z.string(),
  request_id: z.string(),
  patient_id: z.string().nullable(),
  payload: z.record(z.string(), z.unknown()),
});
export type VigilEvent = z.infer<typeof VigilEventSchema>;

export const EventsTailResponseSchema = z.object({
  events: z.array(VigilEventSchema),
  server_ts: z.string(),
});
export type EventsTailResponse = z.infer<typeof EventsTailResponseSchema>;

export const QueueAlertSchema = z.object({
  id: z.string(),
  patient_id: z.string(),
  severity: z.enum(["critical", "urgent", "info"]),
  sbar: z.object({
    situation: z.string(),
    background: z.string().optional().default(""),
    assessment: z.string(),
    recommendation: z.string().optional().default(""),
  }),
  narrative: z.string(),
  recipient_role: z.string(),
  model_used: z.string(),
  status: z.string(),
  created_at: z.string(),
  acknowledged_at: z.string().nullable().optional(),
  clinician_id: z.string().nullable().optional(),
  note: z.string().nullable().optional(),
  audit_id: z.string().nullable().optional(),
});
export type QueueAlert = z.infer<typeof QueueAlertSchema>;

export const AlertsResponseSchema = z.object({
  alerts: z.array(QueueAlertSchema),
});

/** Client-side: poll event tail (Timeline, FE3) */
export async function fetchEvents(
  since?: string
): Promise<EventsTailResponse> {
  const url = since
    ? `/api/events/tail?since=${encodeURIComponent(since)}`
    : "/api/events/tail";
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error("events fetch failed");
  const data = await res.json();
  return EventsTailResponseSchema.parse(data);
}

/** Client-side: fetch pending alert queue (Alerts, FE4) */
export async function fetchAlerts(): Promise<{ alerts: QueueAlert[] }> {
  const res = await fetch("/api/alerts", { cache: "no-store" });
  if (!res.ok) throw new Error("alerts fetch failed");
  const data = await res.json();
  return AlertsResponseSchema.parse(data);
}
