import { supabase } from "@/lib/supabase";
import { Pick, Player } from "@/types";

export const revalidate = 0;

async function getData() {
  const [picksRes, playersRes] = await Promise.all([
    supabase.from("picks").select("*").eq("mode", "playoffs").order("date", { ascending: false }),
    supabase.from("players").select("id, name, team"),
  ]);
  const picks = (picksRes.data || []) as Pick[];
  const players = (playersRes.data || []) as Player[];
  const playersMap = new Map(players.map((p) => [p.id, p]));
  return { picks, playersMap };
}

export default async function PicksPage() {
  const { picks, playersMap } = await getData();

  const scores = picks.map((p) => p.actual_score).filter((s): s is number => s !== null);
  const avg = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : 0;
  const best = scores.length ? Math.max(...scores) : 0;
  const worst = scores.length ? Math.min(...scores) : 0;

  return (
    <div className="px-4 py-4">
      <h1 className="text-lg font-bold mb-1">Mes picks playoffs</h1>
      <p className="text-gray-500 text-sm mb-4">
        {picks.length} joueur{picks.length > 1 ? "s" : ""} pické{picks.length > 1 ? "s" : ""}
        {scores.length > 0 ? ` · Total : ${scores.reduce((a, b) => a + b, 0)} pts TTFL` : ""}
      </p>
      {scores.length > 0 && (
        <div className="grid grid-cols-3 gap-2 mb-4">
          <div className="bg-gray-900 rounded-lg p-2 text-center">
            <div className="font-bold">{avg.toFixed(1)}</div>
            <div className="text-gray-500 text-[0.65em]">Avg / pick</div>
          </div>
          <div className="bg-gray-900 rounded-lg p-2 text-center">
            <div className="font-bold text-green-500">{best}</div>
            <div className="text-gray-500 text-[0.65em]">Meilleur</div>
          </div>
          <div className="bg-gray-900 rounded-lg p-2 text-center">
            <div className="font-bold text-red-400">{worst}</div>
            <div className="text-gray-500 text-[0.65em]">Pire</div>
          </div>
        </div>
      )}
      <div className="flex flex-col gap-2">
        {picks.map((pick) => {
          const player = playersMap.get(pick.player_id);
          const scoreColor = pick.actual_score === null ? "text-gray-500"
            : pick.actual_score >= 50 ? "text-green-500"
            : pick.actual_score >= 30 ? "text-gray-100" : "text-red-400";
          return (
            <div key={pick.id} className="bg-gray-900 rounded-lg px-3 py-2.5 flex justify-between items-center">
              <div>
                <div className="font-bold text-sm">{player?.name || "?"}</div>
                <div className="text-gray-500 text-xs">
                  {new Date(pick.date).toLocaleDateString("fr-FR", { day: "numeric", month: "short" })}
                  {player ? ` · ${player.team}` : ""}
                </div>
              </div>
              <div className={`font-bold ${scoreColor}`}>{pick.actual_score !== null ? pick.actual_score : "—"}</div>
            </div>
          );
        })}
        {picks.length === 0 && (
          <p className="text-gray-600 text-sm text-center py-8">Aucun pick encore. Va sur l&apos;onglet &quot;Ce soir&quot; pour commencer !</p>
        )}
      </div>
    </div>
  );
}
