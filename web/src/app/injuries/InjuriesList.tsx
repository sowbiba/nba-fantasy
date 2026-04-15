"use client";

import { useState } from "react";

export type InjuredPlayer = {
  id: number;
  name: string;
  team: string;
  position: string;
  injury_status: string;
  injury_detail: string | null;
  injury_short_comment?: string | null;
  injury_return_date?: string | null;
  injury_updated_at?: string | null;
};

// Official-ish NBA team colors (primary)
const teamColors: Record<string, string> = {
  ATL: "#E03A3E", BOS: "#007A33", BKN: "#000000", CHA: "#1D1160",
  CHI: "#CE1141", CLE: "#860038", DAL: "#00538C", DEN: "#0E2240",
  DET: "#C8102E", GSW: "#1D428A", HOU: "#CE1141", IND: "#002D62",
  LAC: "#C8102E", LAL: "#552583", MEM: "#5D76A9", MIA: "#98002E",
  MIL: "#00471B", MIN: "#0C2340", NOP: "#0C2340", NYK: "#006BB6",
  OKC: "#007AC1", ORL: "#0077C0", PHI: "#006BB6", PHX: "#1D1160",
  POR: "#E03A3E", SAC: "#5A2D81", SAS: "#C4CED4", TOR: "#CE1141",
  UTA: "#002B5C", WAS: "#002B5C",
};

// Lighter, saturated versions for readability on dark background
const teamColorsBright: Record<string, string> = {
  ATL: "#E03A3E", BOS: "#10a050", BKN: "#4a4a4a", CHA: "#5a42c8",
  CHI: "#E63946", CLE: "#D33482", DAL: "#0C7FD6", DEN: "#3b82f6",
  DET: "#EF4444", GSW: "#3B82F6", HOU: "#E63946", IND: "#FDBB30",
  LAC: "#F87171", LAL: "#A855F7", MEM: "#60A5FA", MIA: "#EC4899",
  MIL: "#10B981", MIN: "#60A5FA", NOP: "#4169E1", NYK: "#3B82F6",
  OKC: "#38BDF8", ORL: "#0EA5E9", PHI: "#3B82F6", PHX: "#F97316",
  POR: "#E63946", SAC: "#A855F7", SAS: "#9CA3AF", TOR: "#EF4444",
  UTA: "#FBBF24", WAS: "#DC2626",
};

const statusColors: Record<string, { bg: string; text: string; label: string }> = {
  Out: { bg: "bg-red-950", text: "text-red-400", label: "OUT" },
  Doubtful: { bg: "bg-red-950", text: "text-red-300", label: "DOUTEUX" },
  Questionable: { bg: "bg-amber-950", text: "text-amber-400", label: "INCERT." },
  "Day-To-Day": { bg: "bg-blue-950", text: "text-blue-400", label: "GTD" },
};

function getStatusBadge(status: string) {
  return (
    statusColors[status] || {
      bg: "bg-gray-800",
      text: "text-gray-400",
      label: status.toUpperCase(),
    }
  );
}

function formatReturnDate(dateStr: string | null | undefined): string | null {
  if (!dateStr) return null;
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return null;
    const now = new Date();
    const diffDays = Math.round((d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
    if (diffDays < 0) return null;
    if (diffDays === 0) return "aujourd'hui";
    if (diffDays === 1) return "demain";
    if (diffDays < 7) return `dans ${diffDays}j`;
    return d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
  } catch {
    return null;
  }
}

function formatUpdateAge(dateStr: string | null | undefined): string | null {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return null;
  const diffDays = Math.floor((Date.now() - d.getTime()) / (1000 * 60 * 60 * 24));
  if (diffDays <= 0) return "màj aujourd'hui";
  if (diffDays === 1) return "màj hier";
  if (diffDays < 7) return `màj il y a ${diffDays}j`;
  return `màj ${d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" })}`;
}

function TeamBlock({
  team,
  players,
  open,
  onToggle,
}: {
  team: string;
  players: InjuredPlayer[];
  open: boolean;
  onToggle: () => void;
}) {
  const outCount = players.filter(
    (p) => p.injury_status === "Out" || p.injury_status === "Doubtful"
  ).length;
  const gtdCount = players.length - outCount;
  const teamColor = teamColors[team] || "#1e293b";

  return (
    <div className="bg-gray-900 rounded-xl overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full px-3.5 py-2.5 flex justify-between items-center text-left border-l-4"
        style={{ backgroundColor: teamColor, borderLeftColor: teamColorsBright[team] || "#64748b" }}
      >
        <div className="flex items-center gap-2">
          <span className="text-white/70 text-xs w-3 inline-block">
            {open ? "▲" : "▼"}
          </span>
          <span className="font-bold text-sm text-white">{team}</span>
          <span className="text-white/70 text-xs">
            · {players.length} joueur{players.length > 1 ? "s" : ""}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {outCount > 0 && (
            <span className="bg-black/40 text-white text-[0.65em] px-1.5 py-0.5 rounded font-bold">
              {outCount} OUT
            </span>
          )}
          {gtdCount > 0 && (
            <span className="bg-black/40 text-white text-[0.65em] px-1.5 py-0.5 rounded font-bold">
              {gtdCount} GTD
            </span>
          )}
        </div>
      </button>

      {open && (
        <div className="divide-y divide-gray-950">
          {players.map((p) => {
            const badge = getStatusBadge(p.injury_status);
            const returnStr = formatReturnDate(p.injury_return_date);
            const updateStr = formatUpdateAge(p.injury_updated_at);
            return (
              <div key={p.id} className="px-3.5 py-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-sm text-gray-100">
                        {p.name}
                      </span>
                      <span className="text-gray-500 text-[0.65em]">
                        {p.position}
                      </span>
                    </div>
                    {p.injury_detail && (
                      <div className="text-gray-400 text-xs mt-0.5">
                        {p.injury_detail}
                      </div>
                    )}
                    {p.injury_short_comment && (
                      <div className="text-gray-500 text-xs mt-1 leading-snug">
                        {p.injury_short_comment}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <span
                      className={`${badge.bg} ${badge.text} text-[0.65em] px-2 py-0.5 rounded font-bold`}
                    >
                      {badge.label}
                    </span>
                    {returnStr && (
                      <span className="text-gray-500 text-[0.65em]">
                        retour : {returnStr}
                      </span>
                    )}
                    {updateStr && (
                      <span className="text-gray-600 text-[0.6em]">
                        {updateStr}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function InjuriesList({
  byTeam,
}: {
  byTeam: Record<string, InjuredPlayer[]>;
}) {
  const teams = Object.keys(byTeam).sort();
  const [openTeams, setOpenTeams] = useState<Record<string, boolean>>({});

  const toggle = (team: string) => {
    setOpenTeams((prev) => ({ ...prev, [team]: !prev[team] }));
  };
  const openAll = () => {
    setOpenTeams(Object.fromEntries(teams.map((t) => [t, true])));
  };
  const closeAll = () => {
    setOpenTeams({});
  };

  const anyOpen = teams.some((t) => openTeams[t]);

  return (
    <>
      <div className="flex justify-end mb-2">
        <button
          onClick={anyOpen ? closeAll : openAll}
          className="text-blue-400 text-xs font-medium"
        >
          {anyOpen ? "Tout replier" : "Tout déplier"}
        </button>
      </div>
      <div className="flex flex-col gap-2">
        {teams.map((team) => (
          <TeamBlock
            key={team}
            team={team}
            players={byTeam[team]}
            open={!!openTeams[team]}
            onToggle={() => toggle(team)}
          />
        ))}
      </div>
    </>
  );
}
