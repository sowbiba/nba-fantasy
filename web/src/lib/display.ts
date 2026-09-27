import { frDayMonth } from "./date";
import type { MatchupSeasonRow, StandingsRow } from "@/types";

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

/** Chance de victoire affichée (mode connecté, `game_predictions.home_win_prob`) :
 *  « 64 % », arrondi à l'entier, jamais de décimale. */
export function winPct(p: number): string {
  return `${Math.round(p * 100)} %`;
}

/** Paire domicile/extérieur affichée à partir de `home_win_prob` (M-10, review
 *  finale L3a) : l'extérieur = 100 − l'arrondi du domicile, jamais un arrondi
 *  indépendant de `1 - p` — sinon un match à 35.5 % peut afficher 36 % / 65 %
 *  (65 au lieu de 64) au lieu de 36 % / 64 %. */
export function winPctPair(homeProb: number): { home: string; away: string } {
  const home = Math.round(homeProb * 100);
  return { home: `${home} %`, away: `${100 - home} %` };
}

/** Opacité du fond de ligne du classement : dégressive sur 1-6, plus légère
 *  sur 7-10, nulle au-delà. Reste discrète par construction (jamais > 0.07). */
export function standingsTint(rank: number): number {
  if (rank >= 1 && rank <= 6) return 0.07 - (rank - 1) * 0.008;
  if (rank >= 7 && rank <= 10) return 0.02 - (rank - 7) * 0.0015;
  return 0;
}

/** Écart moyen affiché (`point_diff`) : toujours signé, jamais « -0.0 » pour
 *  une valeur qui arrondit à zéro. `point_diff` arrive en `numeric`
 *  Postgres (donc parfois en chaîne via PostgREST) : toujours passer par
 *  `Number(...)` ici plutôt que de faire confiance au type déclaré. */
export function formatPointDiff(n: number | string): string {
  const v = Number(n);
  const abs = Math.abs(v).toFixed(1);
  if (abs === "0.0") return "0.0";
  return v > 0 ? `+${abs}` : `-${abs}`;
}

/** Lecture de la colonne `streak` (`"V3"`, `"D1"`, `""`) en un score
 *  ordonnable : une série de victoires est positive (plus longue = plus
 *  grande), une série de défaites négative (plus longue = plus négative),
 *  pas de série (ou format inattendu) = 0. Sert le tri « meilleur d'abord »
 *  du classement (tâche 2) : score décroissant place les séries de
 *  victoires devant, la plus longue en tête, puis "" puis les séries de
 *  défaites, la plus courte en tête. */
export function streakScore(streak: string): number {
  const m = /^([VD])(\d+)$/.exec(streak);
  if (!m) return 0;
  const n = Number(m[2]);
  return m[1] === "V" ? n : -n;
}

/** Colonnes du classement sur lesquelles la tâche 2 permet de trier.
 *  `"force"` n'a de sens qu'en mode connecté (colonne `ratings` fournie par
 *  `ownerDb()`, jamais interrogée en mode public — StandingsTable ne rend
 *  le bouton de tri correspondant que si `ratings` est fourni). */
export type StandingsSortKey =
  | "rank"
  | "pct"
  | "wins"
  | "losses"
  | "games_behind"
  | "last10"
  | "streak"
  | "point_diff"
  | "force";

export type SortDir = "asc" | "desc";

/** Clés numériques comparées par `compareBestFirst` — `"force"` est géré à
 *  part dans `sortStandings` (valeurs manquantes toujours en fin de liste,
 *  quelle que soit la direction ; pas de valeur numérique unique sans
 *  `ratings`), donc jamais passé à `compareBestFirst`. */
type NumericSortKey = Exclude<StandingsSortKey, "force">;

