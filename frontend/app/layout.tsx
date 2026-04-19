import type { Metadata } from "next";
import { Geist, Geist_Mono, Inter } from "next/font/google";
import Link from "next/link";
import { Toaster } from "@/components/ui/sonner";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist-sans", display: "swap" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
  // Tabular numerals for vitals columns
});

export const metadata: Metadata = {
  title: "Vigil — Postop Sentinel",
  description: "Post-operative clinical early-warning dashboard powered by FHIR + AI",
};

const NAV_LINKS = [
  { href: "/patients", label: "Patients" },
  { href: "/timeline", label: "Timeline" },
  { href: "/alerts",   label: "Alerts" },
  { href: "/settings", label: "Settings" },
];

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geist.variable} ${geistMono.variable} ${inter.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-50 font-[family-name:var(--font-inter)]">
        {/* Skip-to-content for keyboard navigation (WCAG 2.4.1) */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:px-4 focus:py-2 focus:bg-[#0B5FFF] focus:text-white focus:rounded-md focus:text-sm focus:font-medium"
        >
          Skip to main content
        </a>

        {/* ── Top bar ── */}
        <header className="sticky top-0 z-50 h-14 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center px-6 gap-4 shadow-[0_1px_0_0_#E2E8F0]">
          {/* Logo — left */}
          <Link
            href="/"
            className="flex items-center gap-2 font-[family-name:var(--font-geist-sans)] font-bold text-lg text-slate-900 dark:text-slate-50 tracking-tight select-none"
            aria-label="Vigil home"
          >
            <svg
              width="22"
              height="22"
              viewBox="0 0 22 22"
              fill="none"
              aria-hidden="true"
              className="text-[#0B5FFF]"
            >
              <rect width="22" height="22" rx="5" fill="currentColor" />
              <path
                d="M11 5L14.5 13H7.5L11 5Z"
                fill="white"
                stroke="white"
                strokeWidth="0.5"
              />
              <circle cx="11" cy="16" r="1.5" fill="white" />
            </svg>
            Vigil
          </Link>

          {/* Unit name — center */}
          <div className="flex-1 flex justify-center">
            <span className="text-sm font-medium text-slate-500 dark:text-slate-400 tracking-wide">
              Post-op Unit 4B
            </span>
          </div>

          {/* User & settings — right */}
          <div className="flex items-center gap-3">
            <span className="text-sm text-slate-600 dark:text-slate-300">Dr. A. Chen</span>
            <Link
              href="/settings"
              className="p-1.5 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              aria-label="Settings"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </Link>
          </div>
        </header>

        {/* ── Side-nav + main ── */}
        <div className="flex flex-1 min-h-0">
          {/* Sidebar */}
          <nav
            className="w-56 shrink-0 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col py-4 px-3 gap-1"
            aria-label="Primary navigation"
          >
            {NAV_LINKS.map(({ href, label }) => (
              <NavLink key={href} href={href} label={label} />
            ))}
          </nav>

          {/* Page content */}
          <main className="flex-1 overflow-auto bg-slate-50 dark:bg-slate-950" id="main-content">
            {children}
          </main>
        </div>
        <Toaster position="bottom-right" richColors />
      </body>
    </html>
  );
}

/** Client-side-aware nav link with active state */
function NavLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-50 transition-colors"
    >
      {label}
    </Link>
  );
}
