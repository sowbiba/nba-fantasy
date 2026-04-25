import { supabase } from "@/lib/supabase";
import {
  Player,
  Recommendation,
  Game,
  Pick,
  WatchlistEntry,
  WeeklyPlanEntry,
} from "@/types";
import { ProsBlock, ConsBlock, VerdictBlock } from "@/components/ProsCons";
import PickButton from "./PickButton";
import BackButton from "./BackButton";
import WatchlistStar from "./WatchlistStar";
import { todayNBA } from "@/lib/date";

export const revalidate = 300;

const tierLabels: Record<
  string,
  { label: string; color: string; stars: string }
> = {
  elite: {
    label: "ELITE",
    color: "text-[color:var(--color-gold)]",
    stars: "★★★",
  },
  solid: {
    label: "SOLIDE",
    color: "text-[color:var(--color-ice)]",
    stars: "★★",
  },
  filler: {
    label: "FILLER",
    color: "text-[color:var(--color-text-soft)]",
    stars: "★",
  },
};

async function getData(playerId: number, planDate: string | null) {
  const today = todayNBA();
  const isFuturePlan = !!planDate && planDate !== today;
  const effectiveDate = planDate || today;

  const [playerRes, recRes, planRes, gamesRes, picksRes, watchlistRes] =
    await Promise.all([
      supabase.from("players").select("*").eq("id", playerId).single(),
      isFuturePlan
        ? Promise.resolve({ data: null })
        : supabase
            .from("recommendations")
            .select("*")
            .eq("player_id", playerId)
            .eq("date", today)
            .single(),
      isFuturePlan
        ? supabase
            .from("weekly_plan")
            .select("*")
            .eq("player_id", playerId)
            .eq("date", planDate)
            .single()
        : Promise.resolve({ data: null }),
      supabase.from("games").select("*").eq("date", effectiveDate),
      supabase.from("picks").select("*").eq("mode", "playoffs"),
      supabase
        .from("player_watchlist")
        .select("*")
        .eq("player_id", playerId)
        .maybeSingle(),
    ]);
  const player = playerRes.data as Player | null;
  const rec = recRes.data as Recommendation | null;
  const plan = planRes.data as WeeklyPlanEntry | null;
  const games = (gamesRes.data || []) as Game[];
  const picks = (picksRes.data || []) as Pick[];
  const watchlist = (watchlistRes.data as WatchlistEntry | null) ?? null;
  const game = games.find(
    (g) => g.home_team === player?.team || g.away_team === player?.team
  );
  const alreadyPicked = picks.some((p) => p.player_id === playerId);
  const pickedToday = picks.some((p) => p.date === today);
  return {
    player,
    rec,
    plan,
    game,
    alreadyPicked,
    pickedToday,
    isFuturePlan,
    watchlist,
  };
}

