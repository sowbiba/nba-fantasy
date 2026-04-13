"use client";

import { useState } from "react";
import { Game, Series } from "@/types";

interface Props {
  games: Game[];
  series: Series[];
}

export default function GamesCollapsible({ games, series }: Props) {
  const [open, setOpen] = useState(false);

  const getSeriesForGame = (game: Game) =>
    series.find(
      (s) =>
        (s.home_team === game.home_team && s.away_team === game.away_team) ||
        (s.home_team === game.away_team && s.away_team === game.home_team)
    );

  const formatTipOff = (tipOff: string | null) => {
    if (!tipOff) return "";
    const d = new Date(tipOff);
    return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  };

  return (
    <div className="mx-3 bg-gray-900 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-3.5 py-2.5 flex justify-between items-center"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-gray-100">🏀 Matchs du soir</span>
          <span className="bg-gray-950 text-gray-500 text-xs px-1.5 py-0.5 rounded">
            {games.length}
          </span>
        </div>
        <span className="text-gray-500 text-sm">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-gray-950 px-3.5 py-2 flex flex-col gap-1.5">
          {games.map((game) => {
            const s = getSeriesForGame(game);
            return (
              <div key={game.id} className="flex justify-between items-center text-sm py-1">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-gray-100 min-w-[100px]">
                    {game.home_team} vs {game.away_team}
                  </span>
                  {game.game_number && (
                    <span className="bg-green-950 text-green-500 text-[0.7em] px-1.5 py-0.5 rounded">
                      G{game.game_number}
                    </span>
                  )}
                </div>
                <span className="text-gray-500 text-xs">{formatTipOff(game.tip_off)}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
