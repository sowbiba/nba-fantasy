import { frDayMonth } from "./date";

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

export function homeState(s: { hasNight: boolean; recCount: number; hasPick: boolean }) {
  if (!s.hasNight) return "no_games" as const;
  if (s.hasPick) return "picked" as const;
  if (s.recCount === 0) return "waiting_sync" as const;
  return "to_pick" as const;
}
