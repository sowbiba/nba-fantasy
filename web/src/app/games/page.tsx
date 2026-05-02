import { supabase } from "@/lib/supabase";
import { Game, Series } from "@/types";
import GamesList from "./GamesList";

export const revalidate = 300;

const PLAYOFFS_START = "2026-04-14";

async function getData() {
  const [gamesRes, seriesRes] = await Promise.all([
    supabase
      .from("games")
      .select("*")
      .gte("date", PLAYOFFS_START)
      .order("date", { ascending: false }),
    supabase.from("series").select("*"),
  ]);

  const allGames = (gamesRes.data || []) as Game[];
  const allSeries = (seriesRes.data || []) as Series[];

  // Drop unplayed phantom games of completed series (G6/G7 of a series
  // that ended early — NBA's static schedule keeps the placeholder slots
  // and load_schedule.py keeps re-upserting them). Keep `final` games so
  // box scores remain visible.
  const completedSeriesIds = new Set(
    allSeries.filter((s) => s.status === "completed").map((s) => s.id)
  );
  const completedPairs = new Set(
    allSeries
      .filter((s) => s.status === "completed")
      .map((s) => [s.home_team, s.away_team].sort().join("|"))
  );
  const games = allGames.filter((g) => {
    if (g.status === "final") return true;
    if (g.series_id && completedSeriesIds.has(g.series_id)) return false;
    const pair = [g.home_team, g.away_team].sort().join("|");
    if (completedPairs.has(pair)) return false;
    return true;
  });

  return { games };
}

export default async function GamesPage() {
  const { games } = await getData();

  return (
    <div className="px-4 py-5 animate-fade-in">
      <div className="mb-5">
        <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.22em] uppercase text-[color:var(--color-flame)]">
          <span className="w-1 h-1 rounded-full bg-[color:var(--color-flame)]" />
          Box scores
        </span>
        <h1 className="font-display text-4xl leading-none tracking-wide text-white mt-1">
          MATCH<span className="flame-text">S</span>
        </h1>
        <p className="text-[11px] text-[color:var(--color-text-mute)] mt-2 uppercase tracking-[0.18em]">
          {games.filter((g) => g.status === "final").length} terminé
          {games.filter((g) => g.status === "final").length > 1 ? "s" : ""} ·{" "}
          {games.filter((g) => g.status !== "final").length} à venir
        </p>
      </div>

      <GamesList games={games} />
    </div>
  );
}
