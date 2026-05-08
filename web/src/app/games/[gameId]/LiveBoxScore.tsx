"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";

const POLL_INTERVAL_MS = 15_000;

type LivePlayer = {
  player_id: number;
  player_name: string;
  team: string;
  is_home: boolean;
  on_court: boolean;
  played: boolean;
  minutes: number;
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
  fouls: number;
  ttfl_score: number;
};

type LiveData = {
  game_id: string;
  status: number;
  status_text: string;
  period: number;
  game_clock: string;
  home_team: string;
  away_team: string;
  home_score: number;
  away_score: number;
  players: LivePlayer[];
  fetched_at: string;
};

function parseClock(iso: string): string {
  const m = iso.match(/PT(\d+)M([\d.]+)S/);
  if (!m) return iso;
  const minutes = parseInt(m[1], 10);
  const seconds = Math.floor(parseFloat(m[2]));
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export default function LiveBoxScore({
  gameId,
  homeTeam,
  awayTeam,
  initialStatus,
}: {
  gameId: string;
  homeTeam: string;
  awayTeam: string;
  initialStatus: string;
}) {
  const [data, setData] = useState<LiveData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());
  const lastFetchRef = useRef<number>(0);

  const fetchLive = useCallback(async () => {
    try {
      setError(null);
      const res = await fetch(`/api/live-box-score/${gameId}`, {
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = (await res.json()) as LiveData;
      setData(json);
      lastFetchRef.current = Date.now();
    } catch (e) {
      setError(e instanceof Error ? e.message : "erreur");
    } finally {
      setLoading(false);
    }
  }, [gameId]);

  useEffect(() => {
    fetchLive();
  }, [fetchLive]);

  useEffect(() => {
    // Polling only matters while the game can still change.
    if (data?.status === 3 || initialStatus === "final") return;

    let interval: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      if (interval) return;
      interval = setInterval(fetchLive, POLL_INTERVAL_MS);
    };
    const stop = () => {
      if (interval) {
        clearInterval(interval);
        interval = null;
      }
    };

    start();

    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        fetchLive();
        start();
      } else {
        stop();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    const tick = setInterval(() => setNow(Date.now()), 1000);

    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
      clearInterval(tick);
    };
  }, [fetchLive, data?.status, initialStatus]);

  const isLive = data?.status === 2;
  const isFinal = data?.status === 3 || initialStatus === "final";
  const secondsAgo = data
    ? Math.max(0, Math.floor((now - lastFetchRef.current) / 1000))
    : 0;

  const homePlayers = (data?.players ?? [])
    .filter((p) => p.is_home && (p.played || p.minutes > 0))
    .sort((a, b) => b.ttfl_score - a.ttfl_score);
  const awayPlayers = (data?.players ?? [])
    .filter((p) => !p.is_home && (p.played || p.minutes > 0))
    .sort((a, b) => b.ttfl_score - a.ttfl_score);

  return (
    <div className="mt-5">
      {/* scoreboard */}
      <div className="rounded-[var(--radius-card)] border border-white/5 bg-[color:var(--color-surface)] px-4 py-4">
        <div className="flex items-center justify-center gap-4 font-mono-num">
          <div className="text-center">
            <div className="text-[10px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)]">
              {homeTeam}
            </div>
            <div className="font-display text-5xl leading-none text-white mt-1">
              {data?.home_score ?? "—"}
            </div>
          </div>
          <div className="flex flex-col items-center gap-1 min-w-[80px]">
            {isLive ? (
              <span className="text-[9px] font-bold tracking-[0.22em] px-1.5 py-0.5 rounded bg-[color:var(--color-flame)]/15 text-[color:var(--color-flame)] border border-[color:var(--color-flame)]/30 animate-live-dot">
                LIVE
              </span>
            ) : isFinal ? (
              <span className="text-[9px] font-bold tracking-[0.22em] px-1.5 py-0.5 rounded bg-white/5 text-[color:var(--color-text-soft)] border border-white/10">
                FINAL
              </span>
            ) : (
              <span className="text-[9px] tracking-[0.22em] px-1.5 py-0.5 rounded bg-white/5 text-[color:var(--color-text-mute)] border border-white/10">
                À VENIR
              </span>
            )}
            {data && !isFinal && (
              <div className="text-[10px] text-[color:var(--color-text-soft)] mt-0.5">
                {isLive
                  ? `Q${data.period} · ${parseClock(data.game_clock)}`
                  : data.status_text}
              </div>
            )}
          </div>
          <div className="text-center">
            <div className="text-[10px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)]">
              {awayTeam}
            </div>
            <div className="font-display text-5xl leading-none text-white mt-1">
              {data?.away_score ?? "—"}
            </div>
          </div>
        </div>
      </div>

      {/* refresh bar — hidden on finals (data won't change) */}
      {!isFinal && (
        <div className="flex items-center justify-between mt-3 px-1 text-[10px] uppercase tracking-[0.18em] text-[color:var(--color-text-mute)]">
          <span>
            {loading && !data
              ? "Chargement…"
              : error
                ? `Erreur : ${error}`
                : `Actualisé il y a ${secondsAgo}s`}
          </span>
          <button
            onClick={fetchLive}
            disabled={loading}
            className="inline-flex items-center gap-1 px-2 py-1 rounded border border-white/10 hover:border-[color:var(--color-flame)]/40 hover:text-[color:var(--color-flame)] transition-colors disabled:opacity-50"
          >
            <span className={loading ? "animate-spin inline-block" : ""}>↻</span>
            <span>Actualiser</span>
          </button>
        </div>
      )}

      {/* stats tables */}
      {data && data.players.length > 0 ? (
        <div className="mt-4 flex flex-col gap-3">
          <TeamStatsTable teamLabel={data.home_team} players={homePlayers} />
          <TeamStatsTable teamLabel={data.away_team} players={awayPlayers} />
        </div>
      ) : data ? (
        <div className="mt-6 text-center text-[11px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)]">
          Match pas encore commencé
        </div>
      ) : null}
    </div>
  );
}

