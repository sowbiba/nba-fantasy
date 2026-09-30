import type { Metadata } from "next";
import Link from "next/link";
import { TEAMS } from "@/lib/pronos";
import { frDayMonth, frLongDate } from "@/lib/date";
import { neighbors, parseDayParams, type DayParamsInput, type DayRow } from "@/lib/score-by-day";
import { fetchDay, fetchNights } from "./data";
import AutoSubmitSelect from "./AutoSubmitSelect";

// Page autonome (sans habillage, voir STANDALONE_PREFIXES), non liée depuis
// l'application et non indexée : pour chaque soirée 2025-26, tous les
// joueurs entrés en jeu avec leurs stats et leur score TTFL, du meilleur au
// moins bon. Toujours dynamique (search params).
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Scores TTFL par soirée 2025-26",
  description: "Scores TTFL de chaque joueur, soirée par soirée, saison 2025-26.",
  robots: { index: false, follow: false },
};

const TEAM_CODES = TEAMS.map((t) => t.code);

const control =
  "h-11 px-3 rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface-3)] border border-[color:var(--color-line)] text-[color:var(--color-text)]";
const navBtn =
  "h-10 px-3 inline-flex items-center rounded-full border border-[color:var(--color-line)] text-xs font-semibold text-[color:var(--color-text)] active:bg-white/5";

function href(date: string, team: string | null): string {
  const sp = new URLSearchParams({ date });
  if (team) sp.set("team", team);
  return `/score-by-day-25-26?${sp.toString()}`;
}

/** « jeu. 25/12 » : tient dans le sélecteur sur mobile. */
function shortDay(iso: string): string {
  const wd = new Date(`${iso}T12:00:00Z`).toLocaleDateString("fr-FR", { weekday: "short", timeZone: "UTC" });
  return `${wd} ${frDayMonth(iso)}`;
}

const TYPE_LABEL: Record<string, string> = { playoffs: "Playoffs", cup_final: "Finale NBA Cup" };

function Unavailable() {
  return (
    <div className="surface p-8 text-center">
      <div className="font-display text-2xl text-[color:var(--color-text-mute)]">Données indisponibles</div>
      <p className="text-[11px] uppercase tracking-[0.2em] text-[color:var(--color-text-dim)] mt-2">réessaie plus tard</p>
    </div>
  );
}

export default async function ScoreByDayPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const raw = (await searchParams) as DayParamsInput;
  const { nights, available: nightsOk } = await fetchNights();
  const { date, team } = parseDayParams(raw, nights, TEAM_CODES);
  const day = date ? await fetchDay(date, team) : { rows: [] as DayRow[], available: nightsOk };
  const { prev, next } = neighbors(nights, date);
  const special = [...new Set(day.rows.map((r) => TYPE_LABEL[r.gameType]).filter(Boolean))];

  return (
    <div className="px-4 pt-6 pb-10 animate-fade-in">
      <p className="text-[10px] font-semibold tracking-[0.22em] uppercase text-[color:var(--color-gold)]">TTFL 2025-26</p>
      <h1 className="font-display text-5xl leading-none mt-1">Scores par soirée</h1>
      <p className="mt-3 text-sm text-[color:var(--color-text-soft)]">
        Tous les joueurs de la soirée, leurs stats et leur score TTFL.
      </p>

      {!nightsOk ? (
        <div className="mt-6">
          <Unavailable />
        </div>
      ) : (
        <>
          <form method="get" className="surface p-4 mt-6 flex flex-col gap-3">
            <div className="flex gap-2">
              <label className="flex-[3] min-w-0 flex flex-col gap-1">
                <span className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-text-mute)]">Soirée</span>
                <AutoSubmitSelect name="date" defaultValue={date ?? ""} className={control}>
                  {[...nights].reverse().map((n) => (
                    <option key={n} value={n}>
                      {shortDay(n)}
                    </option>
                  ))}
                </AutoSubmitSelect>
              </label>
              <label className="flex-[2] min-w-0 flex flex-col gap-1">
                <span className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-text-mute)]">Équipe</span>
                <AutoSubmitSelect name="team" defaultValue={team ?? ""} className={control}>
                  <option value="">Toutes</option>
                  {TEAM_CODES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </AutoSubmitSelect>
              </label>
            </div>
            <noscript>
              <button type="submit" className={`${control} bg-[color:var(--color-flame)] text-black font-semibold`}>
                Voir
              </button>
            </noscript>
          </form>

          {date && (
            <div className="mt-5 flex items-center justify-between gap-2">
              {prev ? (
                <Link href={href(prev, team)} className={navBtn} aria-label="Soirée précédente">
                  ← {frDayMonth(prev)}
                </Link>
              ) : (
                <span />
              )}
              <div className="text-center min-w-0">
                <div className="font-display text-2xl leading-none capitalize">{frLongDate(date)}</div>
                <div className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-text-mute)] mt-1">
                  {[...special, `${day.rows.length} joueur${day.rows.length > 1 ? "s" : ""}`].join(" · ")}
                </div>
              </div>
              {next ? (
                <Link href={href(next, team)} className={navBtn} aria-label="Soirée suivante">
                  {frDayMonth(next)} →
                </Link>
              ) : (
                <span />
              )}
            </div>
          )}

          <div className="mt-4">
            {!day.available ? (
              <Unavailable />
            ) : day.rows.length === 0 ? (
              <div className="surface p-8 text-center">
                <div className="font-display text-2xl text-[color:var(--color-text-mute)]">Aucun joueur</div>
              </div>
            ) : (
              <DayTable rows={day.rows} />
            )}
          </div>
        </>
      )}
    </div>
  );
}

