const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

export async function getPatients() {
  const res = await fetch(`${BASE}/api/patients`, { next: { revalidate: 10 } });
  if (!res.ok) throw new Error('patients fetch failed');
  return res.json();
}

export async function getPatient(id: string) {
  const res = await fetch(`${BASE}/api/patients/${id}`, { next: { revalidate: 10 } });
  if (!res.ok) throw new Error(`patient ${id} fetch failed`);
  return res.json();
}

export async function getAlert(pid: string, aid: string) {
  const res = await fetch(`${BASE}/api/patients/${pid}/alerts/${aid}`, { next: { revalidate: 10 } });
  if (!res.ok) throw new Error(`alert ${aid} fetch failed`);
  return res.json();
}

export async function ackAlert(pid: string, aid: string): Promise<{
  alert_id: string;
  status: string;
  acknowledged_at: string;
  audit_id: string;
}> {
  const res = await fetch(`${BASE}/api/patients/${pid}/alerts/${aid}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ clinician_id: 'prac-nurse-17', note: 'Acknowledged, RRT dispatched.' }),
  });
  if (!res.ok) throw new Error('approve failed');
  return res.json();
}

export async function getLatestAlert(pid: string) {
  const res = await fetch(`${BASE}/api/patients/${pid}/alerts/latest`, { next: { revalidate: 5 } });
  if (!res.ok) throw new Error(`latest alert for ${pid} fetch failed`);
  return res.json();
}

export async function triggerAgentTick() {
  const res = await fetch(`${BASE}/api/agent/tick`, { method: 'POST' });
  if (!res.ok) throw new Error('agent tick failed');
  return res.json();
}

export async function getEvents(since?: string) {
  const url = since
    ? `${BASE}/api/events/tail?since=${encodeURIComponent(since)}`
    : `${BASE}/api/events/tail`;
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error('events fetch failed');
  return res.json();
}

export async function getStatus() {
  const res = await fetch(`${BASE}/api/status`, { next: { revalidate: 30 } });
  if (!res.ok) throw new Error('status fetch failed');
  return res.json();
}
