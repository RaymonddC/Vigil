/**
 * Typed client for NEXT_PUBLIC_* environment variables.
 * Only NEXT_PUBLIC_ vars are accessible in the browser — no secrets here.
 */
export const env = {
  /** FastAPI backend base URL. Defaults to localhost:8000 in dev. */
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
} as const;

export type Env = typeof env;
