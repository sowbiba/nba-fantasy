"use client";

import { useState } from "react";
import Link from "next/link";
import { RecommendationWithPlayer } from "@/types";

const tierVisual: Record<
  string,
  { stars: string; starColor: string; tone: string }
> = {
  elite: {
    stars: "★★★",
    starColor: "text-[color:var(--color-gold)]",
    tone: "bg-[color:var(--color-gold)]/10",
  },
  solid: {
    stars: "★★",
    starColor: "text-[color:var(--color-ice)]",
    tone: "bg-[color:var(--color-ice)]/10",
  },
  filler: {
    stars: "★",
    starColor: "text-[color:var(--color-text-dim)]",
    tone: "bg-white/[0.03]",
  },
};

export default function PlayerList({
  recs,
}: {
  recs: RecommendationWithPlayer[];
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <section className="mt-5 px-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 rounded-[var(--radius-card-sm)] border border-dashed border-white/10 bg-white/[0.015] text-[color:var(--color-text-soft)] hover:border-white/20 hover:bg-white/[0.03] transition-colors"
      >
        <span className="text-[11px] uppercase tracking-[0.22em] font-semibold text-[color:var(--color-text-mute)]">
          {expanded ? "Replier" : "Classement complet"}
        </span>
        <span className="flex items-center gap-2">
          <span className="font-mono-num text-sm text-[color:var(--color-text)]">
            {recs.length}
          </span>
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={`transition-transform duration-300 ${
              expanded ? "rotate-180" : ""
            }`}
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
        </span>
      </button>

      {expanded && (
        <ol className="mt-2 flex flex-col gap-1 stagger">
          {recs.map((rec) => {
            const { player, game } = rec;
            const isHome = player.team === game.home_team;
            const opponent = isHome ? game.away_team : game.home_team;
            const t = tierVisual[rec.tier] || tierVisual.filler;
            return (
              <li key={rec.id}>
                <Link
                  href={`/player/${player.id}`}
                  className="group flex items-center justify-between gap-3 px-3 py-2.5 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface)] border border-transparent hover:border-white/10 transition-colors"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="font-mono-num text-[13px] text-[color:var(--color-text-mute)] w-7 text-right tabular-nums">
                      {String(rec.rank).padStart(2, "0")}
                    </span>
                    <span
                      className={`text-xs leading-none ${t.starColor} w-10`}
                    >
                      {t.stars}
                    </span>
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-[color:var(--color-text)] truncate">
                        {player.name}
                      </div>
                      <div className="text-[11px] text-[color:var(--color-text-mute)] truncate">
                        {player.team} {isHome ? "vs" : "@"} {opponent}
                      </div>
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="font-display text-xl leading-none font-mono-num text-[color:var(--color-text)]">
                      {rec.estimated_score.toFixed(1)}
                    </div>
                  </div>
                </Link>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
