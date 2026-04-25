"use client";

import * as React from "react";
import { Check } from "lucide-react";

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

/** Compact role chip — the design rules call for an UPPERCASE mono token. */
function shortRole(role: string): string {
  // Strip any trailing comma-detail and uppercase the leading 1–2 words.
  const head = role.split(/[,(—–-]/)[0].trim();
  const words = head.split(/\s+/).filter(Boolean);
  if (words.length === 0) return "";
  if (words[0].toLowerCase() === "rn") return "RN";
  if (words[0].toLowerCase() === "charge") return "CHARGE";
  if (words[0].toLowerCase() === "intensivist") return "ICU";
  if (words[0].toLowerCase() === "rapid") return "RAPID";
  return words[0].toUpperCase();
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
    setSelectedClinicianId(id);
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label="Switch clinician"
        className="clipill"
      >
        <span className="av" aria-hidden="true">
          {initialsOf(current.name)}
        </span>
        <span className="name">{current.name}</span>
        <span className="role">{shortRole(current.role)}</span>
      </DropdownMenuTrigger>

      <DropdownMenuContent
        align="end"
        sideOffset={6}
        className="min-w-[260px] p-0"
      >
        <DropdownMenuGroup>
          <DropdownMenuLabel className="text-[10px] uppercase tracking-wider text-[var(--fg-3)] px-3 pt-2 pb-1">
            Signed in as
          </DropdownMenuLabel>
          <DropdownMenuSeparator className="my-1" />
          {CLINICIANS.map((c) => {
            const active = c.id === selectedId;
            return (
              <DropdownMenuItem
                key={c.id}
                onClick={() => handleSelect(c.id)}
                aria-label={`Switch to ${c.name}, ${c.role}`}
                className="flex items-center gap-2.5 px-3 py-2 cursor-pointer"
              >
                <span
                  aria-hidden="true"
                  className="flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full text-[10px] font-semibold"
                  style={{
                    background: active ? "var(--ink-700)" : "var(--gray-200)",
                    color: active ? "#fff" : "var(--fg-2)",
                  }}
                >
                  {initialsOf(c.name)}
                </span>
                <span className="flex flex-col leading-tight flex-1 min-w-0">
                  <span className="text-[12px] font-medium text-[var(--fg-1)] truncate">
                    {c.name}
                  </span>
                </span>
                <span
                  className="text-[10px] uppercase tracking-wider text-[var(--fg-3)]"
                  style={{ fontFamily: "var(--font-mono)" }}
                >
                  {shortRole(c.role)}
                </span>
                <span
                  aria-hidden="true"
                  className="flex h-3 w-3 shrink-0 items-center justify-center"
                >
                  {active ? <Check className="h-3 w-3 text-[var(--ink-700)]" /> : null}
                </span>
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
