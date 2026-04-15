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

// Official-ish NBA team colors (primary). Kept intact per requirement.
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

const statusColors: Record<
  string,
  { classes: string; label: string }
> = {
  Out: {
    classes:
      "bg-[color:var(--color-crimson)]/15 text-[color:var(--color-crimson)] border border-[color:var(--color-crimson)]/40",
    label: "OUT",
  },
  Doubtful: {
    classes:
      "bg-[color:var(--color-crimson)]/10 text-red-300 border border-red-400/30",
    label: "DOUTEUX",
  },
  Questionable: {
    classes:
      "bg-amber-500/10 text-amber-300 border border-amber-400/30",
    label: "INCERT.",
  },
  "Day-To-Day": {
    classes:
      "bg-[color:var(--color-ice)]/10 text-[color:var(--color-ice)] border border-[color:var(--color-ice)]/30",
    label: "GTD",
  },
};

function getStatusBadge(status: string) {
  return (
    statusColors[status] || {
      classes:
        "bg-white/5 text-[color:var(--color-text-soft)] border border-white/10",
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
    const diffDays = Math.round(
      (d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)
    );
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
  const diffDays = Math.floor(
    (Date.now() - d.getTime()) / (1000 * 60 * 60 * 24)
  );
  if (diffDays <= 0) return "màj aujourd'hui";
  if (diffDays === 1) return "màj hier";
  if (diffDays < 7) return `màj il y a ${diffDays}j`;
  return `màj ${d.toLocaleDateString("fr-FR", {
    day: "numeric",
    month: "short",
  })}`;
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
  const brightColor = teamColorsBright[team] || "#64748b";

  return (
    <div
      className="overflow-hidden rounded-[var(--radius-card)] border border-white/5"
      style={{
        background: `linear-gradient(180deg, ${teamColor}12 0%, rgba(15, 16, 23, 0) 100%), var(--color-surface)`,
      }}
    >
      <button
        onClick={onToggle}
        className="w-full flex justify-between items-center text-left transition-colors relative overflow-hidden"
        style={{
          background: `linear-gradient(90deg, ${teamColor}cc 0%, ${teamColor}70 100%)`,
        }}
      >
        {/* subtle diagonal court line overlay */}
        <span
          aria-hidden
          className="absolute inset-0 pointer-events-none opacity-15"
          style={{
            background:
              "repeating-linear-gradient(-30deg, rgba(255,255,255,0.08) 0, rgba(255,255,255,0.08) 1px, transparent 1px, transparent 10px)",
          }}
        />
        <div className="relative flex items-center gap-3 px-4 py-3">
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={`text-white/90 transition-transform duration-300 ${
              open ? "rotate-180" : ""
            }`}
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
          <span
            className="font-display text-2xl leading-none tracking-wider text-white"
            style={{ textShadow: "0 1px 2px rgba(0,0,0,0.6)" }}
          >
            {team}
          </span>
          <span className="text-[10px] uppercase tracking-[0.18em] font-semibold text-white/80 font-mono-num">
            · {players.length} joueur{players.length > 1 ? "s" : ""}
          </span>
        </div>
        <div className="relative flex items-center gap-1.5 px-4">
          {outCount > 0 && (
            <span className="bg-black/50 backdrop-blur-sm text-white text-[10px] font-bold tracking-[0.1em] px-2 py-0.5 rounded-full border border-white/10">
              {outCount} OUT
            </span>
          )}
          {gtdCount > 0 && (
            <span className="bg-black/50 backdrop-blur-sm text-white text-[10px] font-bold tracking-[0.1em] px-2 py-0.5 rounded-full border border-white/10">
              {gtdCount} GTD
            </span>
          )}
        </div>
      </button>

      {open && (
        <div className="divide-y divide-white/[0.04] animate-fade-in">
          {players.map((p) => {
            const badge = getStatusBadge(p.injury_status);
            const returnStr = formatReturnDate(p.injury_return_date);
            const updateStr = formatUpdateAge(p.injury_updated_at);
            return (
              <div
                key={p.id}
                className="px-4 py-3 relative"
                style={{
                  borderLeft: `2px solid ${brightColor}50`,
                }}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2 flex-wrap">
                      <span className="font-semibold text-sm text-[color:var(--color-text)]">
                        {p.name}
                      </span>
                      <span className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--color-text-mute)] font-mono-num">
                        {p.position}
                      </span>
                    </div>
                    {p.injury_detail && (
                      <div className="text-xs text-[color:var(--color-text-soft)] mt-1">
                        {p.injury_detail}
                      </div>
                    )}
                    {p.injury_short_comment && (
                      <div className="text-xs text-[color:var(--color-text-mute)] mt-1 leading-relaxed">
                        {p.injury_short_comment}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <span
                      className={`text-[10px] font-bold tracking-[0.1em] px-2 py-0.5 rounded-full ${badge.classes}`}
                    >
                      {badge.label}
                    </span>
                    {returnStr && (
                      <span className="text-[10px] text-[color:var(--color-text-mute)] font-mono-num">
                        retour · {returnStr}
                      </span>
                    )}
                    {updateStr && (
                      <span className="text-[9px] text-[color:var(--color-text-dim)] font-mono-num">
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
      <div className="flex justify-end mb-3">
        <button
          onClick={anyOpen ? closeAll : openAll}
          className="text-[10px] uppercase tracking-[0.22em] font-bold text-[color:var(--color-flame)] hover:text-[color:var(--color-flame-soft)] transition-colors"
        >
          {anyOpen ? "Tout replier" : "Tout déplier"}
        </button>
      </div>
      <div className="flex flex-col gap-2 stagger">
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
