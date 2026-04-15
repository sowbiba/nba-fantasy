import { supabase } from "@/lib/supabase";

export const revalidate = 300;

type InjuredPlayer = {
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

async function getData() {
  const res = await supabase
    .from("players")
    .select(
      "id, name, team, position, injury_status, injury_detail, injury_short_comment, injury_return_date, injury_updated_at"
    )
    .not("injury_status", "is", null)
    .order("team");

  const players = (res.data || []) as InjuredPlayer[];

  // Group by team
  const byTeam: Record<string, InjuredPlayer[]> = {};
  for (const p of players) {
    if (!byTeam[p.team]) byTeam[p.team] = [];
    byTeam[p.team].push(p);
  }

  return { byTeam, total: players.length };
}

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

export default async function InjuriesPage() {
  const { byTeam, total } = await getData();
  const teams = Object.keys(byTeam).sort();

  return (
    <div className="px-4 py-4">
      <h1 className="text-lg font-bold mb-1">Indisponibilités</h1>
      <p className="text-gray-500 text-sm mb-4">
        {total} joueur{total > 1 ? "s" : ""} indisponible{total > 1 ? "s" : ""}{" "}
        · {teams.length} équipe{teams.length > 1 ? "s" : ""}
      </p>

      {total === 0 && (
        <p className="text-gray-600 text-sm text-center py-8">
          Aucune indisponibilité. La prochaine synchro mettra la liste à jour.
        </p>
      )}

      <div className="flex flex-col gap-3">
        {teams.map((team) => {
          const players = byTeam[team];
          return (
            <div
              key={team}
              className="bg-gray-900 rounded-xl overflow-hidden"
            >
              <div className="px-3.5 py-2 bg-gray-800 flex justify-between items-center">
                <span className="font-bold text-sm text-gray-100">{team}</span>
                <span className="text-gray-500 text-xs">
                  {players.length} joueur{players.length > 1 ? "s" : ""}
                </span>
              </div>
              <div className="divide-y divide-gray-950">
                {players.map((p) => {
                  const badge = getStatusBadge(p.injury_status);
                  const returnStr = formatReturnDate(p.injury_return_date);
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
                          {p.injury_updated_at && (
                            <span className="text-gray-600 text-[0.6em]">
                              {(() => {
                                const d = new Date(p.injury_updated_at);
                                const diffDays = Math.floor((Date.now() - d.getTime()) / (1000 * 60 * 60 * 24));
                                if (diffDays <= 0) return "màj aujourd'hui";
                                if (diffDays === 1) return "màj hier";
                                if (diffDays < 7) return `màj il y a ${diffDays}j`;
                                return `màj ${d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" })}`;
                              })()}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
