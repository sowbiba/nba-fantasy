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
    return d.toLocaleTimeString("fr-FR", {
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="overflow-hidden rounded-[var(--radius-card)] border border-white/5 bg-gradient-to-br from-[color:var(--color-surface-2)] to-[color:var(--color-surface)]">
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-4 py-3 flex justify-between items-center"
      >
        <div className="flex items-center gap-2.5">
          <div className="relative flex items-center justify-center w-7 h-7 rounded-full bg-[color:var(--color-flame)]/15 border border-[color:var(--color-flame)]/30">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="text-[color:var(--color-flame)]"
            >
              <circle cx="12" cy="12" r="10" />
              <path d="M4.93 4.93c4.97 4.97 9.19 9.19 14.14 14.14" />
              <path d="M19.07 4.93c-4.97 4.97-9.19 9.19-14.14 14.14" />
              <path d="M2 12h20" />
            </svg>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-[11px] uppercase tracking-[0.22em] font-bold text-[color:var(--color-text-soft)]">
              Matchs
            </span>
            <span className="font-display text-2xl leading-none text-[color:var(--color-flame)] font-mono-num">
              {games.length}
            </span>
          </div>
        </div>
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`text-[color:var(--color-text-mute)] transition-transform duration-300 ${
            open ? "rotate-180" : ""
          }`}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {open && (
        <div className="border-t border-white/5 px-4 py-2 flex flex-col divide-y divide-white/5 animate-fade-up">
          {games.map((game) => {
            const s = getSeriesForGame(game);
            return (
              <div
                key={game.id}
                className="flex justify-between items-center py-2"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <div className="flex items-center gap-1.5 font-mono-num text-[13px] font-semibold tracking-wide">
                    <span className={`${game.status === "final" && game.home_score !== null && game.away_score !== null && game.home_score > game.away_score ? "text-[color:var(--color-emerald)]" : "text-[color:var(--color-text)]"}`}>
                      {game.home_team}
                    </span>
                    {game.status === "final" && game.home_score !== null && game.away_score !== null ? (
                      <span className="text-[color:var(--color-text-soft)] text-[12px] font-bold font-mono-num">
                        {game.home_score} - {game.away_score}
                      </span>
                    ) : game.status === "live" && game.home_score !== null ? (
                      <span className="text-[color:var(--color-flame)] text-[12px] font-bold font-mono-num animate-live-dot">
                        {game.home_score} - {game.away_score}
                      </span>
                    ) : (
                      <span className="text-[color:var(--color-text-mute)] text-[10px] px-0.5">
                        vs
                      </span>
                    )}
                    <span className={`${game.status === "final" && game.home_score !== null && game.away_score !== null && game.away_score > game.home_score ? "text-[color:var(--color-emerald)]" : "text-[color:var(--color-text)]"}`}>
                      {game.away_team}
                    </span>
                  </div>
                  {game.game_number && (
                    <span className="text-[9px] font-bold tracking-[0.1em] px-1.5 py-0.5 rounded bg-[color:var(--color-gold)]/15 text-[color:var(--color-gold)] border border-[color:var(--color-gold)]/30">
                      G{game.game_number}
                    </span>
                  )}
                  {s && (
                    <span className="text-[10px] font-mono-num text-[color:var(--color-text-mute)]">
                      {game.home_team === s.home_team
                        ? `${s.home_wins}-${s.away_wins}`
                        : `${s.away_wins}-${s.home_wins}`}
                    </span>
                  )}
                </div>
                <span className="font-mono-num text-[12px] text-[color:var(--color-text-soft)] tabular-nums shrink-0">
                  {game.status === "final" ? (
                    <span className="text-[9px] uppercase tracking-[0.15em] text-[color:var(--color-text-mute)]">Final</span>
                  ) : game.status === "live" ? (
                    <span className="text-[9px] uppercase tracking-[0.15em] text-[color:var(--color-flame)] font-bold">Live</span>
                  ) : (
                    formatTipOff(game.tip_off)
                  )}
                </span>
              </div>
            );
          })}
          {games.length === 0 && (
            <p className="py-3 text-sm text-[color:var(--color-text-mute)] text-center">
              Pas de match ce soir
            </p>
          )}
        </div>
      )}
    </div>
  );
}
