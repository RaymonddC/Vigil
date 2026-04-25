import { getPatients, type PatientSummary } from "@/lib/api";
import { PatientsTable } from "@/components/patients-table";

export const metadata = {
  title: "Roster — Vigil",
};

/**
 * Force dynamic rendering — RSC fetch runs per-request, never at build
 * time. Otherwise docker build blocks pre-rendering this page when the
 * backend isn't up yet. Router cache + Timeline's router.refresh() on
 * Tick Now keep data fresh without a hard reload. FRONTEND_SPEC §3.1
 */
export const dynamic = "force-dynamic";

export default async function PatientsPage() {
  let patients: PatientSummary[] = [];
  let offline = false;

  try {
    const data = await getPatients();
    patients = data.patients;
  } catch {
    offline = true;
  }

  const count = patients.length;
  const ward = "Ward 4N";

  return (
    <div className="page">
      <div className="page__hd">
        <h1 className="page__title">Roster</h1>
        <span className="page__sub">
          {ward} · {count} patient{count === 1 ? "" : "s"} · sorted by risk
        </span>
      </div>

      {offline ? (
        <div className="panel">
          <div className="panel__hd">
            <span className="t">Backend unavailable</span>
            <span className="s">FastAPI proxy unreachable</span>
          </div>
          <div className="panel__body">
            <p className="text-[13px] text-[var(--fg-2)] leading-relaxed">
              Cannot reach the FastAPI proxy. Ensure{" "}
              <code className="mono text-[12px]" style={{ background: "var(--surface-2)", padding: "1px 6px", borderRadius: 3 }}>
                NEXT_PUBLIC_API_BASE_URL
              </code>{" "}
              is set and the server is running.
            </p>
          </div>
        </div>
      ) : (
        <PatientsTable patients={patients} />
      )}
    </div>
  );
}
