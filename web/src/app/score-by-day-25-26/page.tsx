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

const STATS: { key: keyof DayRow; label: string; title: string }[] = [
  { key: "minutes", label: "Min", title: "Minutes" },
  { key: "pts", label: "Pts", title: "Points" },
  { key: "reb", label: "Reb", title: "Rebonds" },
  { key: "ast", label: "PD", title: "Passes décisives" },
  { key: "stl", label: "Int", title: "Interceptions" },
  { key: "blk", label: "Ctr", title: "Contres" },
  { key: "tov", label: "BP", title: "Balles perdues" },
];

// Tirs réussis (M) / tentés (T), une colonne chacun, regroupés sous un
// en-tête commun.
const SHOTS: { label: string; title: string; made: keyof DayRow; att: keyof DayRow }[] = [
  { label: "Tirs", title: "Tirs", made: "fgm", att: "fga" },
  { label: "3 pts", title: "Tirs à 3 points", made: "tpm", att: "tpa" },
  { label: "LF", title: "Lancers francs", made: "ftm", att: "fta" },
];

// Colonne joueur figée à gauche pendant le défilement horizontal (fond
// opaque pour masquer les colonnes qui passent dessous).
const stickyCell = "sticky left-0 z-[1] bg-[color:var(--color-ink)]";
const th = "font-semibold py-1 px-1.5 text-right";
const td = "text-right py-1.5 px-1.5 whitespace-nowrap";

function DayTable({ rows }: { rows: DayRow[] }) {
  return (
    <div className="overflow-x-auto -mx-4">
      <table className="w-full text-xs border-collapse min-w-[720px] [&_tr>*:last-child]:pr-4">
        <thead className="text-[9px] uppercase tracking-[0.14em] text-[color:var(--color-text-mute)]">
          <tr>
            <th scope="col" rowSpan={2} className={`${stickyCell} text-left font-semibold py-1 pl-4 pr-2 align-bottom`}>
              # Joueur
            </th>
            <th scope="col" rowSpan={2} className={`${th} text-white align-bottom`}>TTFL</th>
            {STATS.map((c) => (
              <th key={c.key} scope="col" rowSpan={2} title={c.title} className={`${th} align-bottom`}>
                {c.label}
              </th>
            ))}
            {SHOTS.map((g) => (
              <th key={g.label} scope="colgroup" colSpan={2} title={g.title} className="font-semibold py-1 px-1.5 text-center border-b border-white/10">
                {g.label}
              </th>
            ))}
          </tr>
          <tr>
            {SHOTS.flatMap((g) => [
              <th key={`${g.label}-m`} scope="col" title={`${g.title} réussis`} className={th}>M</th>,
              <th key={`${g.label}-t`} scope="col" title={`${g.title} tentés`} className={th}>T</th>,
            ])}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.playerId} className="font-mono-num border-b border-white/[0.03]">
              <td className={`${stickyCell} py-1.5 pl-4 pr-2 whitespace-nowrap`}>
                <span className="inline-block w-6 text-[color:var(--color-text-mute)]">{i + 1}</span>
                <span className="text-[color:var(--color-text)]">{r.name}</span>
                <span className="block pl-6 text-[10px] text-[color:var(--color-text-dim)]">
                  {r.team} {r.home ? "vs" : "@"} {r.opponent}
                </span>
              </td>
              <td className={`${td} font-bold text-white`}>{r.ttfl}</td>
              {STATS.map((c) => (
                <td key={c.key} className={`${td} text-[color:var(--color-text-soft)]`}>
                  {r[c.key]}
                </td>
              ))}
              {SHOTS.flatMap((g) => [
                <td key={`${g.label}-m`} className={`${td} text-[color:var(--color-text)]`}>{r[g.made]}</td>,
                <td key={`${g.label}-t`} className={`${td} text-[color:var(--color-text-mute)]`}>{r[g.att]}</td>,
              ])}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
