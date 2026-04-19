import Link from "next/link";
import { RiskBadge } from "@/components/risk-badge";
import type { RiskLevel } from "@/lib/risk";

export const metadata = {
  title: "Patients — Vigil",
};

// Placeholder patients for Phase 1 scaffold
const PLACEHOLDER_PATIENTS = [
  { id: "PT-007", name: "Reyes, Maria",   mrn: "102394", procedure: "Lap chole",        tPlus: "02:14", risk: "critical" as RiskLevel, alertTime: "00:42" },
  { id: "PT-009", name: "Osei, Kwame",    mrn: "110201", procedure: "Hip arthroplasty", tPlus: "05:48", risk: "high"     as RiskLevel, alertTime: "01:10" },
  { id: "PT-003", name: "Novak, Irena",   mrn: "100882", procedure: "C-section",        tPlus: "01:02", risk: "medium"   as RiskLevel, alertTime: "04:33" },
  { id: "PT-002", name: "Tanaka, Yuki",   mrn: "119384", procedure: "CABG",             tPlus: "07:30", risk: "low"      as RiskLevel, alertTime: ""      },
  { id: "PT-001", name: "Nguyen, Linh",   mrn: "105521", procedure: "Appendectomy",     tPlus: "03:45", risk: "normal"   as RiskLevel, alertTime: ""      },
];

export default function PatientsPage() {
  return (
    <div className="p-6 space-y-6">
      {/* Page heading */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold font-[family-name:var(--font-geist-sans)] text-slate-900 dark:text-slate-50 tracking-tight">
          Post-operative Patients
        </h1>
        <div className="flex items-center gap-2" role="group" aria-label="Filter patients">
          <FilterPill label="All 10" active />
          <FilterPill label="High+" />
          <FilterPill label="Triggered" />
        </div>
      </div>

      {/* Patient table */}
      <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <caption className="sr-only">Post-op patient roster</caption>
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950">
              <th scope="col" className="px-4 py-3 text-left font-medium text-slate-500 dark:text-slate-400">Name</th>
              <th scope="col" className="px-4 py-3 text-left font-medium text-slate-500 dark:text-slate-400 font-[family-name:var(--font-geist-mono)]">MRN</th>
              <th scope="col" className="px-4 py-3 text-left font-medium text-slate-500 dark:text-slate-400">Procedure</th>
              <th scope="col" className="px-4 py-3 text-left font-medium text-slate-500 dark:text-slate-400 font-[family-name:var(--font-geist-mono)]">T+ OR</th>
              <th scope="col" className="px-4 py-3 text-left font-medium text-slate-500 dark:text-slate-400">Risk</th>
              <th scope="col" className="px-4 py-3 text-left font-medium text-slate-500 dark:text-slate-400 font-[family-name:var(--font-geist-mono)]">Alert</th>
              <th scope="col" className="w-10"><span className="sr-only">Open</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {PLACEHOLDER_PATIENTS.map((p) => (
              <tr
                key={p.id}
                className="hover:bg-slate-50 dark:hover:bg-slate-800/50 cursor-pointer transition-colors"
              >
                <td className="px-4 py-3 font-medium text-slate-900 dark:text-slate-50">
                  <Link href={`/patients/${p.id}`} className="block hover:text-[#0B5FFF] transition-colors">
                    {p.name}
                  </Link>
                </td>
                <td className="px-4 py-3 text-slate-500 dark:text-slate-400 font-[family-name:var(--font-geist-mono)] text-xs tabular-nums">{p.mrn}</td>
                <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{p.procedure}</td>
                <td className="px-4 py-3 text-slate-500 dark:text-slate-400 font-[family-name:var(--font-geist-mono)] tabular-nums">{p.tPlus}</td>
                <td className="px-4 py-3">
                  <RiskBadge level={p.risk} />
                </td>
                <td className="px-4 py-3 text-slate-500 dark:text-slate-400 font-[family-name:var(--font-geist-mono)] tabular-nums">
                  {p.alertTime || <span className="text-slate-300 dark:text-slate-600">—</span>}
                </td>
                <td className="px-4 py-3 text-right">
                  <Link
                    href={`/patients/${p.id}`}
                    className="text-slate-400 hover:text-[#0B5FFF] transition-colors"
                    aria-label={`Open ${p.name}`}
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                      <polyline points="9 18 15 12 9 6" />
                    </svg>
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FilterPill({ label, active }: { label: string; active?: boolean }) {
  return (
    <button
      type="button"
      className={[
        "px-3 py-1.5 text-xs font-medium rounded-md border transition-colors",
        active
          ? "bg-[#0B5FFF] text-white border-[#0B5FFF]"
          : "bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600",
      ].join(" ")}
    >
      {label}
    </button>
  );
}
