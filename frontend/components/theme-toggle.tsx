"use client";

import * as React from "react";
import { Moon, Sun } from "lucide-react";

const STORAGE_KEY = "vigil-theme";

function readStoredTheme(): "light" | "dark" {
  if (typeof window === "undefined") return "light";
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "dark" || stored === "light") return stored;
  } catch {
    /* localStorage disabled — fall through */
  }
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

export function ThemeToggle() {
  // We don't render the icon until after mount — both icons are roughly the
  // same shape and either pre-paint risks a hydration mismatch since the
  // server has no idea what the user's stored preference is.
  const [theme, setTheme] = React.useState<"light" | "dark">("light");
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    // One-time mount read to swap from the SSR-safe "light" placeholder to
    // the persisted theme. The set-state-in-effect rule flags cascading
    // renders; this is the documented "synchronise with external store"
    // exception (matches the clinician-switcher pattern in this repo).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTheme(readStoredTheme());
    setMounted(true);
  }, []);

  const toggle = React.useCallback(() => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    if (typeof document !== "undefined") {
      document.documentElement.classList.toggle("dark", next === "dark");
    }
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore quota / private mode */
    }
  }, [theme]);

  return (
    <button
      type="button"
      onClick={toggle}
      className="btn btn--ghost"
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
    >
      {mounted ? (
        theme === "dark" ? (
          <Sun size={14} strokeWidth={1.75} aria-hidden="true" />
        ) : (
          <Moon size={14} strokeWidth={1.75} aria-hidden="true" />
        )
      ) : (
        <span aria-hidden="true" style={{ width: 14, height: 14, display: "inline-block" }} />
      )}
    </button>
  );
}
