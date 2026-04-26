"use client";

import * as React from "react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import {
  CLINICIANS,
  getSelectedClinicianId,
  onClinicianChange,
  type Clinician,
} from "@/lib/clinicians";
import {
  getSelectedFhirSourceId,
  onFhirSourceChange,
  type FhirSourceId,
} from "@/lib/fhir-sources";
import { ackAlert } from "@/lib/api";

const APPROVE_DISABLED_TITLE =
  "Approval is disabled when reading from an external FHIR source. Switch to local HAPI to acknowledge alerts.";

function initialsOf(name: string): string {
  const stripped = name.replace(/^Dr\.\s+/i, "").trim();
  return stripped
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p.charAt(0).toUpperCase())
    .join("");
}

function nowHHMM(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** Subscribe to clinician selection. SSR-safe: returns CLINICIANS[0] on the server. */
function useCurrentClinician(): Clinician {
  const id = React.useSyncExternalStore(
    (cb) => onClinicianChange(() => cb()),
    () => getSelectedClinicianId(),
    () => CLINICIANS[0].id
  );
  return CLINICIANS.find((c) => c.id === id) ?? CLINICIANS[0];
}

/** Subscribe to FHIR-source selection. SSR-safe: returns "hapi" on the server. */
function useCurrentFhirSource(): FhirSourceId {
  return React.useSyncExternalStore(
    (cb) => onFhirSourceChange(() => cb()),
    () => getSelectedFhirSourceId(),
    () => "hapi"
  );
}

export interface ApproveBarProps {
  patientId: string;
  alertId: string;
  /** When true, render the green attribution toast pre-approved (no buttons). */
  initialApproved?: boolean;
  /** Called after a successful approval so the parent can swap SBAR tag. */
  onApproved?: () => void;
}

/**
 * ApproveBar — the demo's emotional climax. Until the clinician taps Approve,
 * shows Dismiss / Edit draft / Approve handoff buttons. After approval, the
 * whole bar is replaced with the green `.attr-toast` clinical attribution
 * line: "Approved by {Full name} · {HH:MM} · written to EHR".
 */
export function ApproveBar({
  patientId,
  alertId,
  initialApproved = false,
  onApproved,
}: ApproveBarProps) {
  const clinician = useCurrentClinician();
  const fhirSource = useCurrentFhirSource();
  const router = useRouter();
  const [approved, setApproved] = React.useState(initialApproved);
  const [approvedAt, setApprovedAt] = React.useState<string>("");
  const [pending, setPending] = React.useState(false);

  const writesBlocked = fhirSource !== "hapi";

  // Per-clinician "full name" string. The brief is exact about this copy.
  const fullName = React.useMemo(() => clinician.name, [clinician]);

  async function handleApprove() {
    if (pending || approved || writesBlocked) return;
    setPending(true);
    try {
      const res = await ackAlert(patientId, alertId);
      const stamp = nowHHMM();
      setApproved(true);
      setApprovedAt(stamp);
      toast.success(`Handoff written to EHR for ${patientId}.`, {
        description: `Audit ${res.audit_id.slice(0, 10)}`,
        duration: 4500,
      });
      onApproved?.();
      router.refresh();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Write failed — retry";
      toast.error(msg);
    } finally {
      setPending(false);
    }
  }

  function handleDismiss() {
    toast.message("Alert dismissed", {
      description: "No write to EHR. The agent will continue watching.",
      duration: 3000,
    });
  }

  if (approved) {
    return (
      <div className="attr-toast" role="status" aria-live="polite">
        <span className="av" aria-hidden="true">
          {initialsOf(fullName)}
        </span>
        <span className="txt">
          Approved by {fullName} · {approvedAt || nowHHMM()} · written to EHR
        </span>
      </div>
    );
  }

  return (
    <div className="approve-bar">
      <button type="button" className="btn" onClick={handleDismiss} disabled={pending}>
        Dismiss
      </button>
      <span className="grow" />
      <button type="button" className="btn btn--ghost btn--sm" disabled={pending}>
        Edit draft
      </button>
      <button
        type="button"
        className="btn btn--primary btn--lg"
        onClick={handleApprove}
        disabled={pending || writesBlocked}
        aria-busy={pending}
        title={writesBlocked ? APPROVE_DISABLED_TITLE : undefined}
      >
        {pending ? "Approving…" : "Approve handoff →"}
      </button>
    </div>
  );
}
