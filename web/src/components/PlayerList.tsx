"use client";

import { useState } from "react";
import Link from "next/link";
import { RecommendationWithPlayer } from "@/types";

const tierColors: Record<string, string> = {
  elite: "text-amber-400",
  solid: "text-blue-400",
  filler: "text-gray-500",
};

export default function PlayerList({ recs }: { recs: RecommendationWithPlayer[] }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? recs : [];

  return (
    <div className="mx-3 mt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full bg-gray-900 rounded-xl p-3 text-center text-gray-500 text-sm border border-dashed border-gray-800"
      >
        {expanded ? "▲ Replier" : `👇 Voir les ${recs.length} joueurs classés`}
      </button>
      {expanded && (
        <div className="mt-2 flex flex-col gap-1">
          {visible.map((rec) => {
            const { player, game } = rec;
            const isHome = player.team === game.home_team;
            const opponent = isHome ? game.away_team : game.home_team;
            return (
              <Link key={rec.id} href={`/player/${player.id}`} className="block text-gray-100">
                <div className="bg-gray-900 rounded-lg px-3 py-2 flex justify-between items-center">
                  <div className="flex items-center gap-2">
                    <span className="text-gray-600 text-xs w-6 text-right">{rec.rank}</span>
                    <div>
                      <span className="font-medium text-sm text-gray-100">{player.name}</span>
                      <span className="text-gray-600 text-xs ml-2">{player.team} {isHome ? "vs" : "@"} {opponent}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`text-xs ${tierColors[rec.tier]}`}>
                      {rec.tier === "elite" ? "★★★" : rec.tier === "solid" ? "★★" : "★"}
                    </span>
                    <span className="font-bold text-sm">{rec.estimated_score.toFixed(1)}</span>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
