/**
 * FHIR-source toggle (portfolio play): pick where the dashboard reads FHIR
 * data from. Mirrors the persisted-settings pattern in `clinicians.ts` —
 * three independent values (source id, PO URL, PO token), each with
 * `get` / `set` / `onChange`, backed by `localStorage` and a same-tab
 * `CustomEvent` so subscribers update without a refresh. The `storage`
 * event covers cross-tab sync.
 *
 * Cookie mirror (source + URL only — token is never mirrored): so server
 * components in `next/headers` can read the choice during RSC render. The
 * token never leaves the browser via SSR; client-side fetches inject it
 * directly from localStorage.
 */
export type FhirSourceId = "hapi" | "po";

export type FhirSource = {
  id: FhirSourceId;
  label: string;
  description: string;
  /** Whether the dashboard's Approve flow is allowed against this source. */
  writesAllowed: boolean;
};

export const FHIR_SOURCES = [
  {
    id: "hapi",
    label: "Local HAPI",
    description: "Default — the bundled HAPI FHIR R4 server seeded with synthetic patients.",
    writesAllowed: true,
  },
  {
    id: "po",
    label: "Prompt Opinion",
    description: "Read live FHIR from a Prompt Opinion workspace (read-only — Approve disabled).",
    writesAllowed: false,
  },
] as const satisfies readonly FhirSource[];

const SOURCE_STORAGE_KEY = "vigil.selected_fhir_source";
const URL_STORAGE_KEY = "vigil.po_fhir_url";
const TOKEN_STORAGE_KEY = "vigil.po_fhir_token";

const SOURCE_CHANGE_EVENT = "vigil:fhir-source-changed";
const URL_CHANGE_EVENT = "vigil:fhir-url-changed";
const TOKEN_CHANGE_EVENT = "vigil:fhir-token-changed";

const SOURCE_COOKIE = "vigil_fhir_source";
const URL_COOKIE = "vigil_fhir_url";

const KNOWN_SOURCE_IDS: ReadonlySet<string> = new Set(
  FHIR_SOURCES.map((s) => s.id)
);

const DEFAULT_SOURCE_ID: FhirSourceId = "hapi";

function isKnownSourceId(id: string | null | undefined): id is FhirSourceId {
  return typeof id === "string" && KNOWN_SOURCE_IDS.has(id);
}

/**
 * Cookie mirror — readable from `next/headers` cookies() during RSC.
 * 30-day expiry, `Lax` to ride along with same-site fetches, `Path=/`.
 * Empty value clears the cookie.
 */
function setCookieMirror(name: string, value: string): void {
  if (typeof document === "undefined") return;
  try {
    const enc = encodeURIComponent(value);
    if (value === "") {
      document.cookie = `${name}=; Path=/; Max-Age=0; SameSite=Lax`;
    } else {
      const maxAge = 60 * 60 * 24 * 30; // 30 days
      document.cookie = `${name}=${enc}; Path=/; Max-Age=${maxAge}; SameSite=Lax`;
    }
  } catch {
    // Document/cookie disabled — silently ignore.
  }
}

// ---------------------------------------------------------------------------
// Source id
// ---------------------------------------------------------------------------

export function getSelectedFhirSourceId(): FhirSourceId {
  if (typeof window === "undefined") return DEFAULT_SOURCE_ID;
  try {
    const stored = window.localStorage.getItem(SOURCE_STORAGE_KEY);
    return isKnownSourceId(stored) ? stored : DEFAULT_SOURCE_ID;
  } catch {
    return DEFAULT_SOURCE_ID;
  }
}

export function getSelectedFhirSource(): FhirSource {
  const id = getSelectedFhirSourceId();
  return FHIR_SOURCES.find((s) => s.id === id) ?? FHIR_SOURCES[0];
}

export function setSelectedFhirSourceId(id: string): void {
  if (!isKnownSourceId(id)) return;
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(SOURCE_STORAGE_KEY, id);
  } catch {
    /* localStorage disabled — still fire event + cookie below */
  }
  setCookieMirror(SOURCE_COOKIE, id);
  window.dispatchEvent(new CustomEvent(SOURCE_CHANGE_EVENT, { detail: { id } }));
}

