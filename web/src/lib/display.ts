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

/** R8 : la soirée est fermée dès que `closingAt` (nights.closing_at, minuit
 *  Paris ou premier tip-off si plus tôt) est atteint ou dépassé. Pas de
 *  closingAt connu (ex. pas de ligne nights) : on ne bloque pas ici. */
export function isClosed(closingAt: string | null | undefined, now: Date = new Date()): boolean {
  if (!closingAt) return false;
  return now.getTime() >= new Date(closingAt).getTime();
}

/** Suggestion du x2 (plan indicatif) : le pick "meilleur dispo" du soir ne change pas.
 *  Sans pick : "pose" = le plan suggère un x2 ce soir (sur son joueur).
 *  Avec un pick : le moteur replanifie sur le pick de l'utilisateur, donc on ne suit la décision
 *  du plan que si son joueur EST le pick ("pose_sur_pick", ou "deja" si le x2 est déjà posé) ;
 *  sinon (plan d'une synchro antérieure au pick) rien à afficher. null aussi si pas de
 *  suggestion ou mois interdit. Miroir informatif de is_x2 (plan, migrations 019/021) — la
 *  contrainte réelle (un x2 par mois calendaire) reste en base (picks_x2_month, migration 021). */
export type X2HintKind = "pose" | "pose_sur_pick" | "deja";

export function x2Hint(input: {
  planIsX2: boolean; planPlayerId: number | null; pickPlayerId: number | null; pickIsX2: boolean; x2Allowed: boolean;
}): X2HintKind | null {
  if (!input.planIsX2 || !input.x2Allowed) return null;
  if (input.pickPlayerId === null) return "pose";
  if (input.planPlayerId !== input.pickPlayerId) return null;
  return input.pickIsX2 ? "deja" : "pose_sur_pick";
}

/** Texte du bandeau x2 ; sans nom de joueur connu (joueur absent de `players`), la phrase
 *  reste correcte sans le nom (jamais "undefined"). */
export function x2HintText(kind: X2HintKind, planPlayerName?: string | null): string {
  if (kind === "deja") return "x2 activé sur ton pick, comme le suggère le plan pour ce soir.";
  if (kind === "pose_sur_pick") return "Le plan suggère le x2 ce soir sur ton pick : active-le ci-dessous.";
  return planPlayerName ? `Le plan suggère un x2 ce soir (sur ${planPlayerName}).` : "Le plan suggère un x2 ce soir.";
}

export function homeState(s: { hasNight: boolean; recCount: number; hasPick: boolean }) {
  if (!s.hasNight) return "no_games" as const;
  if (s.hasPick) return "picked" as const;
  if (s.recCount === 0) return "waiting_sync" as const;
  return "to_pick" as const;
}

/** Zone du classement (tâche 5) : 1-6 playoffs direct, 7-10 play-in, sinon
 *  aucune zone. Purement informatif (le tri officiel départage autrement) —
 *  jamais de rouge/vert franc à l'affichage, juste une teinte discrète. */
export function standingsZone(rank: number): "playoffs" | "playin" | null {
  if (rank >= 1 && rank <= 6) return "playoffs";
  if (rank >= 7 && rank <= 10) return "playin";
  return null;
}

/** Opacité du fond de ligne du classement : dégressive sur 1-6, plus légère
 *  sur 7-10, nulle au-delà. Reste discrète par construction (jamais > 0.07). */
export function standingsTint(rank: number): number {
  if (rank >= 1 && rank <= 6) return 0.07 - (rank - 1) * 0.008;
  if (rank >= 7 && rank <= 10) return 0.02 - (rank - 7) * 0.0015;
  return 0;
}
