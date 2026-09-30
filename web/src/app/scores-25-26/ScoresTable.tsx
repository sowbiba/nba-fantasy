"use client";

import { useMemo, useState } from "react";
import { decimalComma, dateFrCourt, sortScores, type GameType, type ScoreRow, type SortDir, type SortKey } from "@/lib/scores";

// Tableau trié au toucher (tâche 4) : même interaction que StandingsTable
// (@/components/StandingsTable) — un bouton pleine largeur par en-tête pour
// rester tappable, `aria-sort` correct, indicateur ▲/▼ sur la colonne
// active. Ici les deux colonnes triables (Moy., Top) sont toujours « plus
// haut = meilleur » : contrairement à StandingsTable, `dir` représente donc
// directement le sens affiché, pas un état « meilleur d'abord vs inversé ».
// Premier appui = décroissant (le meilleur en tête), second appui =
// croissant (addendum tâche 4).

function ariaSort(active: boolean, dir: SortDir): "ascending" | "descending" | "none" {
  if (!active) return "none";
  return dir === "asc" ? "ascending" : "descending";
}

function SortIndicator({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return null;
  return <span className="ml-0.5 text-[8px] align-middle">{dir === "asc" ? "▲" : "▼"}</span>;
}

function SortableHeader({
  sortKey,
  label,
  ariaLabel,
  active,
  dir,
  onToggle,
}: {
  sortKey: SortKey;
  label: string;
  ariaLabel: string;
  active: boolean;
  dir: SortDir;
  onToggle: (key: SortKey) => void;
}) {
  return (
    <th scope="col" aria-sort={ariaSort(active, dir)} className="font-semibold py-1.5 px-1.5 text-right">
      <button
        type="button"
        onClick={() => onToggle(sortKey)}
        aria-label={ariaLabel}
        className={`w-full py-0.5 text-right ${active ? "text-white" : ""}`}
      >
        {label}
        <SortIndicator active={active} dir={dir} />
      </button>
    </th>
  );
}

export default function ScoresTable({
  rows,
  initialSortKey,
  initialSortDir,
  exportParams,
}: {
  rows: ScoreRow[];
  initialSortKey: SortKey;
  initialSortDir: SortDir;
  exportParams: { type: GameType; team: string | null; minGames: number };
}) {
  const [sortKey, setSortKey] = useState<SortKey>(initialSortKey);
  const [sortDir, setSortDir] = useState<SortDir>(initialSortDir);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  const sorted = useMemo(() => sortScores(rows, sortKey, sortDir), [rows, sortKey, sortDir]);

  const exportHref = useMemo(() => {
    const sp = new URLSearchParams();
    sp.set("type", exportParams.type);
    if (exportParams.team) sp.set("team", exportParams.team);
    sp.set("min", String(exportParams.minGames));
    sp.set("sort", sortKey);
    sp.set("dir", sortDir);
    return `/scores-25-26/export?${sp.toString()}`;
  }, [exportParams, sortKey, sortDir]);

  if (rows.length === 0) {
    return (
      <div className="surface p-8 text-center">
        <div className="font-display text-2xl text-[color:var(--color-text-mute)]">Aucun joueur</div>
        <p className="text-[11px] uppercase tracking-[0.2em] text-[color:var(--color-text-dim)] mt-2">
          essaie d&apos;abaisser le minimum de matchs ou change de filtre
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto -mx-1 px-1">
        <table className="w-full text-xs border-collapse min-w-[420px]">
          <thead>
            <tr className="text-[9px] uppercase tracking-[0.14em] text-[color:var(--color-text-mute)]">
              <th scope="col" className="text-left font-semibold py-1.5 pr-2">
                Joueur
              </th>
              <th scope="col" className="text-left font-semibold py-1.5 pr-2">
                Équipe
              </th>
              <th scope="col" className="text-right font-semibold py-1.5 px-1.5">
                Matchs
              </th>
              <SortableHeader
                sortKey="avg"
                label="Moy."
                ariaLabel="Trier par moyenne TTFL"
                active={sortKey === "avg"}
                dir={sortDir}
                onToggle={toggleSort}
              />
              <SortableHeader
                sortKey="top"
                label="Top"
                ariaLabel="Trier par meilleur score"
                active={sortKey === "top"}
                dir={sortDir}
                onToggle={toggleSort}
              />
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.playerId} className="font-mono-num border-b border-white/[0.03]">
                <td className="py-1.5 pr-2 text-[color:var(--color-text)] whitespace-nowrap">{r.name}</td>
                <td className="py-1.5 pr-2 text-[color:var(--color-text-mute)]">{r.team}</td>
                <td className="text-right py-1.5 px-1.5 text-[color:var(--color-text-mute)]">{r.games}</td>
                <td className="text-right py-1.5 px-1.5 font-bold text-white">{decimalComma(r.avgTtfl)}</td>
                <td className="text-right py-1.5 px-1.5 text-[color:var(--color-text-soft)]">
                  {r.topScore}
                  <span className="text-[color:var(--color-text-dim)] ml-1">
                    {dateFrCourt(r.topDate)} vs {r.topOpponent}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <a
        href={exportHref}
        className="self-start h-10 px-4 inline-flex items-center rounded-[var(--radius-card-sm)] bg-[color:var(--color-surface-3)] border border-[color:var(--color-line)] text-[color:var(--color-text)] text-sm font-semibold"
      >
        Exporter (CSV)
      </a>
    </div>
  );
}
