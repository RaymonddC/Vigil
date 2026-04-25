"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Bell, Settings, Store, UsersRound } from "lucide-react";
import { ClinicianSwitcher } from "@/components/clinician-switcher";
import { ThemeToggle } from "@/components/theme-toggle";

type Tab = {
  id: string;
  label: string;
  href: string;
  Icon: typeof Activity;
  /** Treat any pathname starting with one of these prefixes as active. */
  match: string[];
};

const TABS: Tab[] = [
  { id: "roster",      label: "Roster",      href: "/patients",    Icon: UsersRound, match: ["/patients"] },
  { id: "alerts",      label: "Alerts",      href: "/alerts",      Icon: Bell,       match: ["/alerts"] },
  { id: "timeline",    label: "Timeline",    href: "/timeline",    Icon: Activity,   match: ["/timeline"] },
  { id: "marketplace", label: "Marketplace", href: "/marketplace", Icon: Store,      match: ["/marketplace"] },
  { id: "settings",    label: "Settings",    href: "/settings",    Icon: Settings,   match: ["/settings"] },
];

export function TopNav() {
  const pathname = usePathname() ?? "/";

  return (
    <nav className="nav" aria-label="Primary">
      <Link href="/" className="nav__brand" aria-label="Vigil home">
        <svg
          width="22"
          height="22"
          viewBox="0 0 32 32"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M6 5 L26 5 L26 16 C26 22.6 21.5 27 16 29 C10.5 27 6 22.6 6 16 Z"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
          <path
            d="M10.5 16 C12.2 13.3 14 12 16 12 C18 12 19.8 13.3 21.5 16 C19.8 18.7 18 20 16 20 C14 20 12.2 18.7 10.5 16 Z"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
          <circle cx="16" cy="16" r="1.75" fill="currentColor" />
        </svg>
        <span className="wm">Vigil</span>
      </Link>

      <div className="nav__tabs">
        {TABS.map((t) => {
          const active = t.match.some((m) => pathname === m || pathname.startsWith(m + "/"));
          return (
            <Link
              key={t.id}
              href={t.href}
              className={`nav__tab ${active ? "nav__tab--active" : ""}`}
              aria-current={active ? "page" : undefined}
            >
              <t.Icon size={14} strokeWidth={1.75} aria-hidden="true" />
              {t.label}
            </Link>
          );
        })}
      </div>

      <div className="nav__right">
        <ThemeToggle />
        <ClinicianSwitcher />
      </div>
    </nav>
  );
}