/** Sens réel des valeurs affichées quand la colonne est triée « meilleur
 *  d'abord » (1er appui, `dir` interne = `"asc"`) : `true` = valeurs
 *  décroissantes (ex. V : le plus haut nombre de victoires en tête), `false`
 *  = valeurs croissantes (ex. D : le plus petit nombre de défaites en tête).
 *  Sert à afficher le bon `aria-sort`/▲▼ — l'état interne `dir` code
 *  « meilleur d'abord vs inversé », pas « croissant vs décroissant », ce qui
 *  diffère selon la colonne. `streak` est ordonné par `streakScore` (une
 *  série de victoires plus longue = un score plus haut = « décroissant »
 *  au sens de ce score, même si le libellé affiché n'est pas un nombre). */
const BEST_FIRST_IS_DESCENDING: Record<StandingsSortKey, boolean> = {
  rank: false,
  wins: true,
  losses: false,
  pct: true,
  games_behind: false,
  last10: true,
  streak: true,
  point_diff: true,
  force: true,
};

export function bestFirstIsDescending(key: StandingsSortKey): boolean {
  return BEST_FIRST_IS_DESCENDING[key];
}

/** Direction réellement affichée (pour `aria-sort` et l'indicateur ▲/▼) à
 *  partir de la direction interne du tri (`"asc"` = 1er appui/meilleur
 *  d'abord, `"desc"` = 2e appui/inversé) : contrairement à `dir`, celle-ci
 *  correspond au sens effectif des valeurs de la colonne, qui dépend de la
 *  colonne (V trié meilleur d'abord affiche du plus grand au plus petit :
 *  `"desc"` ; D trié meilleur d'abord affiche du plus petit au plus grand :
 *  `"asc"`). */
export function displayedSortDir(key: StandingsSortKey, dir: SortDir): SortDir {
  const bestFirstDir: SortDir = bestFirstIsDescending(key) ? "desc" : "asc";
  if (dir === "asc") return bestFirstDir;
  return bestFirstDir === "asc" ? "desc" : "asc";
}

/** Comparaison « meilleur d'abord » (indépendante de la direction affichée) :
 *  négatif si `a` doit passer avant `b`. `dir` inverse ensuite ce résultat
 *  (2e appui = sens inverse) sans jamais casser la stabilité du départage
 *  par rang officiel. */
function compareBestFirst(key: NumericSortKey, a: StandingsRow, b: StandingsRow): number {
  switch (key) {
    case "rank":
      return a.rank - b.rank;
    case "pct":
      return Number(b.pct) - Number(a.pct);
    case "wins":
      return b.wins - a.wins;
    case "losses":
      return a.losses - b.losses;
    case "games_behind":
      return Number(a.games_behind) - Number(b.games_behind);
    case "last10":
      return b.last10_wins - a.last10_wins;
    case "streak":
      return streakScore(b.streak) - streakScore(a.streak);
    case "point_diff":
      return Number(b.point_diff) - Number(a.point_diff);
  }
}

/** Tri pur du classement (tâche 2/3) : ne mute jamais `rows`, départage
 *  toujours par rang officiel (`a.rank - b.rank`) à égalité — y compris pour
 *  les lignes sans cote (`force`), qui restent en fin de liste dans les deux
 *  sens de tri. `ratings` (Force, mode connecté seulement) est ignoré pour
 *  toute autre clé. */
export function sortStandings(
  rows: StandingsRow[],
  key: StandingsSortKey,
  dir: SortDir,
  ratings?: Record<string, number> | null,
): StandingsRow[] {
  const sign = dir === "desc" ? -1 : 1;
  return [...rows].sort((a, b) => {
    if (key === "force") {
      const ra = ratings?.[a.team];
      const rb = ratings?.[b.team];
      const aMissing = ra === undefined || ra === null;
      const bMissing = rb === undefined || rb === null;
      if (aMissing && bMissing) return a.rank - b.rank;
      if (aMissing) return 1;
      if (bMissing) return -1;
      const primary = sign * (rb - ra);
      return primary !== 0 ? primary : a.rank - b.rank;
    }
    const primary = sign * compareBestFirst(key, a, b);
    return primary !== 0 ? primary : a.rank - b.rank;
  });
}
