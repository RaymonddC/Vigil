/**
 * Format elapsed minutes as "HH:MM" for the T+ OR column.
 * Pass timestamp as a pre-formatted string from server to avoid hydration issues.
 */
export function formatTimeSince(isoTimestamp: string): string {
  const then = new Date(isoTimestamp).getTime();
  const now = Date.now();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60_000);
  const h = Math.floor(diffMin / 60);
  const m = diffMin % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

/**
 * Format a duration in seconds as "MM:SS" for countdown timers.
 */
export function formatCountdown(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

/**
 * Format a date as a short time string "HH:MM" (24h).
 * Use pre-formatted string on server to avoid hydration mismatches.
 */
export function formatTime(isoTimestamp: string): string {
  const d = new Date(isoTimestamp);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/**
 * Tabular number formatter for vitals / MRN columns.
 * Returns string with tabular numeral feature hint.
 */
export function tabularNum(value: number, decimals = 0): string {
  return value.toFixed(decimals);
}
