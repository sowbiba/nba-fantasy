import { supabase } from "@/lib/supabase";
import { Game, Series, Recommendation, Player, SyncLog, RecommendationWithPlayer } from "@/types";
import SyncStatus from "@/components/SyncStatus";
import GamesCollapsible from "@/components/GamesCollapsible";
import StrategyBanner from "@/components/StrategyBanner";
import RecommendationCard from "@/components/RecommendationCard";
import PlayerList from "@/components/PlayerList";

export const revalidate = 300;

async function getData() {
  const today = new Date().toISOString().split("T")[0];

  const [gamesRes, seriesRes, recsRes, playersRes, syncRes] = await Promise.all([
    supabase.from("games").select("*").eq("date", today).order("tip_off"),
    supabase.from("series").select("*").eq("status", "active"),
    supabase.from("recommendations").select("*").eq("date", today).order("rank"),
    supabase.from("players").select("*"),
    supabase.from("sync_log").select("*").order("started_at", { ascending: false }).limit(1),
  ]);

  const games = (gamesRes.data || []) as Game[];
  const series = (seriesRes.data || []) as Series[];
  const recs = (recsRes.data || []) as Recommendation[];
  const players = (playersRes.data || []) as Player[];
  const sync = (syncRes.data?.[0] || null) as SyncLog | null;

  const playersMap = new Map(players.map((p) => [p.id, p]));

  const recsWithPlayers: RecommendationWithPlayer[] = recs
    .map((r) => {
      const player = playersMap.get(r.player_id);
      const game = games.find(
        (g) => g.home_team === player?.team || g.away_team === player?.team
      );
      if (!player || !game) return null;
      return { ...r, player, game };
    })
    .filter(Boolean) as RecommendationWithPlayer[];

  let gameDaysRemaining = 0;
  for (const s of series) {
    const minLeft = 4 - Math.max(s.home_wins, s.away_wins);
    const maxLeft = 7 - s.home_wins - s.away_wins;
    gameDaysRemaining += Math.round((minLeft + maxLeft) / 2);
  }
  gameDaysRemaining = Math.max(1, Math.round(gameDaysRemaining * 0.7));

  return { games, series, recsWithPlayers, sync, gameDaysRemaining };
}

export default async function TonightPage() {
  const { games, series, recsWithPlayers, sync, gameDaysRemaining } = await getData();
  const top3 = recsWithPlayers.slice(0, 3);

  return (
    <div>
      <div className="flex justify-between items-center px-4 py-3 border-b border-gray-900">
        <div>
          <h1 className="text-lg font-bold">TTFL Advisor</h1>
          <p className="text-xs text-gray-500">
            {new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })}
            {" "}· {games.length} match{games.length > 1 ? "s" : ""} ce soir
          </p>
        </div>
        <span className="bg-gray-900 rounded-full px-2.5 py-1 text-xs text-amber-500 font-medium">PLAYOFFS</span>
      </div>
      <SyncStatus sync={sync} />
      <div className="mt-2"><GamesCollapsible games={games} series={series} /></div>
      <div className="mt-2"><StrategyBanner recommendations={recsWithPlayers} gamesDaysRemaining={gameDaysRemaining} /></div>
      <div className="mt-4 px-3">
        <h2 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2 px-1">Top 3 recommandations</h2>
        <div className="flex flex-col gap-2">
          {top3.map((rec) => (<RecommendationCard key={rec.id} rec={rec} />))}
          {top3.length === 0 && (
            <p className="text-gray-600 text-sm text-center py-8">
              Pas encore de recommandations pour ce soir. Prochaine synchro en cours...
            </p>
          )}
        </div>
      </div>
      <PlayerList recs={recsWithPlayers} />
    </div>
  );
}
