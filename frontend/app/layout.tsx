import type { Metadata } from "next";
import { Geist, JetBrains_Mono } from "next/font/google";
import { TopNav } from "@/components/top-nav";
import { Toaster } from "@/components/ui/sonner";
import "./globals.css";

// Geist drives every product surface (UI body + display).
const geist = Geist({
  subsets: ["latin"],
  variable: "--font-geist-sans",
  display: "swap",
});

// JetBrains Mono is reserved for vitals, MRNs, timestamps — anything
// where tabular numerals matter. Bound to `--font-mono` via globals.css.
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Vigil — Postop Sentinel",
  description: "Post-operative clinical early-warning dashboard powered by FHIR + AI",
};

/**
 * Apply the persisted theme before paint to avoid FOUC. Wrapped in a
 * try/catch so localStorage exceptions in private mode don't break first
 * render. Falls through to OS preference if nothing is stored.
 */
const themeBootstrap = `(function(){try{var k='vigil-theme';var v=localStorage.getItem(k);if(v==='dark'||(v==null&&matchMedia('(prefers-color-scheme: dark)').matches)){document.documentElement.classList.add('dark');}}catch(e){}})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geist.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body>
        {/* WCAG 2.4.1 — Skip to content. Hidden until focused. */}
        <a href="#main-content" className="skip-link">
          Skip to main content
        </a>

        <TopNav />

        <main id="main-content">{children}</main>

        <Toaster position="bottom-right" />
      </body>
    </html>
  );
}
