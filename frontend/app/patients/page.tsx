import { getPatients, type PatientSummary } from "@/lib/api";
import { PatientsTable } from "@/components/patients-table";

export const metadata = {
  title: "Patients — Vigil",
};

/**
 * Server Component: fetches patient list from FastAPI backend.
 * Gracefully degrades with an offline notice when backend is unreachable.
 * FRONTEND_SPEC §3.1
 */
export default async function PatientsPage() {
  let patients: PatientSummary[] = [];
  let offline = false;

  try {
    const data = await getPatients();
    patients = data.patients;
  } catch {
    offline = true;
  }

  return (
    <div className="p-6 space-y-6">
      {/* Page heading */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold font-[family-name:var(--font-geist-sans)] text-slate-900 dark:text-slate-50 tracking-tight">
          Post-operative Patients
        </h1>
      </div>

      {offline ? (
        <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm px-6 py-12 text-center space-y-3">
          <div className="mx-auto w-10 h-10 flex items-center justify-center rounded-full bg-amber-50 dark:bg-amber-950/50">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="text-amber-600 dark:text-amber-400"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
          <p className="text-sm font-medium text-slate-600 dark:text-slate-300">
            Backend unavailable
          </p>
          <p className="text-xs text-slate-400 dark:text-slate-500">
            Cannot reach the FastAPI proxy. Ensure{" "}
            <code className="font-[family-name:var(--font-geist-mono)] bg-slate-100 dark:bg-slate-800 px-1 py-0.5 rounded text-[11px]">
              NEXT_PUBLIC_API_BASE_URL
            </code>{" "}
            is set and the server is running.
          </p>
        </div>
      ) : (
        <PatientsTable patients={patients} />
      )}
    </div>
  );
}