const statHeaders = [
  { key: "pts", label: "PTS" },
  { key: "reb", label: "REB" },
  { key: "ast", label: "AST" },
  { key: "stl", label: "STL" },
  { key: "blk", label: "BLK" },
  { key: "fg", label: "FG" },
  { key: "tp", label: "3P" },
  { key: "ft", label: "FT" },
  { key: "tov", label: "TO" },
  { key: "fouls", label: "PF" },
];

function TeamStatsTable({
  teamLabel,
  players,
}: {
  teamLabel: string;
  players: LivePlayer[];
}) {
  return (
    <div className="rounded-[var(--radius-card)] border border-white/5 bg-[color:var(--color-surface)] overflow-hidden">
      <div className="px-4 py-2 text-[10px] uppercase tracking-[0.22em] font-bold text-[color:var(--color-text-soft)] border-b border-white/[0.04]">
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
            {players.map((p) => {
              const ttflColor =
                p.ttfl_score >= 50
                  ? "text-[color:var(--color-emerald)]"
                  : p.ttfl_score >= 30
                    ? "text-white"
                    : p.ttfl_score >= 0
                      ? "text-[color:var(--color-text-soft)]"
                      : "text-[color:var(--color-crimson)]";
              return (
                <tr
                  key={p.player_id}
                  className="border-t border-white/[0.03] hover:bg-white/[0.02]"
                >
                  <td className="px-3 py-1.5 sticky left-0 bg-[color:var(--color-surface)]">
                    <Link
                      href={`/player/${p.player_id}`}
                      className="flex items-center gap-1.5 text-[color:var(--color-text)] hover:text-[color:var(--color-flame)] transition-colors truncate max-w-[130px]"
                    >
                      {p.on_court && (
                        <span className="w-1.5 h-1.5 rounded-full bg-[color:var(--color-flame)] shrink-0 animate-live-dot" />
                      )}
                      <span className="truncate">{p.player_name}</span>
                    </Link>
                  </td>
                  <td
                    className={`text-center px-1.5 py-1.5 font-bold text-[13px] ${ttflColor}`}
                  >
                    {p.ttfl_score}
                  </td>
                  <td className="text-center px-1.5 py-1.5">{p.pts}</td>
                  <td className="text-center px-1.5 py-1.5">{p.reb}</td>
                  <td className="text-center px-1.5 py-1.5">{p.ast}</td>
                  <td className="text-center px-1.5 py-1.5">{p.stl}</td>
                  <td className="text-center px-1.5 py-1.5">{p.blk}</td>
                  <td className="text-center px-1.5 py-1.5 text-[color:var(--color-text-mute)]">
                    {p.fgm}/{p.fga}
                  </td>
                  <td className="text-center px-1.5 py-1.5 text-[color:var(--color-text-mute)]">
                    {p.tpm}/{p.tpa}
                  </td>
                  <td className="text-center px-1.5 py-1.5 text-[color:var(--color-text-mute)]">
                    {p.ftm}/{p.fta}
                  </td>
                  <td className="text-center px-1.5 py-1.5 text-[color:var(--color-text-mute)]">
                    {p.tov}
                  </td>
                  <td
                    className={`text-center px-1.5 py-1.5 ${
                      p.fouls >= 5
                        ? "text-[color:var(--color-crimson)] font-semibold"
                        : p.fouls >= 4
                          ? "text-[color:var(--color-flame)]"
                          : "text-[color:var(--color-text-mute)]"
                    }`}
                  >
                    {p.fouls}
                  </td>
                  <td className="text-center px-1.5 py-1.5 text-[color:var(--color-text-dim)]">
                    {p.minutes}
                  </td>
                </tr>
              );
            })}
            {players.length === 0 && (
              <tr>
                <td
                  colSpan={12}
                  className="text-center py-3 text-[color:var(--color-text-mute)]"
                >
                  Pas encore entré en jeu
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
