import { Skeleton } from "@/components/ui/skeleton";

export default function PatientsLoading() {
  return (
    <div className="p-6 space-y-6">
      {/* Header skeleton */}
      <div className="flex items-center justify-between">
        <Skeleton className="h-8 w-64" />
        <div className="flex gap-2">
          <Skeleton className="h-8 w-16 rounded-md" />
          <Skeleton className="h-8 w-16 rounded-md" />
          <Skeleton className="h-8 w-20 rounded-md" />
        </div>
      </div>

      {/* Table skeleton */}
      <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        {/* Header row */}
        <div className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-4 py-3 flex gap-4">
          {[120, 80, 140, 60, 60, 60, 20].map((w, i) => (
            <Skeleton key={i} className="h-4" style={{ width: w }} />
          ))}
        </div>
        {/* Data rows */}
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="border-b border-slate-100 dark:border-slate-800 px-4 py-3 flex gap-4 items-center"
          >
            <Skeleton className="h-4 w-[120px]" />
            <Skeleton className="h-4 w-[80px]" />
            <Skeleton className="h-4 w-[140px]" />
            <Skeleton className="h-4 w-[60px]" />
            <Skeleton className="h-6 w-[70px] rounded-md" />
            <Skeleton className="h-4 w-[60px]" />
            <Skeleton className="h-4 w-[16px]" />
          </div>
        ))}
      </div>
    </div>
  );
}
