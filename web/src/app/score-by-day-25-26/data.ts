import "server-only";

import { supabase } from "@/lib/supabase/public";
import { DAY_GAME_TYPES, DAY_SEASON, distinctNights, toDayRows, type DayLogInput, type DayRow } from "@/lib/score-by-day";

// Lecture des tables publiques `games`, `game_logs` et `players` avec le
// client anon uniquement (voir no-private-leak.test.ts). Toute erreur rend
// `available: false` : la page affiche « Données indisponibles » au lieu
// de planter.

const PAGE = 1000; // max-rows PostgREST

/** Soirées de la saison 2025-26 ayant au moins un match terminé du jeu,
 *  par ordre croissant. ~1 400 matchs : lus par pages de 1000. */
export async function fetchNights(): Promise<{ nights: string[]; available: boolean }> {
  const dates: string[] = [];
  for (let from = 0; from < 10 * PAGE; from += PAGE) {
    const { data, error } = await supabase
      .from("games")
      .select("date")
      .eq("season", DAY_SEASON)
      .eq("status", "final")
      .in("game_type", [...DAY_GAME_TYPES])
      .order("date")
      .order("id")
      .range(from, from + PAGE - 1);
    if (error || !data) {
      if (error) console.error("score-by-day, soirées indisponibles :", error.message ?? error);
      return { nights: [], available: false };
    }
    dates.push(...data.map((g: { date: string }) => g.date));
    if (data.length < PAGE) break;
  }
  return { nights: distinctNights(dates), available: true };
}

/** Joueurs entrés en jeu lors d'une soirée (éventuellement d'une équipe),
 *  avec leurs stats et leur score TTFL. */
export async function fetchDay(date: string, team: string | null): Promise<{ rows: DayRow[]; available: boolean }> {
  let query = supabase
    .from("game_logs")
    .select(
      "player_id, team, is_home, minutes, pts, reb, ast, stl, blk, tov, fgm, fga, tpm, tpa, ftm, fta, ttfl_score, players(name), games(home_team, away_team, game_type)",
      { count: "exact" },
    )
    .eq("season", DAY_SEASON)
    .eq("date", date)
    .gt("minutes", 0);
  if (team) query = query.eq("team", team);

  const { data, error, count } = await query;
  if (error || !data) {
    if (error) console.error("score-by-day, soirée indisponible :", error.message ?? error);
    return { rows: [], available: false };
  }
  if (count !== null && count > data.length) {
    console.error(`score-by-day : ${count} lignes au total, seulement ${data.length} renvoyées (troncature)`);
  }
  return { rows: toDayRows(data as unknown as DayLogInput[]), available: true };
}
