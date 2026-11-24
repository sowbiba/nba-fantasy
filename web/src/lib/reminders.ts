import { frDayMonth, parisTime } from "@/lib/date";

export type Reminder = { kind: "no_pick_2h" | "no_pick_30m"; key: string; title: string; body: string };

const H2 = 2 * 60 * 60 * 1000;
const M30 = 30 * 60 * 1000;
const INJURY_ALERT_START_MIN = 7 * 60; // 07:00 Paris (M3, revue finale) : pas d'alerte deck la nuit

/** Minutes écoulées depuis 00:00 heure de Paris (DST-safe, via Intl). */
function parisMinutesOfDay(d: Date): number {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Paris", hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(d);
  const h = Number(parts.find((p) => p.type === "hour")?.value ?? "0") % 24;
  const m = Number(parts.find((p) => p.type === "minute")?.value ?? "0");
  return h * 60 + m;
}

export function dueReminders(input: {
  now: Date;
  night: { date: string; closing_at: string } | null;
  pick: { playerId: number; name: string; injuryStatus: string | null } | null;
  sent: Set<string>;
}): Reminder[] {
  const { now, night, pick, sent } = input;
  if (!night) return [];
  const closing = new Date(night.closing_at).getTime();
  const t = now.getTime();
  if (t >= closing) return [];
  const at = parisTime(night.closing_at);
  const out: Reminder[] = [];
  if (!pick) {
    const kind = t >= closing - M30 ? "no_pick_30m" : t >= closing - H2 ? "no_pick_2h" : null;
    if (kind && !sent.has(`${kind}|`)) {
      out.push({ kind, key: "", title: "Pas de pick ce soir", body: `Le deck ferme à ${at}.` });
    }
  }
  // L'alerte blessure du pick du soir est faite par deckAlerts (tout statut,
  // sur 7 jours, avec la proposition du moteur).
  return out;
}

/** Vérification du deck sur 7 jours (24/11/2026) : à chaque passage, chaque
 *  pick du deck est comparé à la proposition du moteur (dernier plan, ou
 *  reco n°1 le soir même). Alerte si le joueur est signalé blessé, ou si le
 *  moteur propose quelqu'un d'autre (il ne le fait qu'au-delà de sa marge de
 *  3 points). Une alerte par changement (clé dédupliquée par soirée). */
const fr1 = (x: number) => x.toFixed(1).replace(".", ",");

export type DeckEntry = {
  night: string;
  closingAt: string;
  pick: { playerId: number; name: string; injuryStatus: string | null } | null;
  proposal: { playerId: number; name: string; expected: number } | null;
};

export type DeckAlert = { kind: "deck_injury" | "deck_change"; night: string; key: string; title: string; body: string };

export function deckAlerts(input: { now: Date; entries: DeckEntry[]; sent: Set<string> }): DeckAlert[] {
  const { now, entries, sent } = input;
  if (parisMinutesOfDay(now) < INJURY_ALERT_START_MIN) return [];
  const out: DeckAlert[] = [];
  for (const e of entries) {
    if (!e.pick || now.getTime() >= new Date(e.closingAt).getTime()) continue;
    const day = frDayMonth(e.night);
    const p = e.pick;
    const other = e.proposal && e.proposal.playerId !== p.playerId ? e.proposal : null;
    // Pas de proposition (soirée x2 réservée, absente du plan ; recos du
    // soir pas encore calculées) : ne pas prétendre que le moteur le garde.
    const proposalText = other
      ? `Le moteur propose ${other.name} (≈ ${fr1(other.expected)}).`
      : e.proposal
        ? "Le moteur le garde pour l'instant."
        : "Pas de proposition du moteur pour cette soirée : vérifie les recos dans l'app.";
    let alert: DeckAlert | null = null;
    if (p.injuryStatus) {
      alert = { kind: "deck_injury", night: e.night, key: `${p.playerId}:${p.injuryStatus}`,
                title: `Deck ${day} : ${p.name} (${p.injuryStatus})`,
                body: `${proposalText} Le deck ferme à ${parisTime(e.closingAt)} le ${day}.` };
    } else if (other) {
      alert = { kind: "deck_change", night: e.night, key: `${p.playerId}>${other.playerId}`,
                title: `Deck ${day} : changement proposé`,
                body: `Le moteur propose ${other.name} (≈ ${fr1(other.expected)}) à la place de ${p.name}.` };
    }
    if (alert && !sent.has(`${alert.night}|${alert.kind}|${alert.key}`)) out.push(alert);
  }
  return out;
}
