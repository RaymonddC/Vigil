"use client";

/**
 * Shared error boundary UI for all route segments.
 * Displays a recovery-friendly error card with retry and navigation options.
 * FRONTEND_SPEC §8 — accessible, keyboard-navigable.
 */

import Link from "next/link";

interface RouteErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
  title?: string;
}

export function RouteError({
  error,
  reset,
  title = "Something went wrong",
}: RouteErrorProps) {
  const isBackendError =
    error.message.includes("fetch failed") ||
    error.message.includes("ECONNREFUSED") ||
    error.message.includes("502") ||
    error.message.includes("Backend unavailable");

  return (
    <div className="p-6 flex items-center justify-center min-h-[50vh]">
      <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-800 shadow-sm p-8 max-w-md w-full text-center space-y-4">
        {/* Icon */}
        <div className="mx-auto w-12 h-12 flex items-center justify-center rounded-full bg-amber-50 dark:bg-amber-950/50">
          <svg
            width="24"
            height="24"
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

        {/* Title */}
        <h2 className="text-lg font-semibold font-[family-name:var(--font-geist-sans)] text-slate-900 dark:text-slate-50">
          {title}
        </h2>

        {/* Message */}
        <p className="text-sm text-slate-500 dark:text-slate-400">
          {isBackendError
            ? "Cannot reach the FastAPI backend. Make sure the server is running on the expected port."
            : error.message || "An unexpected error occurred."}
        </p>

        {/* Actions */}
        <div className="flex items-center justify-center gap-3 pt-2">
          <button
            type="button"
            onClick={reset}
            className="px-4 py-2 text-sm font-medium bg-[#0B5FFF] text-white rounded-md hover:bg-[#0950DB] transition-colors min-h-[44px]"
          >
            Try again
          </button>
          <Link
            href="/patients"
            className="px-4 py-2 text-sm font-medium border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors min-h-[44px] inline-flex items-center"
          >
            Back to patients
          </Link>
        </div>

        {/* Digest (for debugging) */}
        {error.digest && (
          <p className="text-xs text-slate-300 dark:text-slate-700 font-[family-name:var(--font-geist-mono)]">
            Error ID: {error.digest}
          </p>
        )}
      </div>
    </div>
  );
}
