import { supabase } from "@/lib/supabase";
import { Player, Recommendation, Game, Pick } from "@/types";
import { ProsBlock, ConsBlock, VerdictBlock } from "@/components/ProsCons";
import PickButton from "./PickButton";
import BackButton from "./BackButton";
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

async function getData(playerId: number) {
  const today = todayNBA();
  const [playerRes, recRes, gamesRes, picksRes] = await Promise.all([
    supabase.from("players").select("*").eq("id", playerId).single(),
    supabase
      .from("recommendations")
      .select("*")
      .eq("player_id", playerId)
      .eq("date", today)
      .single(),
    supabase.from("games").select("*").eq("date", today),
    supabase.from("picks").select("*").eq("mode", "playoffs"),
  ]);
  const player = playerRes.data as Player | null;
  const rec = recRes.data as Recommendation | null;
  const games = (gamesRes.data || []) as Game[];
  const picks = (picksRes.data || []) as Pick[];
  const game = games.find(
    (g) => g.home_team === player?.team || g.away_team === player?.team
  );
  const alreadyPicked = picks.some((p) => p.player_id === playerId);
  const pickedToday = picks.some((p) => p.date === today);
  return { player, rec, game, alreadyPicked, pickedToday };
}

export default async function PlayerPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const playerId = parseInt(id, 10);
  const { player, rec, game, alreadyPicked, pickedToday } = await getData(
    playerId
  );

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

  const isHome = game ? player.team === game.home_team : false;
  const opponent = game ? (isHome ? game.away_team : game.home_team) : "?";
  const tier = tierLabels[rec?.tier || "filler"];

  return (
    <div className="px-4 py-4 animate-fade-in">
      <BackButton />

      {/* ----------------- identity header ----------------- */}
      <header className="mt-3 relative">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-xs ${tier.color}`}>{tier.stars}</span>
              <span
                className={`text-[10px] uppercase tracking-[0.22em] font-bold ${tier.color}`}
              >
                {tier.label}
              </span>
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
              {game && (
                <>
                  <span className="text-[color:var(--color-text-mute)]">·</span>
                  <span className="text-[color:var(--color-text-soft)]">
                    {isHome ? "vs" : "@"}{" "}
                    <span className="font-bold text-[color:var(--color-text)]">
                      {opponent}
                    </span>
                    {game.game_number && (
                      <span className="text-[color:var(--color-gold)] ml-1">
                        · G{game.game_number}
                      </span>
                    )}
                  </span>
                </>
              )}
            </div>
          </div>

          {rec && (
            <div className="text-right shrink-0">
              <div className="font-display text-5xl leading-none font-mono-num flame-text">
                {rec.estimated_score.toFixed(1)}
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
      {rec && (
        <div className="flex flex-col gap-3 mt-5">
          {rec.pros.length > 0 && <ProsBlock pros={rec.pros} />}
          {rec.cons.length > 0 && <ConsBlock cons={rec.cons} />}
          <VerdictBlock verdict={rec.verdict} />
        </div>
      )}

      {/* ----------------- pick cta ----------------- */}
      {game && rec && (
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
