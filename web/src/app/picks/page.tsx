import { supabase } from "@/lib/supabase";
import { Pick, Player } from "@/types";

export const revalidate = 0;

async function getData() {
  const [picksRes, playersRes] = await Promise.all([
    supabase.from("picks").select("*").order("date", { ascending: false }),
    supabase.from("players").select("id, name, team"),
  ]);
  const picks = (picksRes.data || []) as Pick[];
  const players = (playersRes.data || []) as Player[];
  const playersMap = new Map(players.map((p) => [p.id, p]));
  return { picks, playersMap };
}

function effectiveScore(pick: Pick): number {
  // If estimated_score is set and differs from actual_score, it's a x2 bonus
  if (
    pick.estimated_score !== null &&
    pick.actual_score !== null &&
    pick.estimated_score !== pick.actual_score &&
    pick.estimated_score === pick.actual_score * 2
  ) {
    return pick.estimated_score;
  }
  return pick.actual_score ?? 0;
}

function isX2(pick: Pick): boolean {
  return (
    pick.estimated_score !== null &&
    pick.actual_score !== null &&
    pick.estimated_score === pick.actual_score * 2
  );
}

export default async function PicksPage() {
  const { picks, playersMap } = await getData();

  const effectiveScores = picks
    .filter((p) => p.actual_score !== null)
    .map((p) => effectiveScore(p));
  const total = effectiveScores.reduce((a, b) => a + b, 0);
  const avg = effectiveScores.length ? total / effectiveScores.length : 0;
  const best = effectiveScores.length ? Math.max(...effectiveScores) : 0;
  const worst = effectiveScores.length ? Math.min(...effectiveScores) : 0;

  return (
    <div className="px-4 py-4">
      <h1 className="text-lg font-bold mb-1">Mes picks</h1>
      <p className="text-gray-500 text-sm mb-4">
        {picks.length} pick{picks.length > 1 ? "s" : ""}
        {effectiveScores.length > 0 ? ` · Total : ${total} pts TTFL` : ""}
      </p>
      {effectiveScores.length > 0 && (
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
          const eff = effectiveScore(pick);
          const x2 = isX2(pick);
          const scoreColor =
            pick.actual_score === null
              ? "text-gray-500"
              : eff >= 50
                ? "text-green-500"
                : eff >= 30
                  ? "text-gray-100"
                  : "text-red-400";
          return (
            <div
              key={pick.id}
              className="bg-gray-900 rounded-lg px-3 py-2.5 flex justify-between items-center"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-bold text-sm">
                    {player?.name || "?"}
                  </span>
                  {x2 && (
                    <span className="bg-amber-500 text-gray-950 text-[0.6em] px-1.5 py-0.5 rounded font-bold">
                      x2
                    </span>
                  )}
                </div>
                <div className="text-gray-500 text-xs">
                  {new Date(pick.date + "T12:00:00").toLocaleDateString("fr-FR", {
                    day: "numeric",
                    month: "short",
                  })}
                  {player ? ` · ${player.team}` : ""}
                </div>
              </div>
              <div className="text-right">
                <div className={`font-bold ${scoreColor}`}>
                  {pick.actual_score !== null ? eff : "—"}
                </div>
                {x2 && (
                  <div className="text-gray-600 text-[0.6em]">
                    ({pick.actual_score} × 2)
                  </div>
                )}
              </div>
            </div>
          );
        })}
        {picks.length === 0 && (
          <p className="text-gray-600 text-sm text-center py-8">
            Aucun pick encore. Va sur l&apos;onglet &quot;Ce soir&quot; pour
            commencer !
          </p>
        )}
      </div>
    </div>
  );
}
