import { StandingsRow } from "@/types";
import { standingsTint, standingsZone } from "@/lib/display";

/** `.652`, jamais `0.652` (convention NBA). 0 match joué → `.000`. */
function formatPct(pct: number): string {
  return pct.toFixed(3).replace(/^0\./, ".").replace(/^-0\./, "-.");
}

function formatGB(gb: number, rank: number): string {
  if (rank === 1 || gb === 0) return "—";
  return gb.toFixed(1).replace(/\.0$/, "");
}

function ConferenceTable({ rows, ratings }: { rows: StandingsRow[]; ratings?: Record<string, number> | null }) {
  return (
    <div className="overflow-x-auto -mx-1 px-1">
      <table className="w-full text-xs border-collapse min-w-[420px]">
        <thead>
          <tr className="text-[9px] uppercase tracking-[0.14em] text-[color:var(--color-text-mute)]">
            <th className="text-left font-semibold py-1.5 pr-2">Rang</th>
            <th className="text-left font-semibold py-1.5 pr-2">Équipe</th>
            <th className="text-right font-semibold py-1.5 px-1.5">V</th>
            <th className="text-right font-semibold py-1.5 px-1.5">D</th>
            <th className="text-right font-semibold py-1.5 px-1.5">%</th>
            <th className="text-right font-semibold py-1.5 px-1.5">GB</th>
            <th className="text-right font-semibold py-1.5 px-1.5">Dom.</th>
            <th className="text-right font-semibold py-1.5 px-1.5">Ext.</th>
            <th className="text-right font-semibold py-1.5 px-1.5">10 der.</th>
            <th className="text-right font-semibold py-1.5 pl-1.5">Série</th>
            {ratings && <th className="text-right font-semibold py-1.5 pl-1.5">Force</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const zone = standingsZone(r.rank);
            const tint = standingsTint(r.rank);
            // Séparateur dès que la zone change (playoffs → play-in → hors zone),
            // donc toujours après la 6e et la 10e place sans dupliquer ces
            // numéros en dur ici.
            const next = rows[i + 1];
            const separator = !!next && standingsZone(next.rank) !== zone;
            return (
              <tr
                key={r.team}
                data-zone={zone ?? undefined}
                className={`font-mono-num ${separator ? "border-b border-white/15" : "border-b border-white/[0.03]"}`}
                style={tint > 0 ? { backgroundColor: `rgba(255, 255, 255, ${tint})` } : undefined}
              >
                <td className="py-1.5 pr-2 text-[color:var(--color-text-mute)]">{r.rank}</td>
                <td className="py-1.5 pr-2 font-bold text-white">{r.team}</td>
                <td className="text-right py-1.5 px-1.5 text-[color:var(--color-text)]">{r.wins}</td>
                <td className="text-right py-1.5 px-1.5 text-[color:var(--color-text)]">{r.losses}</td>
                <td className="text-right py-1.5 px-1.5 text-[color:var(--color-text-soft)]">{formatPct(Number(r.pct))}</td>
                <td className="text-right py-1.5 px-1.5 text-[color:var(--color-text-mute)]">{formatGB(Number(r.games_behind), r.rank)}</td>
                <td className="text-right py-1.5 px-1.5 text-[color:var(--color-text-mute)]">{r.home_wins}-{r.home_losses}</td>
                <td className="text-right py-1.5 px-1.5 text-[color:var(--color-text-mute)]">{r.away_wins}-{r.away_losses}</td>
                <td className="text-right py-1.5 px-1.5 text-[color:var(--color-text-mute)]">{r.last10_wins}-{r.last10_losses}</td>
                <td className="text-right py-1.5 pl-1.5 text-[color:var(--color-text-mute)]">{r.streak || "—"}</td>
                {ratings && (
                  <td className="text-right py-1.5 pl-1.5 text-[color:var(--color-text-mute)]">
                    {r.team in ratings ? Math.round(ratings[r.team]) : "—"}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function StandingsTable({ rows, ratings }: { rows: StandingsRow[]; ratings?: Record<string, number> | null }) {
  const est = rows.filter((r) => r.conference === "Est").sort((a, b) => a.rank - b.rank);
  const ouest = rows.filter((r) => r.conference === "Ouest").sort((a, b) => a.rank - b.rank);

  if (rows.length === 0) {
    return (
      <div className="surface p-8 text-center">
        <div className="font-display text-2xl text-[color:var(--color-text-mute)]">Pas encore de classement</div>
        <p className="text-[11px] uppercase tracking-[0.2em] text-[color:var(--color-text-dim)] mt-2">
          la saison n&apos;a pas encore commencé
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-[10px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)] mb-2">Conférence Est</h2>
        <ConferenceTable rows={est} ratings={ratings} />
      </div>
      <div>
        <h2 className="text-[10px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)] mb-2">Conférence Ouest</h2>
        <ConferenceTable rows={ouest} ratings={ratings} />
      </div>
      <p className="text-[10px] text-[color:var(--color-text-mute)] tracking-wide">
        1-6 playoffs · 7-10 play-in
      </p>
    </div>
  );
}
