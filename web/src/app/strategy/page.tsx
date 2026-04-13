import { supabase } from "@/lib/supabase";
import { Recommendation, Series, Game } from "@/types";

export const revalidate = 300;

async function getData() {
  const today = new Date().toISOString().split("T")[0];
  const futureDate = new Date();
  futureDate.setDate(futureDate.getDate() + 7);
  const futureDateStr = futureDate.toISOString().split("T")[0];

  const [recsRes, seriesRes, gamesRes] = await Promise.all([
    supabase.from("recommendations").select("*").eq("date", today),
    supabase.from("series").select("*").eq("status", "active"),
    supabase.from("games").select("*").gte("date", today).lte("date", futureDateStr).order("date"),
  ]);

  return {
    recs: (recsRes.data || []) as Recommendation[],
    series: (seriesRes.data || []) as Series[],
    games: (gamesRes.data || []) as Game[],
  };
}

export default async function StrategyPage() {
  const { recs, series, games } = await getData();

  const elites = recs.filter((r) => r.tier === "elite").length;
  const solids = recs.filter((r) => r.tier === "solid").length;
  const fillers = recs.filter((r) => r.tier === "filler").length;

  const gamesByDate = new Map<string, Game[]>();
  for (const g of games) {
    const list = gamesByDate.get(g.date) || [];
    list.push(g);
    gamesByDate.set(g.date, list);
  }

  let bestDate = "";
  let bestCount = 0;
  for (const [date, dateGames] of gamesByDate) {
    if (dateGames.length > bestCount) {
      bestCount = dateGames.length;
      bestDate = date;
    }
  }

  return (
    <div className="px-4 py-4">
      <h1 className="text-lg font-bold mb-4">Vue stratégique</h1>
      <div className="bg-gray-900 rounded-xl p-3.5 mb-3">
        <h2 className="text-amber-500 font-bold text-sm mb-2.5">Capital joueurs restant</h2>
        <div className="flex justify-around">
          <div className="text-center">
            <div className="text-amber-400 text-xl font-bold">{elites}</div>
            <div className="text-amber-400 text-xs">★★★ Elite</div>
          </div>
          <div className="text-center">
            <div className="text-blue-400 text-xl font-bold">{solids}</div>
            <div className="text-blue-400 text-xs">★★ Solide</div>
          </div>
          <div className="text-center">
            <div className="text-gray-400 text-xl font-bold">{fillers}</div>
            <div className="text-gray-400 text-xs">★ Filler</div>
          </div>
        </div>
      </div>
      <div className="bg-gray-900 rounded-xl p-3.5 mb-3">
        <h2 className="text-purple-400 font-bold text-sm mb-2.5">Prochains 7 jours</h2>
        <div className="flex flex-col gap-1.5">
          {Array.from(gamesByDate.entries()).map(([dateStr, dateGames]) => {
            const d = new Date(dateStr + "T12:00:00");
            const dayLabel = d.toLocaleDateString("fr-FR", { weekday: "short", day: "numeric" });
            const isBest = dateStr === bestDate;
            const isToday = dateStr === new Date().toISOString().split("T")[0];
            return (
              <div key={dateStr} className="flex justify-between items-center text-sm py-1 border-b border-gray-950 last:border-0">
                <span className={isToday ? "text-white font-bold" : "text-gray-400"}>
                  {isToday ? "Aujourd'hui" : dayLabel}
                </span>
                <span className="text-gray-100">{dateGames.length} match{dateGames.length > 1 ? "s" : ""}</span>
                <span className={`text-xs ${isBest ? "text-amber-500" : "text-gray-600"}`}>
                  {isBest ? "⭐ Best spot semaine" : ""}
                </span>
              </div>
            );
          })}
          {gamesByDate.size === 0 && <p className="text-gray-600 text-sm">Aucun match prévu</p>}
        </div>
      </div>
      <div className="bg-gray-900 rounded-xl p-3.5">
        <h2 className="text-green-500 font-bold text-sm mb-2.5">Séries en cours</h2>
        <div className="flex flex-col gap-2">
          {series.map((s) => {
            const minLeft = 4 - Math.max(s.home_wins, s.away_wins);
            const maxLeft = 7 - s.home_wins - s.away_wins;
            const estLeft = Math.round((minLeft + maxLeft) / 2);
            return (
              <div key={s.id} className="flex justify-between items-center text-sm">
                <span className="text-gray-100">{s.home_team} vs {s.away_team}</span>
                <span className="text-gray-400">{s.home_wins}-{s.away_wins}</span>
                <span className="text-amber-500 text-xs">~{estLeft} game{estLeft > 1 ? "s" : ""} restant{estLeft > 1 ? "s" : ""}</span>
              </div>
            );
          })}
          {series.length === 0 && <p className="text-gray-600 text-sm">Aucune série active</p>}
        </div>
      </div>
    </div>
  );
}