export function onFhirSourceChange(
  cb: (id: FhirSourceId) => void
): () => void {
  if (typeof window === "undefined") return () => {};

  const onCustom = (e: Event) => {
    const detail = (e as CustomEvent<{ id?: string }>).detail;
    if (detail && isKnownSourceId(detail.id)) cb(detail.id);
  };
  const onStorage = (e: StorageEvent) => {
    if (e.key !== SOURCE_STORAGE_KEY) return;
    if (isKnownSourceId(e.newValue)) cb(e.newValue);
  };

  window.addEventListener(SOURCE_CHANGE_EVENT, onCustom);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(SOURCE_CHANGE_EVENT, onCustom);
    window.removeEventListener("storage", onStorage);
  };
}

// ---------------------------------------------------------------------------
// PO FHIR URL
// ---------------------------------------------------------------------------

export function getPoFhirUrl(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(URL_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setPoFhirUrl(url: string): void {
  if (typeof window === "undefined") return;
  const trimmed = (url ?? "").trim();
  try {
    if (trimmed === "") {
      window.localStorage.removeItem(URL_STORAGE_KEY);
    } else {
      window.localStorage.setItem(URL_STORAGE_KEY, trimmed);
    }
  } catch {
    /* localStorage disabled — still fire event + cookie below */
  }
  setCookieMirror(URL_COOKIE, trimmed);
  window.dispatchEvent(
    new CustomEvent(URL_CHANGE_EVENT, { detail: { url: trimmed } })
  );
}

export function onPoFhirUrlChange(cb: (url: string) => void): () => void {
  if (typeof window === "undefined") return () => {};

  const onCustom = (e: Event) => {
    const detail = (e as CustomEvent<{ url?: string }>).detail;
    if (detail && typeof detail.url === "string") cb(detail.url);
  };
  const onStorage = (e: StorageEvent) => {
    if (e.key !== URL_STORAGE_KEY) return;
    cb(e.newValue ?? "");
  };

  window.addEventListener(URL_CHANGE_EVENT, onCustom);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(URL_CHANGE_EVENT, onCustom);
    window.removeEventListener("storage", onStorage);
  };
}

// ---------------------------------------------------------------------------
// PO bearer token (NEVER mirrored to cookie — only injected on client fetches)
// ---------------------------------------------------------------------------

export function getPoFhirToken(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setPoFhirToken(token: string): void {
  if (typeof window === "undefined") return;
  const trimmed = (token ?? "").trim();
  try {
    if (trimmed === "") {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    } else {
      window.localStorage.setItem(TOKEN_STORAGE_KEY, trimmed);
    }
  } catch {
    /* localStorage disabled — still fire event so listeners update */
  }
  // Token is intentionally NOT written to cookie.
  window.dispatchEvent(
    new CustomEvent(TOKEN_CHANGE_EVENT, { detail: { hasToken: trimmed !== "" } })
  );
}

export function onPoFhirTokenChange(cb: (hasToken: boolean) => void): () => void {
  if (typeof window === "undefined") return () => {};

  const onCustom = (e: Event) => {
    const detail = (e as CustomEvent<{ hasToken?: boolean }>).detail;
    if (detail && typeof detail.hasToken === "boolean") cb(detail.hasToken);
  };
  const onStorage = (e: StorageEvent) => {
    if (e.key !== TOKEN_STORAGE_KEY) return;
    cb((e.newValue ?? "") !== "");
  };

  window.addEventListener(TOKEN_CHANGE_EVENT, onCustom);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(TOKEN_CHANGE_EVENT, onCustom);
    window.removeEventListener("storage", onStorage);
  };
}

// ---------------------------------------------------------------------------
// Convenience getter — what the API client needs to populate headers.
// ---------------------------------------------------------------------------

export type FhirHeaderValues = {
  source: FhirSourceId;
  url: string;
  token: string;
};

export function getFhirHeaderValues(): FhirHeaderValues {
  return {
    source: getSelectedFhirSourceId(),
    url: getPoFhirUrl(),
    token: getPoFhirToken(),
  };
}
