"use client";

import * as React from "react";
import { Check, ChevronDown } from "lucide-react";

import {
  CLINICIANS,
  getSelectedClinicianId,
  onClinicianChange,
  setSelectedClinicianId,
  type Clinician,
} from "@/lib/clinicians";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/** "Dr. Amit Patel" → "AP"; "Sarah Chen" → "SC". */
function initialsOf(name: string): string {
  const stripped = name.replace(/^Dr\.\s+/i, "").trim();
  const parts = stripped.split(/\s+/).filter(Boolean);
  return parts
    .slice(0, 2)
    .map((p) => p.charAt(0).toUpperCase())
    .join("");
}

// useSyncExternalStore adapters — the switcher is driven by localStorage,
// which React treats as an external store. getServerSnapshot pins SSR and the
// first hydration render to CLINICIANS[0] so markup matches; React then swaps
// in the real value on the post-hydration re-render.
function subscribeClinician(cb: () => void) {
  return onClinicianChange(() => cb());
}
function getClinicianSnapshot() {
  return getSelectedClinicianId();
}
function getClinicianServerSnapshot() {
  return CLINICIANS[0].id;
}

export function ClinicianSwitcher() {
  const selectedId = React.useSyncExternalStore(
    subscribeClinician,
    getClinicianSnapshot,
    getClinicianServerSnapshot
  );

  const current: Clinician =
    CLINICIANS.find((c) => c.id === selectedId) ?? CLINICIANS[0];

  const handleSelect = (id: string) => {
    // setSelectedClinicianId dispatches the change event; useSyncExternalStore
    // picks it up and re-renders — no need to setState locally.
    setSelectedClinicianId(id);
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label="Switch clinician"
        className="flex items-center gap-2 rounded-md px-1.5 py-1 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B5FFF] focus-visible:ring-offset-1 focus-visible:ring-offset-white dark:focus-visible:ring-offset-slate-900"
      >
        <span
          aria-hidden="true"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#0B5FFF] text-[11px] font-semibold text-white"
        >
          {initialsOf(current.name)}
        </span>
        <span className="hidden sm:flex flex-col items-start leading-tight text-left">
          <span className="text-sm font-medium text-slate-900 dark:text-slate-50">
            {current.name}
          </span>
          <span className="text-[11px] text-slate-500 dark:text-slate-400">
            {current.role}
          </span>
        </span>
        <ChevronDown
          aria-hidden="true"
          className="h-4 w-4 text-slate-400 dark:text-slate-500"
        />
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" sideOffset={6} className="min-w-[240px]">
        {/* Base UI 1.4 requires GroupLabel to live inside a Group — rendering
            the label bare throws MenuGroupRootContext error #31 on open. */}
        <DropdownMenuGroup>
          <DropdownMenuLabel className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Signed in as
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          {CLINICIANS.map((c) => {
            const active = c.id === selectedId;
            return (
              <DropdownMenuItem
                key={c.id}
                onClick={() => handleSelect(c.id)}
                aria-label={`Switch to ${c.name}, ${c.role}`}
                className="flex items-start gap-2 py-1.5"
              >
                {/* Fixed-width check slot so rows don't shift when active changes. */}
                <span
                  aria-hidden="true"
                  className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center"
                >
                  {active ? (
                    <Check className="h-4 w-4 text-[#0B5FFF]" />
                  ) : null}
                </span>
                <span className="flex flex-col leading-tight">
                  <span className="text-sm font-medium text-slate-900 dark:text-slate-50">
                    {c.name}
                  </span>
                  <span className="text-[11px] text-slate-500 dark:text-slate-400">
                    {c.role}
                  </span>
                </span>
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
