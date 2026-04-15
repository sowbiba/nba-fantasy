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
    <div className="px-4 py-5 animate-fade-in">
      <div className="mb-5">
        <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.22em] uppercase text-[color:var(--color-crimson)]">
          <span className="w-1 h-1 rounded-full bg-[color:var(--color-crimson)] animate-live-dot" />
          Injury report
        </span>
        <h1 className="font-display text-4xl leading-none tracking-wide text-white mt-1">
          BLESS<span className="text-[color:var(--color-crimson)]">É</span>S
        </h1>
        <div className="flex items-baseline gap-2 mt-2 font-mono-num">
          <span className="font-display text-2xl text-white">{total}</span>
          <span className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-text-mute)]">
            joueurs
          </span>
          <span className="text-[color:var(--color-text-mute)]">·</span>
          <span className="font-display text-2xl text-white">{teamCount}</span>
          <span className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--color-text-mute)]">
            équipes
          </span>
        </div>
      </div>

      {total === 0 ? (
        <div className="surface p-8 text-center">
          <div className="font-display text-2xl text-[color:var(--color-text-mute)]">
            Aucune indispo
          </div>
          <p className="text-[11px] uppercase tracking-[0.2em] text-[color:var(--color-text-dim)] mt-2">
            la sync mettra la liste à jour
          </p>
        </div>
      ) : (
        <InjuriesList byTeam={byTeam} />
      )}
    </div>
  );
}
