import { frDayMonth } from "./date";
import type { MatchupSeasonRow } from "@/types";

// Garde-fou d'affichage (pas une règle) : un joueur passé « Out » après la
// dernière synchro ne doit pas rester en tête / doit être signalé. Miroir de
// HARD_OUT_STATUSES (engine/stats/availability_prob.py).
export const HARD_OUT_STATUSES = new Set(["Out", "Doubtful", "Out For Season", "Suspended"]);

type RecS1 = { p_play: number | null; value: number | null; locked_until: string | null; best_future: string | null };

export function recMeta(rec: RecS1) {
  return {
    pPlay: rec.p_play === null ? null : `${Math.round(rec.p_play * 100)} %`,
    value: rec.value === null ? null : rec.value.toFixed(1),
    lockedUntil: rec.locked_until ? frDayMonth(rec.locked_until) : null,
    bestFuture: rec.best_future,
  };
}

/** Points affichés pour un pick scoré : score réel × 2 si x2, sinon tel quel. */
export function pickPoints(actualScore: number | null, isX2: boolean): number | null {
  return actualScore === null ? null : actualScore * (isX2 ? 2 : 1);
}

/** Défenseur principal (le plus présent) sur un joueur donné cette saison ; null si l'échantillon est trop faible (< 5 min). */
export function topDefender(rows: MatchupSeasonRow[]) {
  const total = rows.reduce((s, r) => s + r.minutes, 0);
  const top = [...rows].sort((a, b) => b.minutes - a.minutes)[0];
  if (!top || top.minutes < 5 || !top.def_player_name) return null;
  return {
    name: top.def_player_name,
    share: Math.round((top.minutes / total) * 100),
    per36: top.minutes > 0 ? Math.round((top.points / top.minutes) * 36 * 10) / 10 : null,
    games: top.games,
  };
}

export function homeState(s: { hasNight: boolean; recCount: number; hasPick: boolean }) {
  if (!s.hasNight) return "no_games" as const;
  if (s.hasPick) return "picked" as const;
  if (s.recCount === 0) return "waiting_sync" as const;
  return "to_pick" as const;
}
