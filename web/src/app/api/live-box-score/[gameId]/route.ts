import { NextRequest } from "next/server";
import { computeTtflScore } from "@/lib/ttfl";
import { supabase } from "@/lib/supabase/public";
import { fetchEspnLiveBox, matchPlayerId } from "@/lib/espn";

export const runtime = "nodejs";

type StoredLog = {
  player_id: number;
  pts: number | null;
  reb: number | null;
  ast: number | null;
  stl: number | null;
  blk: number | null;
  fgm: number | null;
  fga: number | null;
  tpm: number | null;
  tpa: number | null;
  ftm: number | null;
  fta: number | null;
  tov: number | null;
  fouls: number | null;
  minutes: number | null;
  ttfl_score: number | null;
  is_home: boolean;
  players: { name: string } | { name: string }[] | null;
};

function playerNameFromJoin(p: StoredLog["players"]): string {
  if (!p) return "—";
  return Array.isArray(p) ? p[0]?.name ?? "—" : p.name;
}

async function buildFromGameLogs(
  gameId: string,
  homeTeam: string,
  awayTeam: string,
  homeScore: number | null,
  awayScore: number | null,
) {
  const { data, error } = await supabase
    .from("game_logs")
    .select(
      `player_id, pts, reb, ast, stl, blk, fgm, fga, tpm, tpa, ftm, fta,
       tov, fouls, minutes, ttfl_score, is_home, players ( name )`,
    )
    .eq("game_id", gameId);

  if (error || !data || data.length === 0) return null;

  const logs = data as unknown as StoredLog[];
  const players = logs.map((l) => ({
    player_id: l.player_id,
    player_name: playerNameFromJoin(l.players),
    team: l.is_home ? homeTeam : awayTeam,
    is_home: l.is_home,
    on_court: false,
    played: (l.minutes ?? 0) > 0,
    minutes: l.minutes ?? 0,
    pts: l.pts ?? 0,
    reb: l.reb ?? 0,
    ast: l.ast ?? 0,
    stl: l.stl ?? 0,
    blk: l.blk ?? 0,
    fgm: l.fgm ?? 0,
    fga: l.fga ?? 0,
    tpm: l.tpm ?? 0,
    tpa: l.tpa ?? 0,
    ftm: l.ftm ?? 0,
    fta: l.fta ?? 0,
    tov: l.tov ?? 0,
    fouls: l.fouls ?? 0,
    ttfl_score: l.ttfl_score ?? 0,
  }));

  return {
    game_id: gameId,
    status: 3,
    status_text: "Final",
    period: 4,
    game_clock: "PT00M00.0S",
    home_team: homeTeam,
    away_team: awayTeam,
    home_score:
      homeScore ?? players.filter((p) => p.is_home).reduce((s, p) => s + p.pts, 0),
    away_score:
      awayScore ?? players.filter((p) => !p.is_home).reduce((s, p) => s + p.pts, 0),
    players,
    fetched_at: new Date().toISOString(),
  };
}

type StoredPlayer = { id: number; name: string; team: string };

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ gameId: string }> }
) {
  const { gameId } = await params;
  if (!/^\d+$/.test(gameId)) {
    return Response.json({ error: "invalid gameId" }, { status: 400 });
  }

  // For finals, cdn.nba.com used to drop the box-score JSON after some time
  // (and now 403s outright). Serve from our own game_logs (authoritative
  // once the sync ran).
  const { data: gameRow } = await supabase
    .from("games")
    .select("date, status, home_team, away_team, home_score, away_score")
    .eq("id", gameId)
    .single();

  if (gameRow?.status === "final") {
    const stored = await buildFromGameLogs(
      gameId,
      gameRow.home_team,
      gameRow.away_team,
      gameRow.home_score,
      gameRow.away_score,
    );
    if (stored) {
      return Response.json(stored, {
        headers: {
          "Cache-Control": "public, s-maxage=300, stale-while-revalidate=60",
        },
      });
    }
    // No logs yet — fall through to ESPN; if that also fails, we'll 502.
  }

  if (!gameRow) {
    return Response.json({ error: "not_found" }, { status: 404 });
  }

  const espnDate = gameRow.date.replaceAll("-", "");
  const live = await fetchEspnLiveBox(espnDate, gameRow.home_team, gameRow.away_team);
  if (!live) {
    return Response.json({ error: "upstream" }, { status: 502 });
  }
  const { event, rows } = live;

  const { data: rosterRows } = await supabase
    .from("players")
    .select("id, name, team")
    .in("team", [gameRow.home_team, gameRow.away_team]);
  const roster = (rosterRows ?? []) as StoredPlayer[];

  const players = rows
    .filter((r) => r.played)
    .map((r) => {
      const isHome = r.team === gameRow.home_team;
      const candidates = roster.filter((p) => p.team === r.team);
      const stats = {
        pts: r.pts,
        reb: r.reb,
        ast: r.ast,
        stl: r.stl,
        blk: r.blk,
        fgm: r.fgm,
        fga: r.fga,
        tpm: r.tpm,
        tpa: r.tpa,
        ftm: r.ftm,
        fta: r.fta,
        tov: r.tov,
      };
      return {
        player_id: matchPlayerId(r.name, candidates),
        player_name: r.name,
        team: r.team,
        is_home: isHome,
        on_court: false,
        played: r.played,
        minutes: r.minutes,
        ...stats,
        fouls: r.fouls,
        ttfl_score: computeTtflScore(stats),
      };
    });

  const status = event.state === "post" ? 3 : event.state === "in" ? 2 : 1;
  const statusText =
    event.state === "post" ? "Final" : event.state === "in" ? "En direct" : "À venir";

  return Response.json(
    {
      game_id: gameId,
      status,
      status_text: statusText,
      period: event.period,
      game_clock: event.clock,
      home_team: gameRow.home_team,
      away_team: gameRow.away_team,
      home_score: event.homeScore,
      away_score: event.awayScore,
      players,
      fetched_at: new Date().toISOString(),
    },
    {
      headers: {
        "Cache-Control": "public, s-maxage=8, stale-while-revalidate=4",
      },
    }
  );
}
