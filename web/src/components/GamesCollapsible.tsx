"use client";

import { useState } from "react";
import { Game } from "@/types";
import { winPctPair } from "@/lib/display";

interface Props {
  games: Game[];
  defaultOpen?: boolean;
  // Mode connecté seulement (spec L3a §3, game_predictions) : home_win_prob par game_id,
  // passé en objet simple (composant client, jamais de Map en props). Match absent de
  // l'objet (prédiction manquante) → aucune chance de victoire affichée, jamais « NaN ».
  predictions?: Record<string, number>;
}

export default function GamesCollapsible({ games, defaultOpen = false, predictions }: Props) {
  const [open, setOpen] = useState(defaultOpen);

  const formatTipOff = (tipOff: string | null) => {
    if (!tipOff) return "";
    const d = new Date(tipOff);
    return d.toLocaleTimeString("fr-FR", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "Europe/Paris",
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
            const p = predictions?.[game.id];
            const showPct = p !== undefined && Number.isFinite(p);
            const pct = showPct ? winPctPair(p) : null;
            return (
              <div key={game.id} className="flex justify-between items-center py-2">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="flex items-center gap-1.5 font-mono-num text-[13px] font-semibold tracking-wide">
                    <span className="flex flex-col items-center leading-tight">
                      <span className={`${game.status === "final" && game.home_score !== null && game.away_score !== null && game.home_score > game.away_score ? "text-[color:var(--color-emerald)]" : "text-[color:var(--color-text)]"}`}>
                        {game.home_team}
                      </span>
                      {pct && (
                        <span className="text-[9px] font-normal text-[color:var(--color-text-mute)]">{pct.home}</span>
                      )}
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
                    <span className="flex flex-col items-center leading-tight">
                      <span className={`${game.status === "final" && game.home_score !== null && game.away_score !== null && game.away_score > game.home_score ? "text-[color:var(--color-emerald)]" : "text-[color:var(--color-text)]"}`}>
                        {game.away_team}
                      </span>
                      {pct && (
                        <span className="text-[9px] font-normal text-[color:var(--color-text-mute)]">{pct.away}</span>
                      )}
                    </span>
                  </div>
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
