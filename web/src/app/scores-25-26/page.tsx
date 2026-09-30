import type { Metadata } from "next";
import { TEAMS } from "@/lib/pronos";
import { DEFAULT_MIN_GAMES, GAME_TYPES, parseScoresParams, type ParamsInput } from "@/lib/scores";
import { fetchScores } from "./data";
import ScoresTable from "./ScoresTable";

// Page autonome (sans habillage, voir STANDALONE_PREFIXES), non liée depuis
// l'application et non indexée. Toujours dynamique : les filtres viennent
// des search params, jamais figés au build.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Scores TTFL 2025-26",
  description: "Scores TTFL de la saison 2025-26, joueur par joueur.",
  robots: { index: false, follow: false },
};

const TEAM_CODES = TEAMS.map((t) => t.code);

export default async function ScoresPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const raw = (await searchParams) as ParamsInput;
  const { params } = parseScoresParams(raw, TEAM_CODES);

  const { rows, available } = await fetchScores(params.type, params.minGames, params.team);

  return (
    <div className="px-4 pt-6 pb-10 animate-fade-in">
      <p className="text-[10px] font-semibold tracking-[0.22em] uppercase text-[color:var(--color-gold)]">
        TTFL 2025-26
      </p>
      <h1 className="font-display text-5xl leading-none mt-1">Scores TTFL 2025-26</h1>
      <p className="mt-3 text-sm text-[color:var(--color-text-soft)]">
        Moyenne et meilleur score TTFL de chaque joueur sur la saison.
      </p>

      <form method="get" className="surface p-4 mt-6 flex flex-col gap-3">
        <div className="flex gap-2">
          <label className="flex-1 min-w-0 flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-text-mute)]">Type</span>
            <select
              name="type"
              defaultValue={params.type}
              className="h-11 px-3 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface-3)] border border-[color:var(--color-line)] text-[color:var(--color-text)]"
            >
              {GAME_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex-1 min-w-0 flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-text-mute)]">Équipe</span>
            <select
              name="team"
              defaultValue={params.team ?? ""}
              className="h-11 px-3 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface-3)] border border-[color:var(--color-line)] text-[color:var(--color-text)]"
            >
              <option value="">Toutes</option>
              {TEAMS.map((t) => (
                <option key={t.code} value={t.code}>
                  {t.code}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="flex items-end gap-2">
          <label className="flex-1 min-w-0 flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-text-mute)]">
              Minimum de matchs
            </span>
            <input
              type="number"
              name="min"
              min={1}
              max={82}
              defaultValue={params.minGames}
              placeholder={String(DEFAULT_MIN_GAMES[params.type])}
              className="h-11 px-3 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface-3)] border border-[color:var(--color-line)] text-[color:var(--color-text)]"
            />
          </label>
          <button
            type="submit"
            className="h-11 px-4 rounded-[var(--radius-card-sm)] bg-[color:var(--color-flame)] text-black font-semibold text-sm"
          >
            Filtrer
          </button>
        </div>
      </form>

      <div className="mt-6">
        {!available ? (
          <div className="surface p-8 text-center">
            <div className="font-display text-2xl text-[color:var(--color-text-mute)]">Données indisponibles</div>
            <p className="text-[11px] uppercase tracking-[0.2em] text-[color:var(--color-text-dim)] mt-2">
              réessaie plus tard
            </p>
          </div>
        ) : (
          <ScoresTable
            rows={rows}
            initialSortKey={params.sortKey}
            initialSortDir={params.sortDir}
            exportParams={{ type: params.type, team: params.team, minGames: params.minGames }}
          />
        )}
      </div>
    </div>
  );
}
