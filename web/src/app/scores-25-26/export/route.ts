import { TEAMS } from "@/lib/pronos";
import { buildScoresCsv, csvFilename, parseScoresParams, sortScores } from "@/lib/scores";
import { fetchScores } from "../data";

// Route d'export CSV de la page autonome `/scores-25-26` (tâche 4) :
// mêmes paramètres/validation que la page (parseScoresParams), CSV
// `;`/BOM/virgule décimale, jamais de 500 sur une erreur attendue (params
// invalides → 400, vue absente → 503).

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const TEAM_CODES = TEAMS.map((t) => t.code);

export async function GET(req: Request): Promise<Response> {
  const { searchParams } = new URL(req.url);
  const { params, invalid } = parseScoresParams(
    {
      type: searchParams.get("type"),
      team: searchParams.get("team"),
      min: searchParams.get("min"),
      sort: searchParams.get("sort"),
      dir: searchParams.get("dir"),
    },
    TEAM_CODES,
  );

  if (invalid.length > 0) {
    return new Response(`Paramètres invalides : ${invalid.join(", ")}`, { status: 400 });
  }

  const { rows, available } = await fetchScores(params.type, params.minGames, params.team);
  if (!available) {
    return new Response("Données indisponibles", { status: 503 });
  }

  const sorted = sortScores(rows, params.sortKey, params.sortDir);
  const csv = buildScoresCsv(sorted);
  const filename = csvFilename(params.type, params.team);

  return new Response(csv, {
    status: 200,
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${filename}"`,
    },
  });
}
