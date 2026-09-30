// Scores TTFL 2025-26 (page publique autonome `/scores-25-26`, tâche 4) :
// logique pure (validation des paramètres d'URL, tri, génération du CSV
// d'export) — testée dans scores.test.ts, aucun accès réseau/BD ici. La
// page et la route d'export (`export/route.ts`) partagent ce module pour
// rester cohérentes l'une avec l'autre.

export const SEASON = "2025-26";

export type GameType = "regular" | "playoffs";

export const GAME_TYPES: { value: GameType; label: string }[] = [
  { value: "regular", label: "Saison régulière" },
  { value: "playoffs", label: "Playoffs" },
];

const GAME_TYPE_VALUES: GameType[] = ["regular", "playoffs"];

/** Minimum de matchs par défaut, différent en playoffs (bien moins de
 *  matchs disponibles qu'en saison régulière) — décision de la revue du
 *  concepteur (addendum tâche 4), modifiable par l'utilisateur (1-82). */
export const DEFAULT_MIN_GAMES: Record<GameType, number> = {
  regular: 20,
  playoffs: 5,
};

export type SortKey = "avg" | "top";
export type SortDir = "asc" | "desc";

const SORT_KEYS: SortKey[] = ["avg", "top"];
const SORT_DIRS: SortDir[] = ["asc", "desc"];

export type ScoresParams = {
  type: GameType;
  /** null = toutes les équipes. */
  team: string | null;
  minGames: number;
  sortKey: SortKey;
  sortDir: SortDir;
};

/** Une valeur de paramètre telle qu'elle arrive depuis `URLSearchParams`
 *  côté route (une seule valeur) ou `searchParams` côté page Next
 *  (`string | string[] | undefined` — un paramètre répété dans l'URL donne
 *  un tableau). */
export type ParamValue = string | string[] | undefined | null;

export type ParamsInput = {
  type?: ParamValue;
  team?: ParamValue;
  min?: ParamValue;
  sort?: ParamValue;
  dir?: ParamValue;
};

export type ParseScoresParamsResult = {
  params: ScoresParams;
  /** Noms des paramètres reçus mais invalides (retombés sur leur défaut) —
   *  absent/vide n'est jamais une erreur. Sert à décider un 400 côté route
   *  d'export sans dupliquer la validation (voir addendum : « invalid → 400
   *  or fall back to defaults, be consistent with the page »). La page
   *  ignore ce champ et affiche simplement les valeurs corrigées ; la route
   *  d'export, elle, renvoie 400 dès que `invalid` n'est pas vide. */
  invalid: string[];
};

function first(value: ParamValue): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

/** Valide/normalise les paramètres venant de l'URL. */
export function parseScoresParams(input: ParamsInput, knownTeams: readonly string[]): ParseScoresParamsResult {
  const invalid: string[] = [];

  const typeRaw = first(input.type);
  let type: GameType = "regular";
  if (typeRaw !== "") {
    if (GAME_TYPE_VALUES.includes(typeRaw as GameType)) {
      type = typeRaw as GameType;
    } else {
      invalid.push("type");
    }
  }

  const teamRaw = first(input.team).toUpperCase().trim();
  let team: string | null = null;
  if (teamRaw !== "") {
    if (knownTeams.includes(teamRaw)) {
      team = teamRaw;
    } else {
      invalid.push("team");
    }
  }

  const minRaw = first(input.min).trim();
  let minGames = DEFAULT_MIN_GAMES[type];
  if (minRaw !== "") {
    const minParsed = /^\d+$/.test(minRaw) ? Number(minRaw) : NaN;
    if (Number.isInteger(minParsed) && minParsed >= 1 && minParsed <= 82) {
      minGames = minParsed;
    } else {
      invalid.push("min");
    }
  }

  const sortRaw = first(input.sort);
  let sortKey: SortKey = "avg";
  if (sortRaw !== "") {
    if (SORT_KEYS.includes(sortRaw as SortKey)) {
      sortKey = sortRaw as SortKey;
    } else {
      invalid.push("sort");
    }
  }

  const dirRaw = first(input.dir);
  let sortDir: SortDir = "desc";
  if (dirRaw !== "") {
    if (SORT_DIRS.includes(dirRaw as SortDir)) {
      sortDir = dirRaw as SortDir;
    } else {
      invalid.push("dir");
    }
  }

  return { params: { type, team, minGames, sortKey, sortDir }, invalid };
}

