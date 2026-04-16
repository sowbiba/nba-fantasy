"use client";

import { useState } from "react";
import { Game, Player } from "@/types";
import Link from "next/link";

type GameLog = {
  id: number;
  player_id: number;
  game_id: string;
  pts: number;
  reb: number;
  ast: number;
  stl: number;
  blk: number;
  fgm: number;
  fga: number;
  tpm: number;
  tpa: number;
  ftm: number;
  fta: number;
  tov: number;
  minutes: number;
  ttfl_score: number;
  is_home: boolean;
};

const statHeaders = [
  { key: "pts", label: "PTS" },
  { key: "reb", label: "REB" },
  { key: "ast", label: "AST" },
  { key: "stl", label: "STL" },
  { key: "blk", label: "BLK" },
  { key: "fgm_fga", label: "FG" },
  { key: "tpm_tpa", label: "3P" },
  { key: "ftm_fta", label: "FT" },
  { key: "tov", label: "TO" },
];

function GameCard({
  game,
  players,
  logs,
}: {
  game: Game;
  players: Record<number, Player>;
  logs: GameLog[];
}) {
  const [open, setOpen] = useState(false);

  const homeLogs = logs
    .filter((l) => l.is_home && l.minutes > 0)
    .sort((a, b) => b.ttfl_score - a.ttfl_score);
  const awayLogs = logs
    .filter((l) => !l.is_home && l.minutes > 0)
    .sort((a, b) => b.ttfl_score - a.ttfl_score);

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

  return (
    <div className="rounded-[var(--radius-card)] border border-white/5 bg-gradient-to-br from-[color:var(--color-surface-2)] to-[color:var(--color-surface)] overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
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
          {game.status === "live" && (
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
          className={`text-[color:var(--color-text-mute)] transition-transform duration-300 shrink-0 ${
            open ? "rotate-180" : ""
          }`}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {open && (
        <div className="border-t border-white/5 animate-fade-up">
          {game.status === "final" && logs.length > 0 ? (
            <>
              <TeamStatsTable
                teamLabel={game.home_team}
                logs={homeLogs}
                players={players}
                accent={homeWon}
              />
              <TeamStatsTable
                teamLabel={game.away_team}
                logs={awayLogs}
                players={players}
                accent={!homeWon && game.home_score !== null}
              />
            </>
          ) : (
            <div className="px-4 py-4 text-center">
              <div className="text-[11px] uppercase tracking-[0.2em] text-[color:var(--color-text-mute)]">
                {game.status === "scheduled"
                  ? `Tip-off ${game.tip_off ? new Date(game.tip_off).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Paris" }) + " (heure Paris)" : "à confirmer"}`
                  : game.status === "live"
                    ? "En cours..."
                    : "Pas de données"}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function TeamStatsTable({
  teamLabel,
  logs,
  players,
  accent,
}: {
  teamLabel: string;
  logs: GameLog[];
  players: Record<number, Player>;
  accent: boolean;
}) {
  return (
    <div className="border-b border-white/[0.04] last:border-0">
      <div
        className={`px-4 py-1.5 text-[10px] uppercase tracking-[0.22em] font-bold ${
          accent
            ? "text-[color:var(--color-emerald)]"
            : "text-[color:var(--color-text-soft)]"
        }`}
      >
        {teamLabel}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[11px] font-mono-num">
          <thead>
            <tr className="text-[color:var(--color-text-mute)] text-[9px] uppercase tracking-[0.15em]">
              <th className="text-left px-3 py-1.5 w-32 sticky left-0 bg-[color:var(--color-surface)]">
                Joueur
              </th>
              <th className="text-center px-1.5 py-1.5 font-bold text-[color:var(--color-flame)]">
                TTFL
              </th>
              {statHeaders.map((h) => (
                <th key={h.key} className="text-center px-1.5 py-1.5">
                  {h.label}
                </th>
              ))}
              <th className="text-center px-1.5 py-1.5">MIN</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => {
              const player = players[log.player_id];
              const ttflColor =
                log.ttfl_score >= 50
                  ? "text-[color:var(--color-emerald)]"
                  : log.ttfl_score >= 30
                    ? "text-white"
                    : log.ttfl_score >= 0
                      ? "text-[color:var(--color-text-soft)]"
                      : "text-[color:var(--color-crimson)]";
              return (
                <tr
                  key={log.id}
                  className="border-t border-white/[0.03] hover:bg-white/[0.02]"
                >
                  <td className="px-3 py-1.5 sticky left-0 bg-[color:var(--color-surface)]">
                    <Link
                      href={`/player/${log.player_id}`}
                      className="text-[color:var(--color-text)] hover:text-[color:var(--color-flame)] transition-colors truncate block max-w-[120px]"
                    >
                      {player?.name || "?"}
                    </Link>
                  </td>
                  <td
                    className={`text-center px-1.5 py-1.5 font-bold text-[13px] ${ttflColor}`}
                  >
                    {log.ttfl_score}
                  </td>
                  <td className="text-center px-1.5 py-1.5">
                    {log.pts}
                  </td>
                  <td className="text-center px-1.5 py-1.5">
                    {log.reb}
                  </td>
                  <td className="text-center px-1.5 py-1.5">
                    {log.ast}
                  </td>
                  <td className="text-center px-1.5 py-1.5">
                    {log.stl}
                  </td>
                  <td className="text-center px-1.5 py-1.5">
                    {log.blk}
                  </td>
                  <td className="text-center px-1.5 py-1.5 text-[color:var(--color-text-mute)]">
                    {log.fgm}/{log.fga}
                  </td>
                  <td className="text-center px-1.5 py-1.5 text-[color:var(--color-text-mute)]">
                    {log.tpm}/{log.tpa}
                  </td>
                  <td className="text-center px-1.5 py-1.5 text-[color:var(--color-text-mute)]">
                    {log.ftm}/{log.fta}
                  </td>
                  <td className="text-center px-1.5 py-1.5 text-[color:var(--color-text-mute)]">
                    {log.tov}
                  </td>
                  <td className="text-center px-1.5 py-1.5 text-[color:var(--color-text-dim)]">
                    {log.minutes}
                  </td>
                </tr>
              );
            })}
            {logs.length === 0 && (
              <tr>
                <td
                  colSpan={12}
                  className="text-center py-3 text-[color:var(--color-text-mute)]"
                >
                  Pas de données
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function GamesList({
  games,
  players,
  gameLogs,
}: {
  games: Game[];
  players: Record<number, Player>;
  gameLogs: Record<string, unknown>[];
}) {
  // Group logs by game_id
  const logsByGame: Record<string, GameLog[]> = {};
  for (const log of gameLogs) {
    const gid = log.game_id as string;
    if (!logsByGame[gid]) logsByGame[gid] = [];
    logsByGame[gid].push(log as unknown as GameLog);
  }

  // Group games by date
  const dateGroups: [string, Game[]][] = [];
  const dateMap = new Map<string, Game[]>();
  for (const g of games) {
    const list = dateMap.get(g.date) || [];
    list.push(g);
    dateMap.set(g.date, list);
  }
  for (const [d, gs] of dateMap) {
    dateGroups.push([d, gs]);
  }

  if (games.length === 0) {
    return (
      <div className="surface p-8 text-center">
        <div className="font-display text-2xl text-[color:var(--color-text-mute)]">
          Aucun match terminé
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
        return (
          <div key={dateStr}>
            <h2 className="text-[10px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)] mb-1.5 px-1 capitalize">
              {label}
            </h2>
            <div className="flex flex-col gap-1.5">
              {dateGames.map((game) => (
                <GameCard
                  key={game.id}
                  game={game}
                  players={players}
                  logs={logsByGame[game.id] || []}
                />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