const COLS: { key: keyof DayRow; label: string; title: string }[] = [
  { key: "minutes", label: "Min", title: "Minutes" },
  { key: "pts", label: "Pts", title: "Points" },
  { key: "reb", label: "Reb", title: "Rebonds" },
  { key: "ast", label: "PD", title: "Passes décisives" },
  { key: "stl", label: "Int", title: "Interceptions" },
  { key: "blk", label: "Ctr", title: "Contres" },
  { key: "tov", label: "BP", title: "Balles perdues" },
  { key: "fg", label: "Tirs", title: "Tirs réussis / tentés" },
  { key: "tp", label: "3pts", title: "Tirs à 3 points réussis / tentés" },
  { key: "ft", label: "LF", title: "Lancers francs réussis / tentés" },
];

function DayTable({ rows }: { rows: DayRow[] }) {
  return (
    <div className="overflow-x-auto -mx-4 px-4">
      <table className="w-full text-xs border-collapse min-w-[640px]">
        <thead>
          <tr className="text-[9px] uppercase tracking-[0.14em] text-[color:var(--color-text-mute)]">
            <th scope="col" className="text-left font-semibold py-1.5 pr-2 w-7">#</th>
            <th scope="col" className="text-left font-semibold py-1.5 pr-2">Joueur</th>
            <th scope="col" className="text-right font-semibold py-1.5 px-1.5 text-white">TTFL</th>
            {COLS.map((c) => (
              <th key={c.key} scope="col" title={c.title} className="text-right font-semibold py-1.5 px-1.5">
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.playerId} className="font-mono-num border-b border-white/[0.03]">
              <td className="py-1.5 pr-2 text-[color:var(--color-text-mute)]">{i + 1}</td>
              <td className="py-1.5 pr-2 whitespace-nowrap">
                <span className="text-[color:var(--color-text)]">{r.name}</span>
                <span className="ml-1.5 text-[10px] text-[color:var(--color-text-dim)]">
                  {r.team} {r.home ? "vs" : "@"} {r.opponent}
                </span>
              </td>
              <td className="text-right py-1.5 px-1.5 font-bold text-white">{r.ttfl}</td>
              {COLS.map((c) => (
                <td key={c.key} className="text-right py-1.5 px-1.5 text-[color:var(--color-text-soft)] whitespace-nowrap">
                  {r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
