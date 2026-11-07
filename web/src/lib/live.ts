// Live des matchs de la nuit (lu côté client via /api/live → ESPN).
//
// La table `games` n'est mise à jour que par les synchros (aucune entre 00h
// et 06h Paris, quand se jouent les matchs de saison régulière) : un match y
// passe de « scheduled » à « final » sans jamais être « live ». Le statut,
// le score et le quart-temps en direct viennent donc d'ESPN, fusionnés à
// l'affichage, sans écriture en base.
import type { Game } from "@/types";
import { espnTricode } from "./espn";

export type LiveScore = {
  home: string;
  away: string;
  state: string; // "pre" | "in" | "post"
  homeScore: number;
  awayScore: number;
  period: number;
  clock: string;
};

export type LiveGame = Game & { live_detail?: string };

// Au-delà, un match « commencé » mais pas final en base est sûrement terminé
// et attend juste la synchro du matin : inutile de continuer à interroger ESPN.
const MAX_GAME_HOURS = 6;

const num = (v: unknown) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};

export function parseEspnScoreboardLive(payload: unknown): LiveScore[] {
  const events = (payload as { events?: unknown[] } | null)?.events;
  if (!Array.isArray(events)) return [];
  const rows: LiveScore[] = [];
  for (const ev of events) {
    const e = ev as {
      status?: { period?: number; displayClock?: string; type?: { state?: string } };
      competitions?: { competitors?: { homeAway?: string; team?: { abbreviation?: string }; score?: string }[] }[];
    };
    const competitors = e.competitions?.[0]?.competitors ?? [];
    const h = competitors.find((c) => c.homeAway === "home");
    const a = competitors.find((c) => c.homeAway === "away");
    if (!h || !a) continue;
    rows.push({
      home: espnTricode(h.team?.abbreviation ?? ""),
      away: espnTricode(a.team?.abbreviation ?? ""),
      state: e.status?.type?.state ?? "",
      homeScore: num(h.score),
      awayScore: num(a.score),
      period: e.status?.period ?? 0,
      clock: e.status?.displayClock ?? "",
    });
  }
  return rows;
}

function detail(period: number, clock: string): string {
  const ended = clock === "0.0" || clock === "0:00";
  if (period === 2 && ended) return "Mi-temps";
  const label = period > 4 ? (period === 5 ? "OT" : `OT${period - 4}`) : `Q${period}`;
  return ended ? `Fin ${label}` : `${label} ${clock}`;
}

export function mergeLive(games: Game[], live: LiveScore[]): LiveGame[] {
  return games.map((g) => {
    const l = live.find((x) => x.home === g.home_team && x.away === g.away_team);
    if (!l || (l.state !== "in" && l.state !== "post")) return g;
    if (l.state === "post") {
      return { ...g, status: "final", home_score: l.homeScore, away_score: l.awayScore };
    }
    return { ...g, status: "live", home_score: l.homeScore, away_score: l.awayScore, live_detail: detail(l.period, l.clock) };
  });
}

function startedAndOpen(g: Game, now: Date): boolean {
  if (g.status === "final" || !g.tip_off) return false;
  const elapsed = now.getTime() - new Date(g.tip_off).getTime();
  return elapsed >= 0 && elapsed <= MAX_GAME_HOURS * 3600_000;
}

export function needsLivePolling(games: Game[], now: Date = new Date()): boolean {
  return games.some((g) => startedAndOpen(g, now));
}

/** Dates ESPN (AAAAMMJJ, journée NBA = `games.date`) des matchs à suivre. */
export function liveDates(games: Game[], now: Date = new Date()): string[] {
  return [...new Set(games.filter((g) => startedAndOpen(g, now)).map((g) => g.date.slice(0, 10).replaceAll("-", "")))];
}
