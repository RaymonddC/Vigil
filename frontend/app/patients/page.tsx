import { getPatients } from "@/lib/api";
import { PatientsTable } from "@/components/patients-table";

export const metadata = {
  title: "Patients — Vigil",
};

/**
 * Server Component: fetches patient list from FastAPI backend.
 * Delegates rendering + filtering to PatientsTable client component.
 * FRONTEND_SPEC §3.1
 */
export default async function PatientsPage() {
  const data = await getPatients();

  return (
    <div className="p-6 space-y-6">
      {/* Page heading */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold font-[family-name:var(--font-geist-sans)] text-slate-900 dark:text-slate-50 tracking-tight">
          Post-operative Patients
        </h1>
      </div>

      <PatientsTable patients={data.patients} />
    </div>
  );
}
