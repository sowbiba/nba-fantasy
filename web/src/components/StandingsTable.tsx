"use client";

import { useState } from "react";
import { StandingsRow } from "@/types";
import { formatPointDiff, sortStandings, standingsTint, standingsZone, StandingsSortKey, SortDir } from "@/lib/display";

/** `.652`, jamais `0.652` (convention NBA). 0 match joué → `.000`. */
function formatPct(pct: number): string {
  return pct.toFixed(3).replace(/^0\./, ".").replace(/^-0\./, "-.");
}

function formatGB(gb: number, rank: number): string {
  if (rank === 1 || gb === 0) return "—";
  return gb.toFixed(1).replace(/\.0$/, "");
}

function ariaSort(active: boolean, dir: SortDir): "ascending" | "descending" | "none" {
  if (!active) return "none";
  return dir === "asc" ? "ascending" : "descending";
}

function SortIndicator({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return null;
  return <span className="ml-0.5 text-[8px] align-middle">{dir === "asc" ? "▲" : "▼"}</span>;
}

/** En-tête triable (tâche 2) : un bouton pleine largeur pour rester tappable
 *  au doigt (mobile-first), un `aria-sort` sur le `<th>` pour les lecteurs
 *  d'écran, un indicateur ▲/▼ visible seulement sur la colonne active. */
function SortableHeader({
  sortKey,
  label,
  ariaLabel,
  align,
  active,
  dir,
  onToggle,
}: {
  sortKey: StandingsSortKey;
  label: string;
  ariaLabel: string;
  align: "left" | "right";
  active: boolean;
  dir: SortDir;
  onToggle: (key: StandingsSortKey) => void;
}) {
  return (
    <th
      scope="col"
      aria-sort={ariaSort(active, dir)}
      className={`font-semibold py-1.5 ${align === "left" ? "text-left pr-2" : "text-right px-1.5"}`}
    >
      <button
        type="button"
        onClick={() => onToggle(sortKey)}
        aria-label={ariaLabel}
        className={`w-full py-0.5 ${align === "left" ? "text-left" : "text-right"} ${active ? "text-white" : ""}`}
      >
        {label}
        <SortIndicator active={active} dir={dir} />
      </button>
    </th>
  );
}

function ConferenceTable({ rows, ratings }: { rows: StandingsRow[]; ratings?: Record<string, number> | null }) {
  // Tri par défaut = rang officiel (spec tâche 2). Un tri par une autre
  // colonne masque les séparateurs de zone (ils n'ont de sens qu'en ordre de
  // rang) mais garde la teinte de chaque ligne, toujours calculée depuis le
  // rang officiel `r.rank` — jamais depuis la position affichée.
  const [sortKey, setSortKey] = useState<StandingsSortKey>("rank");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  function toggleSort(key: StandingsSortKey) {
    if (key === sortKey) {
      // Rang déjà actif : inverser l'ordre officiel n'a pas de sens, un
      // second appui sur « Rang » reste sans effet.
      if (key === "rank") return;
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  const sorted = sortStandings(rows, sortKey, sortDir, ratings);
  const isDefaultOrder = sortKey === "rank";
  const header = (key: StandingsSortKey, label: string, ariaLabel: string, align: "left" | "right" = "right") => (
    <SortableHeader sortKey={key} label={label} ariaLabel={ariaLabel} align={align} active={sortKey === key} dir={sortDir} onToggle={toggleSort} />
  );

  return (
    <div className="overflow-x-auto -mx-1 px-1">
      <table className="w-full text-xs border-collapse min-w-[460px]">
        <thead>
          <tr className="text-[9px] uppercase tracking-[0.14em] text-[color:var(--color-text-mute)]">
            {header("rank", "Rang", "Trier par rang officiel", "left")}
            <th className="text-left font-semibold py-1.5 pr-2">Équipe</th>
            {header("wins", "V", "Trier par victoires")}
            {header("losses", "D", "Trier par défaites")}
            {header("pct", "%", "Trier par pourcentage de victoires")}
            {header("games_behind", "GB", "Trier par écart au premier")}
            <th className="text-right font-semibold py-1.5 px-1.5">Dom.</th>
            <th className="text-right font-semibold py-1.5 px-1.5">Ext.</th>
            {header("last10", "10 der.", "Trier par victoires sur les 10 derniers matchs")}
            {header("streak", "Série", "Trier par série en cours")}
            {header("point_diff", "Écart", "Trier par écart moyen de points")}
            {ratings && header("force", "Force", "Trier par force (cote Elo)")}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => {
            const zone = standingsZone(r.rank);
            const tint = standingsTint(r.rank);
            // Séparateur dès que la zone change (playoffs → play-in → hors
            // zone) : n'a de sens qu'en ordre de rang officiel, donc masqué
            // dès qu'on trie par une autre colonne (tâche 2).
            const next = sorted[i + 1];
            const separator = isDefaultOrder && !!next && standingsZone(next.rank) !== zone;
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
                <td className="text-right py-1.5 px-1.5 text-[color:var(--color-text-mute)]">{r.streak || "—"}</td>
                <td className="text-right py-1.5 px-1.5 text-[color:var(--color-text-mute)]">{formatPointDiff(r.point_diff)}</td>
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
