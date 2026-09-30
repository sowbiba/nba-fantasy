/** Journée NBA (heure de l'Est) : uniquement pour les vues de matchs en direct. */
export function todayNBA(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" });
}

/** Aujourd'hui à Paris. */
export function todayParis(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Europe/Paris" });
}

/**
 * Soirée du deck TTFL : le deck du jour D ferme à 00:00 heure de Paris (R8).
 * À toute heure de la journée D à Paris, la soirée à préparer est D.
 */
export function deckDate(now: Date = new Date()): string {
  return now.toLocaleDateString("en-CA", { timeZone: "Europe/Paris" });
}

export function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** Lundi de la semaine d'une date (semaines lundi → dimanche). */
export function weekStart(iso: string): string {
  const day = new Date(`${iso}T12:00:00Z`).getUTCDay(); // 0 = dimanche
  return addDays(iso, -((day + 6) % 7));
}

/** Saison NBA d'une date (à partir de septembre, la saison qui commence). */
export function seasonForDate(iso: string): string {
  const [y, m] = iso.split("-").map(Number);
  const start = m >= 9 ? y : y - 1;
  return `${start}-${String((start + 1) % 100).padStart(2, "0")}`;
}

export function frDayMonth(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}

export function frLongDate(iso: string): string {
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString("fr-FR", {
    weekday: "long", day: "numeric", month: "long", timeZone: "UTC",
  });
}

export function parisTime(isoTimestamp: string): string {
  return new Date(isoTimestamp).toLocaleTimeString("fr-FR", {
    hour: "2-digit", minute: "2-digit", timeZone: "Europe/Paris",
  });
}

/** « 1 octobre à 12:00 » (heure de Paris) — horodatage d'un prono. */
export function parisDateTime(isoTimestamp: string): string {
  const d = new Date(isoTimestamp);
  const day = d.toLocaleDateString("fr-FR", { day: "numeric", month: "long", timeZone: "Europe/Paris" });
  return `${day} à ${parisTime(isoTimestamp)}`;
}