export type ScoreRow = {
  playerId: number;
  name: string;
  team: string;
  games: number;
  avgTtfl: number;
  totalTtfl: number;
  topScore: number;
  /** Date ISO (YYYY-MM-DD) du meilleur match. */
  topDate: string;
  topOpponent: string;
};

/** Tri pur (tâche 4) : ne mute jamais `rows`. Les deux colonnes triables
 *  (moyenne, top score) sont toujours « plus haut = meilleur », donc `dir`
 *  représente directement le sens affiché (pas d'inversion « meilleur
 *  d'abord » à la StandingsTable). Départage stable, jamais inversé par
 *  `dir` : l'autre colonne numérique, puis le nom (alphabétique FR), pour
 *  qu'un tri ne change jamais d'ordre entre deux rendus à données égales. */
export function sortScores(rows: ScoreRow[], key: SortKey, dir: SortDir): ScoreRow[] {
  const sign = dir === "desc" ? -1 : 1;
  return [...rows].sort((a, b) => {
    const primary = sign * (key === "avg" ? a.avgTtfl - b.avgTtfl : a.topScore - b.topScore);
    if (primary !== 0) return primary;
    const secondary = key === "avg" ? b.topScore - a.topScore : b.avgTtfl - a.avgTtfl;
    if (secondary !== 0) return secondary;
    return a.name.localeCompare(b.name, "fr");
  });
}

/** `avg_ttfl` peut arriver en `number` ou en `string` (PostgREST sérialise
 *  parfois un `numeric` Postgres en chaîne) — toujours passer par `Number`
 *  avant de formater. */
export function decimalComma(value: number | string, decimals = 1): string {
  return Number(value).toFixed(decimals).replace(".", ",");
}

/** jj/mm à partir d'une date ISO (YYYY-MM-DD...) — même format que
 *  `frDayMonth` (@/lib/date), dupliqué ici pour garder `scores.ts` sans
 *  dépendance (module pur, testé isolément). */
export function dateFrCourt(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${m[3]}/${m[2]}`;
}

// Neutralise l'injection de formule CSV (Excel/Sheets exécutent un champ
// commençant par ces caractères comme une formule) : les noms de joueurs
// viennent du flux NBA, jamais saisis par un utilisateur de ce site, mais
// on reste défensif (addendum tâche 4).
const FORMULA_PREFIX_RE = /^[=+\-@]/;
const NEEDS_QUOTING_RE = /[;"\r\n]/;

/** Échappe un champ CSV : garde anti-formule d'abord (apostrophe), puis
 *  guillemets si le champ contient `;`, `"`, CR ou LF (guillemets internes
 *  doublés). */
export function csvField(raw: string): string {
  let value = raw;
  if (FORMULA_PREFIX_RE.test(value)) {
    value = "'" + value;
  }
  if (NEEDS_QUOTING_RE.test(value)) {
    value = '"' + value.replace(/"/g, '""') + '"';
  }
  return value;
}

const CSV_HEADER = ["Joueur", "Équipe", "Matchs", "Moyenne TTFL", "Top", "Date du top", "Adversaire du top"];

/** Construit le CSV complet (BOM UTF-8 + en-tête FR + lignes), séparateur
 *  `;`, fin de ligne CRLF, décimale virgule (Excel FR). */
export function buildScoresCsv(rows: ScoreRow[]): string {
  const lines = [CSV_HEADER.map(csvField).join(";")];
  for (const r of rows) {
    lines.push(
      [
        csvField(r.name),
        csvField(r.team),
        csvField(String(r.games)),
        csvField(decimalComma(r.avgTtfl)),
        csvField(String(r.topScore)),
        csvField(dateFrCourt(r.topDate)),
        csvField(r.topOpponent),
      ].join(";"),
    );
  }
  return "﻿" + lines.join("\r\n") + "\r\n";
}

/** `scores-ttfl-2025-26-<type>[-<équipe>].csv` (addendum tâche 4). */
export function csvFilename(type: GameType, team: string | null): string {
  const parts = ["scores-ttfl-2025-26", type];
  if (team) parts.push(team.toLowerCase());
  return parts.join("-") + ".csv";
}
