// Page autonome « Scores TTFL par soirée » 2025-26 (/score-by-day-25-26) :
// helpers purs (paramètres, navigation entre soirées, lignes du tableau).
// Même périmètre que le jeu : matchs regular, cup_final et playoffs
// (engine/rules/game_types.py ELIGIBLE_TYPES) ; seuls les joueurs entrés en
// jeu (minutes > 0).

export const DAY_SEASON = "2025-26";
export const DAY_GAME_TYPES = ["regular", "cup_final", "playoffs"] as const;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export type DayParamsInput = { [key: string]: string | string[] | undefined };

export type DayParams = { date: string | null; team: string | null };

function first(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v;
}

/** `date` doit être une soirée connue (sinon la dernière soirée de la
 *  saison) ; `team` un code équipe connu (sinon toutes). `nights` trié
 *  par ordre croissant. */
export function parseDayParams(raw: DayParamsInput, nights: string[], teamCodes: readonly string[]): DayParams {
  const d = first(raw.date);
  const date = d && ISO_DATE.test(d) && nights.includes(d) ? d : (nights[nights.length - 1] ?? null);
  const t = first(raw.team)?.toUpperCase();
  const team = t && teamCodes.includes(t) ? t : null;
  return { date, team };
}

/** Soirées précédente et suivante (null aux extrémités). */
export function neighbors(nights: string[], date: string | null): { prev: string | null; next: string | null } {
  const i = date ? nights.indexOf(date) : -1;
  if (i < 0) return { prev: null, next: null };
  return { prev: i > 0 ? nights[i - 1] : null, next: i < nights.length - 1 ? nights[i + 1] : null };
}

/** Dates distinctes triées (entrées : une par match). */
export function distinctNights(dates: string[]): string[] {
  return [...new Set(dates)].sort();
}

export type DayLogInput = {
  player_id: number;
  team: string;
  is_home: boolean | null;
  minutes: number;
  pts: number;
  reb: number;
  ast: number;
  stl: number;
  blk: number;
  tov: number;
  fgm: number;
  fga: number;
  tpm: number;
  tpa: number;
  ftm: number;
  fta: number;
  ttfl_score: number;
  players: { name: string } | null;
  games: { home_team: string; away_team: string; game_type: string } | null;
};

export type DayRow = {
  playerId: number;
  name: string;
  team: string;
  opponent: string;
  home: boolean;
  gameType: string;
  minutes: number;
  pts: number;
  reb: number;
  ast: number;
  stl: number;
  blk: number;
  tov: number;
  fg: string;
  tp: string;
  ft: string;
  ttfl: number;
};

/** Lignes du tableau, triées par score TTFL décroissant (égalité : nom).
 *  Écarte les logs sans match joint ou d'un type de match hors jeu. */
export function toDayRows(logs: DayLogInput[]): DayRow[] {
  const types: readonly string[] = DAY_GAME_TYPES;
  return logs
    .filter((l) => l.games && types.includes(l.games.game_type) && l.minutes > 0)
    .map((l) => {
      const g = l.games!;
      const home = l.team === g.home_team;
      return {
        playerId: l.player_id,
        name: l.players?.name ?? `#${l.player_id}`,
        team: l.team,
        opponent: home ? g.away_team : g.home_team,
        home,
        gameType: g.game_type,
        minutes: l.minutes,
        pts: l.pts,
        reb: l.reb,
        ast: l.ast,
        stl: l.stl,
        blk: l.blk,
        tov: l.tov,
        fg: `${l.fgm}/${l.fga}`,
        tp: `${l.tpm}/${l.tpa}`,
        ft: `${l.ftm}/${l.fta}`,
        ttfl: l.ttfl_score,
      };
    })
    .sort((a, b) => b.ttfl - a.ttfl || a.name.localeCompare(b.name, "fr"));
}
