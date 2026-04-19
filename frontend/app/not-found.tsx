import Link from "next/link";

export default function NotFound() {
  return (
    <div className="p-6 flex items-center justify-center min-h-[60vh]">
      <div className="text-center space-y-4">
        <p className="text-5xl font-semibold font-[family-name:var(--font-geist-mono)] text-slate-300 dark:text-slate-700">
          404
        </p>
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-50">
          Page not found
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 max-w-xs mx-auto">
          The page you are looking for does not exist or has been moved.
        </p>
        <Link
          href="/patients"
          className="inline-flex px-4 py-2 text-sm font-medium bg-[#0B5FFF] text-white rounded-md hover:bg-[#0950DB] transition-colors min-h-[44px] items-center"
        >
          Back to patients
        </Link>
      </div>
    </div>
  );
}
