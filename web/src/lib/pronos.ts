// Pronos 2026-27 : logique pure (aucun accès réseau/BD ici), testée dans
// pronos.test.ts. `web/src/app/pronos-26-27/actions.ts` s'appuie dessus
// pour la validation et le calcul du classement en direct.

export type Conference = "Est" | "Ouest";

export type Team = { code: string; conference: Conference };

/** Même répartition Est/Ouest que la vue SQL `standings` (migrations
 *  027/029/031) — à garder synchronisée si l'une des deux change. */
export const TEAMS: Team[] = [
  { code: "ATL", conference: "Est" },
  { code: "BOS", conference: "Est" },
  { code: "BKN", conference: "Est" },
  { code: "CHA", conference: "Est" },
  { code: "CHI", conference: "Est" },
  { code: "CLE", conference: "Est" },
  { code: "DET", conference: "Est" },
  { code: "IND", conference: "Est" },
  { code: "MIA", conference: "Est" },
  { code: "MIL", conference: "Est" },
  { code: "NYK", conference: "Est" },
  { code: "ORL", conference: "Est" },
  { code: "PHI", conference: "Est" },
  { code: "TOR", conference: "Est" },
  { code: "WAS", conference: "Est" },
  { code: "DAL", conference: "Ouest" },
  { code: "DEN", conference: "Ouest" },
  { code: "GSW", conference: "Ouest" },
  { code: "HOU", conference: "Ouest" },
  { code: "LAC", conference: "Ouest" },
  { code: "LAL", conference: "Ouest" },
  { code: "MEM", conference: "Ouest" },
  { code: "MIN", conference: "Ouest" },
  { code: "NOP", conference: "Ouest" },
  { code: "OKC", conference: "Ouest" },
  { code: "PHX", conference: "Ouest" },
  { code: "POR", conference: "Ouest" },
  { code: "SAC", conference: "Ouest" },
  { code: "SAS", conference: "Ouest" },
  { code: "UTA", conference: "Ouest" },
];

const TEAM_CODES = new Set(TEAMS.map((t) => t.code));

export const LEAGUE_EXPECTED_WINS = 82 * 15; // 1230, une info affichée (pas un blocage).

/** Clé d'unicité du nom (casse et espaces ignorés — « Jean  Dupont » ===
 *  « jean dupont »). Le trim + la collapse des espaces internes évitent
 *  qu'un simple double-espace crée un doublon invisible. */
export function nameKey(name: string): string {
  return name.trim().toLowerCase().replace(/\s+/g, " ");
}

export type WinsMap = Record<string, number>;

export type ValidateWinsResult = { ok: true; wins: WinsMap } | { ok: false; error: string };

/** Valide une carte de victoires envoyée par le client (saisie partielle
 *  autorisée pendant l'enregistrement automatique) : clés = équipes
 *  connues, valeurs = entiers 0-82. Rejette toute équipe ou valeur hors
 *  bornes avec un message clair plutôt que de silencieusement l'ignorer. */
export function validateWins(wins: unknown): ValidateWinsResult {
  if (wins === null || typeof wins !== "object" || Array.isArray(wins)) {
    return { ok: false, error: "Format de pronostic invalide." };
  }
  const out: WinsMap = {};
  for (const [team, raw] of Object.entries(wins as Record<string, unknown>)) {
    if (!TEAM_CODES.has(team)) {
      return { ok: false, error: `Équipe inconnue : ${team}.` };
    }
    const value = typeof raw === "number" ? raw : Number(raw);
    if (!Number.isInteger(value) || value < 0 || value > 82) {
      return { ok: false, error: `Nombre de victoires invalide pour ${team} (entre 0 et 82 attendu).` };
    }
    out[team] = value;
  }
  return { ok: true, wins: out };
}

/** Total des victoires saisies (info affichée : attendu 1230 à saisie
 *  complète, mais jamais bloquant — cf. conception). */
export function leagueWinsTotal(wins: WinsMap): number {
  return Object.values(wins).reduce((sum, v) => sum + (Number.isFinite(v) ? v : 0), 0);
}

export type StandingsRow = { team: string; wins: number; losses: number };

export type Standings = Record<Conference, StandingsRow[]>;

/** Classement en direct par conférence à partir d'une carte de victoires
 *  (saisie partielle : équipe absente = 0-82). Tri par victoires
 *  décroissantes, égalité départagée par ordre alphabétique du code
 *  équipe (conception validée). */
export function standingsFromWins(wins: WinsMap, teams: Team[] = TEAMS): Standings {
  const byConf: Standings = { Est: [], Ouest: [] };
  for (const t of teams) {
    const w = wins[t.code] ?? 0;
    byConf[t.conference].push({ team: t.code, wins: w, losses: 82 - w });
  }
  for (const conf of Object.keys(byConf) as Conference[]) {
    byConf[conf].sort((a, b) => (b.wins !== a.wins ? b.wins - a.wins : a.team.localeCompare(b.team)));
  }
  return byConf;
}

/** Clôture : atteinte dès que `now` >= `deadline` (premier tip-off de la
 *  saison régulière 2026-27, ou repli 2026-10-20T23:00:00Z — résolu côté
 *  actions.ts, pas ici). */
export function isClosed(now: Date, deadline: Date): boolean {
  return now.getTime() >= deadline.getTime();
}
