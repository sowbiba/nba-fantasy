import type { Conference, StandingsRow } from "@/lib/pronos";
import { standingsTint, standingsZone } from "@/lib/display";

/** Classement projeté d'une conférence : même habillage discret que le
 *  Classement (StandingsTable) — teinte dégressive 1-6 / 7-10 et
 *  séparateurs entre zones, sans couleurs fortes. */
export default function PronoStandings({ conference, rows }: { conference: Conference; rows: StandingsRow[] }) {
  return (
    <div>
      <h3 className="text-[10px] uppercase tracking-[0.22em] text-[color:var(--color-text-mute)] mb-2">
        Classement projeté · {conference}
      </h3>
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="text-[9px] uppercase tracking-[0.14em] text-[color:var(--color-text-mute)]">
            <th scope="col" className="text-left font-semibold py-1.5 pr-2 w-10">Rang</th>
            <th scope="col" className="text-left font-semibold py-1.5 pr-2">Équipe</th>
            <th scope="col" className="text-right font-semibold py-1.5 px-1.5">V</th>
            <th scope="col" className="text-right font-semibold py-1.5 pl-1.5">D</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const rank = i + 1;
            const zone = standingsZone(rank);
            const tint = standingsTint(rank);
            const separator = i < rows.length - 1 && standingsZone(rank + 1) !== zone;
            return (
              <tr
                key={r.team}
                data-zone={zone ?? undefined}
                className={`font-mono-num ${separator ? "border-b border-white/15" : "border-b border-white/[0.03]"}`}
                style={tint > 0 ? { backgroundColor: `rgba(255, 255, 255, ${tint})` } : undefined}
              >
                <td className="py-1.5 pr-2 text-[color:var(--color-text-mute)]">{rank}</td>
                <td className="py-1.5 pr-2 font-bold text-white">{r.team}</td>
                <td className="text-right py-1.5 px-1.5 text-[color:var(--color-text)]">{r.wins}</td>
                <td className="text-right py-1.5 pl-1.5 text-[color:var(--color-text-soft)]">{r.losses}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
