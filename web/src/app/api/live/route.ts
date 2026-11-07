import { NextRequest } from "next/server";
import { parseEspnScoreboardLive, type LiveScore } from "@/lib/live";

export const runtime = "nodejs";

const SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard";
const DATE = /^\d{8}$/;

// GET /api/live?dates=20261106,20261107 → statuts/scores ESPN en direct.
// Données publiques (scores NBA), aucune donnée TTFL privée.
export async function GET(req: NextRequest) {
  const dates = (req.nextUrl.searchParams.get("dates") ?? "")
    .split(",").filter((d) => DATE.test(d)).slice(0, 3);
  const results = await Promise.all(dates.map(async (d): Promise<LiveScore[]> => {
    try {
      const res = await fetch(`${SCOREBOARD_URL}?dates=${d}`, { next: { revalidate: 20 } });
      return res.ok ? parseEspnScoreboardLive(await res.json()) : [];
    } catch {
      return [];
    }
  }));
  return Response.json(results.flat(), {
    headers: { "Cache-Control": "public, s-maxage=20, stale-while-revalidate=10" },
  });
}
