import { supabase } from "@/lib/supabase";
import InjuriesList, { InjuredPlayer } from "./InjuriesList";

export const revalidate = 300;

async function getData() {
  const res = await supabase
    .from("players")
    .select(
      "id, name, team, position, injury_status, injury_detail, injury_short_comment, injury_return_date, injury_updated_at"
    )
    .not("injury_status", "is", null)
    .order("team");

  const players = (res.data || []) as InjuredPlayer[];

  const byTeam: Record<string, InjuredPlayer[]> = {};
  for (const p of players) {
    if (!byTeam[p.team]) byTeam[p.team] = [];
    byTeam[p.team].push(p);
  }

  return { byTeam, total: players.length };
}

export default async function InjuriesPage() {
  const { byTeam, total } = await getData();
  const teamCount = Object.keys(byTeam).length;

  return (
    <div className="px-4 py-4">
      <h1 className="text-lg font-bold mb-1 text-gray-100">
        Indisponibilités
      </h1>
      <p className="text-gray-500 text-sm mb-4">
        {total} joueur{total > 1 ? "s" : ""} indisponible{total > 1 ? "s" : ""}{" "}
        · {teamCount} équipe{teamCount > 1 ? "s" : ""}
      </p>

      {total === 0 ? (
        <p className="text-gray-600 text-sm text-center py-8">
          Aucune indisponibilité. La prochaine synchro mettra la liste à jour.
        </p>
      ) : (
        <InjuriesList byTeam={byTeam} />
      )}
    </div>
  );
}
