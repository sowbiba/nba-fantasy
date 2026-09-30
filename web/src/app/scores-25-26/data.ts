import "server-only";

import { supabase } from "@/lib/supabase/public";
import { SEASON, type GameType, type ScoreRow } from "@/lib/scores";

// Lecture de la vue publique `player_ttfl_season` (migration 032) —
// partagée par la page et la route d'export pour ne définir qu'une seule
// fois la requête et l'état "indisponible". Client anon uniquement (voir
// no-private-leak.test.ts) : cette vue est publique (grant à anon).

type Row = {
  player_id: number;
  name: string;
  team: string;
  games: number;
  avg_ttfl: number | string;
  total_ttfl: number | string;
  top_score: number;
  top_date: string;
  top_opponent: string;
};

export type FetchScoresResult = { rows: ScoreRow[]; available: boolean };

function mapRow(r: Row): ScoreRow {
  return {
    playerId: r.player_id,
    name: r.name,
    team: r.team,
    games: r.games,
    avgTtfl: Number(r.avg_ttfl),
    totalTtfl: Number(r.total_ttfl),
    topScore: r.top_score,
    topDate: r.top_date,
    topOpponent: r.top_opponent,
  };
}

/** Lit les scores TTFL 2025-26 pour un type de match, un minimum de
 *  matchs et éventuellement une équipe. La vue `player_ttfl_season` (migration
 *  032) n'est pas encore appliquée en prod au moment de la tâche 4 : toute
 *  erreur (vue absente comprise) retourne `available: false` plutôt que de
 *  lever une exception — page et export affichent alors un état "Données
 *  indisponibles" au lieu de planter. */
export async function fetchScores(type: GameType, minGames: number, team: string | null): Promise<FetchScoresResult> {
  // `count: "exact"` fait compter le total de lignes correspondantes côté
  // Postgres, indépendamment du nombre de lignes réellement renvoyées : un
  // `.limit()` client ne suffit pas à détecter une troncature, PostgREST
  // plafonne de toute façon la page à son `max-rows` serveur (1000 par
  // défaut) quelle que soit la limite demandée — comparer `count` à
  // `data.length` est le seul moyen fiable de la détecter.
  let query = supabase
    .from("player_ttfl_season")
    .select("player_id, name, team, games, avg_ttfl, total_ttfl, top_score, top_date, top_opponent", {
      count: "exact",
    })
    .eq("season", SEASON)
    .eq("game_type", type)
    .gte("games", minGames);
  if (team) query = query.eq("team", team);

  const { data, error, count } = await query;
  if (error || !data) {
    if (error) console.error("player_ttfl_season indisponible :", error.message ?? error);
    return { rows: [], available: false };
  }
  if (count !== null && count > data.length) {
    // Improbable (≤ ~600 joueurs possibles sur une saison) mais on le
    // journalise plutôt que de servir des données incomplètes sans le
    // savoir.
    console.error(`player_ttfl_season : ${count} lignes au total, seulement ${data.length} renvoyées (troncature)`);
  }
  return { rows: (data as Row[]).map(mapRow), available: true };
}
