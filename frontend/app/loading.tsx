export default function RootLoading() {
  return (
    <div className="p-6 flex items-center justify-center min-h-[50vh]">
      <div className="text-center space-y-3">
        <div
          className="mx-auto w-8 h-8 border-2 border-slate-200 dark:border-slate-700 border-t-[#0B5FFF] rounded-full animate-spin"
          role="status"
          aria-label="Loading"
        />
        <p className="text-sm text-slate-400 dark:text-slate-500">Loading...</p>
      </div>
    </div>
  );
}
