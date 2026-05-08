import { NextRequest } from "next/server";
import { computeTtflScore } from "@/lib/ttfl";
import { supabase } from "@/lib/supabase";

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

type RawStats = {
  minutes?: string;
  points?: number;
  reboundsTotal?: number;
  assists?: number;
  steals?: number;
  blocks?: number;
  fieldGoalsMade?: number;
  fieldGoalsAttempted?: number;
  threePointersMade?: number;
  threePointersAttempted?: number;
  freeThrowsMade?: number;
  freeThrowsAttempted?: number;
  turnovers?: number;
  foulsPersonal?: number;
};

type RawPlayer = {
  personId: number;
  firstName: string;
  familyName: string;
  starter?: string;
  oncourt?: string;
  played?: string;
  statistics?: RawStats;
};

type RawTeam = {
  teamTricode: string;
  score?: number;
  players?: RawPlayer[];
};

type RawBoxScore = {
  game: {
    gameId: string;
    gameStatus: number;
    gameStatusText: string;
    period: number;
    gameClock: string;
    homeTeam: RawTeam;
    awayTeam: RawTeam;
  };
};

function parseMinutes(min?: string): number {
  if (!min) return 0;
  const m = min.match(/PT(\d+)M/);
  return m ? parseInt(m[1], 10) : 0;
}

function mapPlayer(p: RawPlayer, isHome: boolean, teamTricode: string) {
  const s = p.statistics ?? {};
  const minutes = parseMinutes(s.minutes);
  const stats = {
    pts: s.points ?? 0,
    reb: s.reboundsTotal ?? 0,
    ast: s.assists ?? 0,
    stl: s.steals ?? 0,
    blk: s.blocks ?? 0,
    fgm: s.fieldGoalsMade ?? 0,
    fga: s.fieldGoalsAttempted ?? 0,
    tpm: s.threePointersMade ?? 0,
    tpa: s.threePointersAttempted ?? 0,
    ftm: s.freeThrowsMade ?? 0,
    fta: s.freeThrowsAttempted ?? 0,
    tov: s.turnovers ?? 0,
    fouls: s.foulsPersonal ?? 0,
  };
  return {
    player_id: p.personId,
    player_name: `${p.firstName} ${p.familyName}`,
    team: teamTricode,
    is_home: isHome,
    on_court: p.oncourt === "1",
    played: p.played === "1",
    minutes,
    ...stats,
    ttfl_score: computeTtflScore(stats),
  };
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ gameId: string }> }
) {
  const { gameId } = await params;
  if (!/^\d+$/.test(gameId)) {
    return Response.json({ error: "invalid gameId" }, { status: 400 });
  }

  // For finals, the NBA CDN drops the box-score JSON after some time.
  // Serve from our own game_logs (authoritative once the sync ran).
  const { data: gameRow } = await supabase
    .from("games")
    .select("status, home_team, away_team, home_score, away_score")
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
    // No logs yet — fall through to CDN; if that also fails, we'll 502.
  }

  const url = `https://cdn.nba.com/static/json/liveData/boxscore/boxscore_${gameId}.json`;
  let upstream: Response;
  try {
    upstream = await fetch(url, {
      next: { revalidate: 8 },
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        Referer: "https://www.nba.com/",
        Accept: "application/json, text/plain, */*",
      },
    });
  } catch (e) {
    return Response.json(
      { error: "fetch_failed", message: e instanceof Error ? e.message : "unknown" },
      { status: 502 }
    );
  }

  if (!upstream.ok) {
    return Response.json(
      { error: "upstream", status: upstream.status },
      { status: 502 }
    );
  }

  let raw: RawBoxScore;
  try {
    raw = (await upstream.json()) as RawBoxScore;
  } catch (e) {
    const ct = upstream.headers.get("content-type") ?? "";
    return Response.json(
      {
        error: "json_parse_failed",
        content_type: ct,
        message: e instanceof Error ? e.message : "unknown",
      },
      { status: 502 }
    );
  }

  if (!raw?.game) {
    return Response.json(
      { error: "unexpected_payload", keys: Object.keys(raw ?? {}) },
      { status: 502 }
    );
  }
  const g = raw.game;
  const home = g.homeTeam;
  const away = g.awayTeam;

  const players = [
    ...(home.players ?? []).map((p) => mapPlayer(p, true, home.teamTricode)),
    ...(away.players ?? []).map((p) => mapPlayer(p, false, away.teamTricode)),
  ].filter((p) => p.played || p.minutes > 0);

  return Response.json(
    {
      game_id: g.gameId,
      status: g.gameStatus,
      status_text: g.gameStatusText,
      period: g.period,
      game_clock: g.gameClock,
      home_team: home.teamTricode,
      away_team: away.teamTricode,
      home_score: home.score ?? 0,
      away_score: away.score ?? 0,
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