export default async function PlayerPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ planDate?: string }>;
}) {
  const [{ id }, { planDate }] = await Promise.all([params, searchParams]);
  const playerId = parseInt(id, 10);
  const {
    player,
    rec,
    plan,
    game,
    alreadyPicked,
    pickedToday,
    isFuturePlan,
    watchlist,
  } = await getData(playerId, planDate ?? null);

  if (!player) {
    return (
      <div className="px-4 py-12 text-center">
        <div className="font-display text-3xl text-[color:var(--color-text-mute)]">
          Joueur
          <br />
          introuvable
        </div>
      </div>
    );
  }

  const isHome = isFuturePlan
    ? plan?.is_home ?? false
    : game
    ? player.team === game.home_team
    : false;
  const opponent = isFuturePlan
    ? plan?.opponent ?? "?"
    : game
    ? isHome
      ? game.away_team
      : game.home_team
    : "?";
  const gameNumber = isFuturePlan
    ? plan?.game_number ?? null
    : game?.game_number ?? null;
  const tier = tierLabels[(isFuturePlan ? plan?.tier : rec?.tier) || "filler"];
  const estimatedScore = isFuturePlan
    ? plan?.estimated_score
    : rec?.estimated_score;
  const pros = isFuturePlan ? plan?.pros ?? [] : rec?.pros ?? [];
  const cons = isFuturePlan ? plan?.cons ?? [] : rec?.cons ?? [];
  const verdict = isFuturePlan ? plan?.verdict ?? "" : rec?.verdict ?? "";
  const hasArgumentaire = isFuturePlan ? !!plan : !!rec;
  const planDayLabel = plan
    ? new Date(plan.date + "T12:00:00")
        .toLocaleDateString("fr-FR", {
          weekday: "long",
          day: "numeric",
          month: "long",
        })
    : null;

  return (
    <div className="px-4 py-4 animate-fade-in">
      <BackButton />

      {/* ----------------- identity header ----------------- */}
      <header className="mt-3 relative">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className={`text-xs ${tier.color}`}>{tier.stars}</span>
              <span
                className={`text-[10px] uppercase tracking-[0.22em] font-bold ${tier.color}`}
              >
                {tier.label}
              </span>
              <WatchlistStar
                playerId={playerId}
                initialPriority={
                  (watchlist?.priority as 1 | 2 | 3 | undefined) ?? null
                }
              />
            </div>
            <h1 className="font-display text-4xl leading-none tracking-wide text-white">
              {player.name}
            </h1>
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 mt-2 text-sm">
              <span className="font-bold text-[color:var(--color-flame)] tracking-wide">
                {player.team}
              </span>
              <span className="text-[color:var(--color-text-mute)]">·</span>
              <span className="text-[color:var(--color-text-soft)]">
                {player.position}
              </span>
              {(game || isFuturePlan) && (
                <>
                  <span className="text-[color:var(--color-text-mute)]">·</span>
                  <span className="text-[color:var(--color-text-soft)]">
                    {isHome ? "vs" : "@"}{" "}
                    <span className="font-bold text-[color:var(--color-text)]">
                      {opponent}
                    </span>
                    {gameNumber && (
                      <span className="text-[color:var(--color-gold)] ml-1">
                        · G{gameNumber}
                      </span>
                    )}
                  </span>
                </>
              )}
            </div>
            {isFuturePlan && planDayLabel && (
              <div className="mt-2 inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[0.22em] font-bold text-[color:var(--color-gold)]">
                <span>📅</span>
                <span>Calé pour {planDayLabel}</span>
              </div>
            )}
          </div>

          {estimatedScore !== undefined && (
            <div className="text-right shrink-0">
              <div className="font-display text-5xl leading-none font-mono-num flame-text">
                {estimatedScore.toFixed(1)}
              </div>
              <div className="text-[9px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)] mt-1">
                Score estimé
              </div>
            </div>
          )}
        </div>
      </header>

      {/* ----------------- stats block ----------------- */}
      <div className="grid grid-cols-3 gap-2 mt-5">
        <StatTile
          value={player.avg_ttfl_l5?.toFixed(1) || "—"}
          label="5 derniers"
        />
        <StatTile
          value={player.avg_ttfl_season?.toFixed(1) || "—"}
          label="Saison"
        />
        <StatTile
          value={
            player.avg_ttfl_season
              ? `${Math.round(
                  player.avg_ttfl_season - player.stddev_ttfl
                )}·${Math.round(player.avg_ttfl_season + player.stddev_ttfl)}`
              : "—"
          }
          label="Floor · Ceiling"
          mono
        />
      </div>

      {/* ----------------- pros / cons / verdict ----------------- */}
      {hasArgumentaire && (
        <div className="flex flex-col gap-3 mt-5">
          {pros.length > 0 && <ProsBlock pros={pros} />}
          {cons.length > 0 && <ConsBlock cons={cons} />}
          {verdict && <VerdictBlock verdict={verdict} />}
        </div>
      )}

      {/* ----------------- pick cta (today only) ----------------- */}
      {!isFuturePlan && game && rec && (
        <div className="mt-6">
          <PickButton
            playerId={player.id}
            gameId={game.id}
            playerName={player.name}
            estimatedScore={rec.estimated_score}
            alreadyPicked={alreadyPicked}
            pickedToday={pickedToday}
          />
        </div>
      )}
    </div>
  );
}

function StatTile({
  value,
  label,
  mono = false,
}: {
  value: string;
  label: string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-[var(--radius-card-sm)] border border-white/5 bg-[color:var(--color-surface)] px-2 py-3 text-center">
      <div
        className={`font-display text-2xl leading-none text-white font-mono-num ${
          mono ? "text-lg" : ""
        }`}
      >
        {value}
      </div>
      <div className="text-[9px] uppercase tracking-[0.18em] text-[color:var(--color-text-mute)] mt-1.5">
        {label}
      </div>
    </div>
  );
}
