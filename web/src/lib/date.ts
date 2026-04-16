/**
 * Returns today's date as YYYY-MM-DD in Paris timezone.
 * The TTFL game day follows French time, not UTC.
 */
export function todayParis(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Europe/Paris" });
}
