import { supabase } from "@/lib/supabase";
import {
  Game,
  Series,
  Recommendation,
  Player,
  SyncLog,
  RecommendationWithPlayer,
  WatchlistEntry,
  Pick,
  MatchupAggregate,
} from "@/types";
import SyncStatus from "@/components/SyncStatus";
import GamesCollapsible from "@/components/GamesCollapsible";
import StrategyBanner from "@/components/StrategyBanner";
import RecommendationCard from "@/components/RecommendationCard";
import PlayerList from "@/components/PlayerList";
import RefreshButton from "@/components/RefreshButton";
import InjuryArbitrage from "@/components/InjuryArbitrage";
import WatchlistAlerts from "@/components/WatchlistAlerts";
import { todayNBA } from "@/lib/date";

export const revalidate = 300;

async function getData() {
  const today = todayNBA();

  const [
    gamesRes,
    seriesRes,
    recsRes,
    playersRes,
    syncRes,
    watchlistRes,
    picksRes,
  ] = await Promise.all([
    supabase.from("games").select("*").eq("date", today).order("tip_off"),
    supabase.from("series").select("*"),
    supabase.from("recommendations").select("*").eq("date", today).order("rank"),
    supabase.from("players").select("*"),
    supabase.from("sync_log").select("*").order("started_at", { ascending: false }).limit(1),
    supabase.from("player_watchlist").select("*"),
    supabase.from("picks").select("*").eq("mode", "playoffs"),
  ]);

  const allGames = (gamesRes.data || []) as Game[];
  const allSeries = (seriesRes.data || []) as Series[];
  const completedSeriesIds = new Set(
    allSeries.filter((s) => s.status === "completed").map((s) => s.id)
  );
  // Phantom games (G6/G7 of a series that ended early) stay in the schedule
  // and keep getting upserted by load_schedule.py — drop them here so they
  // don't show up in tonight's matches or feed stale recommendations.
  const games = allGames.filter(
    (g) => !g.series_id || !completedSeriesIds.has(g.series_id)
  );
  const series = allSeries.filter((s) => s.status === "active");
  const recs = (recsRes.data || []) as Recommendation[];
  const players = (playersRes.data || []) as Player[];
  const sync = (syncRes.data?.[0] || null) as SyncLog | null;
  const watchlist = (watchlistRes.data || []) as WatchlistEntry[];
  const picks = (picksRes.data || []) as Pick[];

  const playersMap = new Map(players.map((p) => [p.id, p]));

  const recsWithoutMatchup: RecommendationWithPlayer[] = recs
    .map((r) => {
      const player = playersMap.get(r.player_id);
      const game = games.find(
        (g) => g.home_team === player?.team || g.away_team === player?.team
      );
      if (!player || !game) return null;
      return { ...r, player, game };
    })
    .filter(Boolean) as RecommendationWithPlayer[];

  // Pull in-series matchup aggregates for tonight's recommended players.
  // One IN(...) query keyed on player_id; we filter to the right
  // opponent in JS since the (player_id, opponent) tuple isn't
  // available as a server-side filter via the supabase-js builder.
  let matchupRows: MatchupAggregate[] = [];
  if (recsWithoutMatchup.length > 0) {
    const playerIds = recsWithoutMatchup.map((r) => r.player_id);
    const { data: matchupsData } = await supabase
      .from("matchup_aggregates")
      .select("*")
      .in("player_id", playerIds);
    matchupRows = (matchupsData || []) as MatchupAggregate[];
  }
  const matchupByKey = new Map<string, MatchupAggregate>();
  for (const m of matchupRows) {
    matchupByKey.set(`${m.player_id}:${m.opponent_team}`, m);
  }

  const recsWithPlayers: RecommendationWithPlayer[] = recsWithoutMatchup.map(
    (r) => {
      const opponent =
        r.game.home_team === r.player.team
          ? r.game.away_team
          : r.game.home_team;
      const matchup = matchupByKey.get(`${r.player_id}:${opponent}`) || null;
      return { ...r, matchup };
    }
  );

  let gameDaysRemaining = 0;
  for (const s of series) {
    const minLeft = 4 - Math.max(s.home_wins, s.away_wins);
    const maxLeft = 7 - s.home_wins - s.away_wins;
    gameDaysRemaining += Math.round((minLeft + maxLeft) / 2);
  }
  gameDaysRemaining = Math.max(1, Math.round(gameDaysRemaining * 0.7));

  return {
    games,
    series,
    recsWithPlayers,
    sync,
    gameDaysRemaining,
    watchlist,
    picks,
  };
}

