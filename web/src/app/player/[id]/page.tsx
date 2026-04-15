import { supabase } from "@/lib/supabase";
import { Player, Recommendation, Game, Pick } from "@/types";
import { ProsBlock, ConsBlock, VerdictBlock } from "@/components/ProsCons";
import Link from "next/link";
import PickButton from "./PickButton";

export const revalidate = 300;

const tierLabels: Record<string, { label: string; color: string }> = {
  elite: { label: "★★★ Elite", color: "text-amber-400" },
  solid: { label: "★★ Solide", color: "text-blue-400" },
  filler: { label: "★ Filler", color: "text-gray-400" },
};

async function getData(playerId: number) {
  const today = new Date().toISOString().split("T")[0];
  const [playerRes, recRes, gamesRes, picksRes] = await Promise.all([
    supabase.from("players").select("*").eq("id", playerId).single(),
    supabase.from("recommendations").select("*").eq("player_id", playerId).eq("date", today).single(),
    supabase.from("games").select("*").eq("date", today),
    supabase.from("picks").select("*").eq("mode", "playoffs"),
  ]);
  const player = playerRes.data as Player | null;
  const rec = recRes.data as Recommendation | null;
  const games = (gamesRes.data || []) as Game[];
  const picks = (picksRes.data || []) as Pick[];
  const game = games.find((g) => g.home_team === player?.team || g.away_team === player?.team);
  const alreadyPicked = picks.some((p) => p.player_id === playerId);
  const pickedToday = picks.some((p) => p.date === today);
  return { player, rec, game, alreadyPicked, pickedToday };
}

export default async function PlayerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const playerId = parseInt(id, 10);
  const { player, rec, game, alreadyPicked, pickedToday } = await getData(playerId);

  if (!player) {
    return <div className="p-8 text-center text-gray-500">Joueur introuvable</div>;
  }

  const isHome = game ? player.team === game.home_team : false;
  const opponent = game ? (isHome ? game.away_team : game.home_team) : "?";
  const tier = tierLabels[rec?.tier || "filler"];

  return (
    <div className="px-4 py-4">
      <Link href="/" className="text-gray-500 text-sm">← Retour</Link>
      <div className="flex justify-between items-start mt-3 mb-4">
        <div>
          <h1 className="text-xl font-bold text-gray-100">{player.name}</h1>
          <p className="text-gray-500 text-sm">
            {player.team} · {player.position}
            {game ? ` · ${isHome ? `vs ${opponent}` : `@ ${opponent}`}${game.game_number ? ` Game ${game.game_number}` : ""}` : ""}
          </p>
        </div>
        {rec && (
          <div className="text-right">
            <div className="text-green-500 font-bold text-2xl">{rec.estimated_score.toFixed(1)}</div>
            <div className="text-gray-600 text-xs">score estimé</div>
            <div className={`text-xs ${tier.color}`}>{tier.label}</div>
          </div>
        )}
      </div>
      <div className="grid grid-cols-3 gap-2 mb-4">
        <div className="bg-gray-900 rounded-lg p-2 text-center">
          <div className="font-bold">{player.avg_ttfl_l5?.toFixed(1) || "—"}</div>
          <div className="text-gray-500 text-[0.65em]">Avg TTFL L5</div>
        </div>
        <div className="bg-gray-900 rounded-lg p-2 text-center">
          <div className="font-bold">{player.avg_ttfl_season?.toFixed(1) || "—"}</div>
          <div className="text-gray-500 text-[0.65em]">Avg saison</div>
        </div>
        <div className="bg-gray-900 rounded-lg p-2 text-center">
          <div className="font-bold">
            {player.avg_ttfl_season
              ? `${Math.round(player.avg_ttfl_season - player.stddev_ttfl)} / ${Math.round(player.avg_ttfl_season + player.stddev_ttfl)}`
              : "—"}
          </div>
          <div className="text-gray-500 text-[0.65em]">Floor / Ceiling</div>
        </div>
      </div>
      {rec && (
        <div className="flex flex-col gap-3 mb-4">
          <ProsBlock pros={rec.pros} />
          <ConsBlock cons={rec.cons} />
          <VerdictBlock verdict={rec.verdict} />
        </div>
      )}
      {game && rec && (
        <PickButton
          playerId={player.id} gameId={game.id} playerName={player.name}
          estimatedScore={rec.estimated_score} alreadyPicked={alreadyPicked} pickedToday={pickedToday}
        />
      )}
    </div>
  );
}
