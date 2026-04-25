"use client";

/**
 * Shared error boundary UI for all route segments.
 * Displays a recovery-friendly error card with retry and navigation options.
 */

import Link from "next/link";
import { Panel } from "@/components/panel";

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
    <div className="page">
      <div className="page__hd">
        <h1 className="page__title">{title}</h1>
        <span className="page__sub">recoverable error</span>
      </div>

      <Panel title="What happened" meta="route boundary">
        <p className="text-[13px] text-[var(--fg-2)] leading-relaxed">
          {isBackendError
            ? "Cannot reach the FastAPI backend. Make sure the server is running on the expected port."
            : error.message || "An unexpected error occurred."}
        </p>
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button type="button" className="btn btn--primary" onClick={reset}>
            Try again
          </button>
          <Link href="/patients" className="btn">
            Back to roster
          </Link>
        </div>
        {error.digest && (
          <p
            style={{
              marginTop: 10,
              fontSize: 11,
              color: "var(--fg-3)",
              fontFamily: "var(--font-mono)",
            }}
          >
            Error ID: {error.digest}
          </p>
        )}
      </Panel>
    </div>
  );
}