export default async function TonightPage() {
  const {
    games,
    series,
    recsWithPlayers,
    sync,
    gameDaysRemaining,
    watchlist,
    picks,
  } = await getData();
  const top3 = recsWithPlayers.slice(0, 3);

  const dateLabel = new Date().toLocaleDateString("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  return (
    <div className="animate-fade-in">
      {/* -------------------- HERO header -------------------- */}
      <header className="relative overflow-hidden px-4 pt-5 pb-4">
        {/* decorative arc (half-court line) */}
        <svg
          className="absolute -top-10 -right-16 w-64 h-64 opacity-[0.07] pointer-events-none"
          viewBox="0 0 200 200"
          fill="none"
          stroke="currentColor"
          strokeWidth="1"
        >
          <circle cx="100" cy="100" r="80" className="text-[color:var(--color-flame)]" />
          <circle cx="100" cy="100" r="40" className="text-[color:var(--color-flame)]" />
          <path d="M 20 100 H 180" className="text-[color:var(--color-flame)]" />
        </svg>

        <div className="flex items-start justify-between gap-3 relative">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.22em] uppercase text-[color:var(--color-gold)]">
                <span className="w-1.5 h-1.5 rounded-full bg-[color:var(--color-gold)] animate-live-dot" />
                Playoffs · Night
              </span>
            </div>
            <h1 className="font-display text-5xl leading-none tracking-wide text-white">
              CE <span className="flame-text">SOIR</span>
            </h1>
            <p className="text-xs text-[color:var(--color-text-mute)] mt-1.5 capitalize tracking-wide">
              {dateLabel} ·{" "}
              <span className="text-[color:var(--color-text-soft)] font-semibold">
                {games.length} match{games.length > 1 ? "s" : ""}
              </span>
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0 pt-1">
            <RefreshButton />
          </div>
        </div>
      </header>

      <SyncStatus sync={sync} />

      <div className="mt-3 px-3">
        <GamesCollapsible games={games} series={series} />
      </div>

      <WatchlistAlerts
        recommendations={recsWithPlayers}
        watchlist={watchlist}
        picks={picks}
      />

      <div className="mt-3 px-3">
        <StrategyBanner
          recommendations={recsWithPlayers}
          gamesDaysRemaining={gameDaysRemaining}
        />
      </div>

      <InjuryArbitrage recs={recsWithPlayers} />

      {/* -------------------- TOP 3 section -------------------- */}
      <section className="mt-6 px-3">
        <div className="flex items-end justify-between mb-3 px-1">
          <h2 className="font-display text-3xl tracking-wide text-white leading-none">
            TOP <span className="gold-text">3</span>
          </h2>
          <span className="text-[10px] tracking-[0.2em] uppercase text-[color:var(--color-text-mute)] pb-1">
            Picks du soir
          </span>
        </div>
        <div className="flex flex-col gap-3 stagger">
          {top3.map((rec) => (
            <RecommendationCard key={rec.id} rec={rec} />
          ))}
          {top3.length === 0 && (
            <div className="surface p-8 text-center">
              <div className="font-display text-2xl text-[color:var(--color-text-mute)] mb-1">
                Aucune reco
              </div>
              <p className="text-sm text-[color:var(--color-text-mute)]">
                Prochaine synchro en cours…
              </p>
            </div>
          )}
        </div>
      </section>

      <PlayerList recs={recsWithPlayers} />
    </div>
  );
}
