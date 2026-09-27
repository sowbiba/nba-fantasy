import { HARD_OUT_STATUSES } from "@/lib/display";
import { parisTime } from "@/lib/date";

export type Reminder = { kind: "no_pick_2h" | "no_pick_30m" | "injury"; key: string; title: string; body: string };

const H2 = 2 * 60 * 60 * 1000;
const M30 = 30 * 60 * 1000;
const INJURY_ALERT_START_MIN = 7 * 60; // 07:00 Paris (M3, revue finale)

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
  } else if (pick.injuryStatus && HARD_OUT_STATUSES.has(pick.injuryStatus) && parisMinutesOfDay(now) >= INJURY_ALERT_START_MIN) {
    const key = `${pick.playerId}:${pick.injuryStatus}`;
    if (!sent.has(`injury|${key}`)) {
      out.push({ kind: "injury", key, title: `${pick.name} : ${pick.injuryStatus}`,
                 body: `Ton pick de ce soir est ${pick.injuryStatus}. Change avant ${at}.` });
    }
  }
  return out;
}
