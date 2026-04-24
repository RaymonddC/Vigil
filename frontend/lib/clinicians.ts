/**
 * Vigil doesn't own user identity — real deployments plug into the hospital
 * IdP (SMART-on-FHIR / OIDC). This hardcoded list is demo-only. IDs are
 * kebab-case to match HAPI-0521; they're what the approve endpoint at
 * `backend/api/routes/patients.py::approve_alert_action` accepts as
 * `clinician_id`.
 */

export type Clinician = {
  id: string;
  name: string;
  role: string;
};

export const CLINICIANS = [
  { id: "prac-nurse-17",   name: "Sarah Chen",       role: "RN, Post-op 4B" },
  { id: "prac-charge-02",  name: "Maya Lee",         role: "Charge Nurse" },
  { id: "prac-md-patel",   name: "Dr. Amit Patel",   role: "Intensivist" },
  { id: "prac-md-park",    name: "Dr. Lindsay Park", role: "Rapid Response" },
] as const satisfies readonly Clinician[];

const STORAGE_KEY = "vigil.selected_clinician_id";
const CHANGE_EVENT = "vigil:clinician-changed";

const KNOWN_IDS: ReadonlySet<string> = new Set(CLINICIANS.map((c) => c.id));

function isKnownId(id: string | null | undefined): id is string {
  return typeof id === "string" && KNOWN_IDS.has(id);
}

/**
 * Read the current selected clinician id from localStorage, falling back to
 * the first clinician if nothing is stored, the stored id is unknown, or we
 * are executing server-side (no `window`).
 */
export function getSelectedClinicianId(): string {
  const fallback = CLINICIANS[0].id;
  if (typeof window === "undefined") return fallback;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return isKnownId(stored) ? stored : fallback;
  } catch {
    // localStorage can throw in private mode / when disabled — silently fall back.
    return fallback;
  }
}

/** Return the full Clinician record for the currently selected id. */
export function getSelectedClinician(): Clinician {
  const id = getSelectedClinicianId();
  return CLINICIANS.find((c) => c.id === id) ?? CLINICIANS[0];
}

/**
 * Persist the selected clinician id. Rejects unknown ids silently (defensive:
 * callers should only ever pass ids from CLINICIANS). Dispatches a custom
 * event so same-tab subscribers update — the native `storage` event only
 * fires in *other* tabs.
 */
export function setSelectedClinicianId(id: string): void {
  if (!isKnownId(id)) return;
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // Storage quota / disabled — still fire the event so UI in this tab updates.
  }
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: { id } }));
}

/**
 * Subscribe to clinician changes. Listens to both the in-tab custom event and
 * the cross-tab `storage` event. Returns an unsubscribe function.
 */
export function onClinicianChange(cb: (id: string) => void): () => void {
  if (typeof window === "undefined") return () => {};

  const onCustom = (e: Event) => {
    const detail = (e as CustomEvent<{ id?: string }>).detail;
    if (detail && isKnownId(detail.id)) cb(detail.id);
  };
  const onStorage = (e: StorageEvent) => {
    if (e.key !== STORAGE_KEY) return;
    if (isKnownId(e.newValue)) cb(e.newValue);
  };

  window.addEventListener(CHANGE_EVENT, onCustom);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onCustom);
    window.removeEventListener("storage", onStorage);
  };
}
