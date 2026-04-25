import { supabase } from "@/lib/supabase";
import { Game } from "@/types";
import LiveBoxScore from "./LiveBoxScore";
import BackButton from "../../player/[id]/BackButton";

export const revalidate = 60;

async function getData(gameId: string) {
  const { data } = await supabase
    .from("games")
    .select("*")
    .eq("id", gameId)
    .single();
  return (data as Game | null) ?? null;
}

export default async function GameLivePage({
  params,
}: {
  params: Promise<{ gameId: string }>;
}) {
  const { gameId } = await params;
  const game = await getData(gameId);

  if (!game) {
    return (
      <div className="px-4 py-12 text-center">
        <div className="font-display text-3xl text-[color:var(--color-text-mute)]">
          Match
          <br />
          introuvable
        </div>
      </div>
    );
  }

  const d = new Date(game.date + "T12:00:00");
  const dateLabel = d.toLocaleDateString("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  return (
    <div className="px-4 py-4 animate-fade-in">
      <BackButton />

      <header className="mt-3">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[10px] uppercase tracking-[0.22em] font-bold text-[color:var(--color-flame)]">
            {dateLabel}
          </span>
          {game.game_number && (
            <span className="text-[9px] font-bold tracking-[0.1em] px-1.5 py-0.5 rounded bg-[color:var(--color-gold)]/15 text-[color:var(--color-gold)] border border-[color:var(--color-gold)]/30">
              G{game.game_number}
            </span>
          )}
        </div>
        <h1 className="font-display text-4xl leading-none tracking-wide text-white mt-1">
          {game.home_team}
          <span className="text-[color:var(--color-text-mute)] mx-3">·</span>
          {game.away_team}
        </h1>
      </header>

      <LiveBoxScore
        gameId={game.id}
        homeTeam={game.home_team}
        awayTeam={game.away_team}
        initialStatus={game.status}
      />
    </div>
  );
}
