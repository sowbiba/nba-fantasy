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

/** Nettoie un nom saisi avant validation/stockage (revue round 1, mineur
 *  5) : normalisation Unicode NFKC (des formes visuellement équivalentes
 *  deviennent identiques), suppression des caractères de contrôle et de
 *  format (catégories Unicode Cc/Cf — espaces de largeur nulle inclus,
 *  invisibles mais qui casseraient sinon la comparaison de noms), espaces
 *  de bord retirés, espaces internes multiples réduits à un seul. */
export function sanitizeName(name: string): string {
  return name
    .normalize("NFKC")
    .replace(/[\p{Cc}\p{Cf}]/gu, "")
    .trim()
    .replace(/\s+/g, " ");
}

/** Clé d'unicité du nom (casse ignorée en plus du nettoyage ci-dessus —
 *  « Jean  Dupont » === « jean dupont »). */
export function nameKey(name: string): string {
  return sanitizeName(name).toLowerCase();
}

export type WinsMap = Record<string, number>;

export type ValidateWinsResult = { ok: true; wins: WinsMap } | { ok: false; error: string };

/** Valide une carte de victoires envoyée par le client (saisie partielle
 *  autorisée pendant l'enregistrement automatique) : clés = équipes
 *  connues (au plus 30, une par équipe), valeurs = *nombres* entiers 0-82.
 *  Rejette toute équipe ou valeur hors bornes avec un message clair plutôt
 *  que de silencieusement l'ignorer. Pas de coercition (revue round 1,
 *  mineur 4) : `null`, `""`, `true/false` ou une chaîne numérique
 *  ("50") sont refusés plutôt que lus comme 0/0/1/50 — seul un `number`
 *  JS est accepté, ce que `JSON.parse` produit pour un nombre JSON. */
export function validateWins(wins: unknown): ValidateWinsResult {
  if (wins === null || typeof wins !== "object" || Array.isArray(wins)) {
    return { ok: false, error: "Format de pronostic invalide." };
  }
  const entries = Object.entries(wins as Record<string, unknown>);
  if (entries.length > TEAMS.length) {
    return { ok: false, error: "Trop d'équipes dans le pronostic." };
  }
  const out: WinsMap = {};
  for (const [team, raw] of entries) {
    if (!TEAM_CODES.has(team)) {
      return { ok: false, error: `Équipe inconnue : ${team}.` };
    }
    if (typeof raw !== "number" || !Number.isInteger(raw) || raw < 0 || raw > 82) {
      return { ok: false, error: `Nombre de victoires invalide pour ${team} (entre 0 et 82 attendu).` };
    }
    out[team] = raw;
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
