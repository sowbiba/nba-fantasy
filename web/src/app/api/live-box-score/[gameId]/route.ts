import { NextRequest } from "next/server";
import { computeTtflScore } from "@/lib/ttfl";

export const runtime = "nodejs";

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
