"use client";

import { Game } from "@/types";
import Link from "next/link";

function GameCard({ game }: { game: Game }) {
  const homeWon =
    game.home_score !== null &&
    game.away_score !== null &&
    game.home_score > game.away_score;

  const d = new Date(game.date + "T12:00:00");
  const dateLabel = d.toLocaleDateString("fr-FR", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });

  const isLive = game.status === "live";

  return (
    <Link
      href={`/games/${game.id}`}
      className="rounded-[var(--radius-card)] border border-white/5 bg-gradient-to-br from-[color:var(--color-surface-2)] to-[color:var(--color-surface)] flex items-center justify-between px-4 py-3 text-left"
    >
      <div className="flex items-center gap-3 min-w-0">
        <div className="text-[10px] uppercase tracking-[0.12em] text-[color:var(--color-text-mute)] w-14 shrink-0">
          {dateLabel}
        </div>
        <div className="flex items-center gap-1.5 font-mono-num text-[14px] font-bold tracking-wide">
          <span
            className={
              homeWon
                ? "text-[color:var(--color-emerald)]"
                : "text-[color:var(--color-text)]"
            }
          >
            {game.home_team}
          </span>
          {game.home_score !== null && game.away_score !== null ? (
            <span className="text-[color:var(--color-text-soft)] text-[13px] font-bold">
              {game.home_score} - {game.away_score}
            </span>
          ) : (
            <span className="text-[color:var(--color-text-mute)] text-xs">
              vs
            </span>
          )}
          <span
            className={
              !homeWon && game.home_score !== null
                ? "text-[color:var(--color-emerald)]"
                : "text-[color:var(--color-text)]"
            }
          >
            {game.away_team}
          </span>
        </div>
        {game.game_number && (
          <span className="text-[9px] font-bold tracking-[0.1em] px-1.5 py-0.5 rounded bg-[color:var(--color-gold)]/15 text-[color:var(--color-gold)] border border-[color:var(--color-gold)]/30">
            G{game.game_number}
          </span>
        )}
        {game.status === "scheduled" && (
          <span className="text-[9px] tracking-[0.1em] px-1.5 py-0.5 rounded bg-white/5 text-[color:var(--color-text-mute)] border border-white/10">
            {game.tip_off
              ? new Date(game.tip_off).toLocaleTimeString("fr-FR", {
                  hour: "2-digit",
                  minute: "2-digit",
                  timeZone: "Europe/Paris",
                })
              : "TBD"}
          </span>
        )}
        {isLive && (
          <span className="text-[9px] font-bold tracking-[0.1em] px-1.5 py-0.5 rounded bg-[color:var(--color-flame)]/15 text-[color:var(--color-flame)] border border-[color:var(--color-flame)]/30 animate-live-dot">
            LIVE
          </span>
        )}
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
        className="text-[color:var(--color-flame)] shrink-0"
      >
        <path d="M9 6l6 6-6 6" />
      </svg>
    </Link>
  );
}

export default function GamesList({ games }: { games: Game[] }) {
  // Group games by date, then sort each day by tip-off (earliest first).
  // Games without a tip_off go last.
  const dateMap = new Map<string, Game[]>();
  for (const g of games) {
    const list = dateMap.get(g.date) || [];
    list.push(g);
    dateMap.set(g.date, list);
  }
  for (const list of dateMap.values()) {
    list.sort((a, b) => {
      if (!a.tip_off) return 1;
      if (!b.tip_off) return -1;
      return a.tip_off.localeCompare(b.tip_off);
    });
  }

  const todayNBA = new Date().toLocaleDateString("en-CA", {
    timeZone: "America/New_York",
  });

  const todayGroup: [string, Game[]][] = [];
  const futureGroups: [string, Game[]][] = [];
  const pastGroups: [string, Game[]][] = [];

  for (const [d, gs] of dateMap) {
    if (d === todayNBA) todayGroup.push([d, gs]);
    else if (d > todayNBA) futureGroups.push([d, gs]);
    else pastGroups.push([d, gs]);
  }
  futureGroups.sort((a, b) => a[0].localeCompare(b[0]));
  pastGroups.sort((a, b) => b[0].localeCompare(a[0]));

  const dateGroups = [...todayGroup, ...futureGroups, ...pastGroups];

  if (games.length === 0) {
    return (
      <div className="surface p-8 text-center">
        <div className="font-display text-2xl text-[color:var(--color-text-mute)]">
          Aucun match
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {dateGroups.map(([dateStr, dateGames]) => {
        const d = new Date(dateStr + "T12:00:00");
        const label = d.toLocaleDateString("fr-FR", {
          weekday: "long",
          day: "numeric",
          month: "long",
        });
        const isToday = dateStr === todayNBA;
        return (
          <div key={dateStr}>
            <h2
              className={`text-[10px] uppercase tracking-[0.22em] mb-1.5 px-1 capitalize ${
                isToday
                  ? "text-[color:var(--color-flame)] font-bold"
                  : "text-[color:var(--color-text-mute)]"
              }`}
            >
              {isToday ? "Aujourd'hui" : label}
            </h2>
            <div className="flex flex-col gap-1.5">
              {dateGames.map((game) => (
                <GameCard key={game.id} game={game} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
